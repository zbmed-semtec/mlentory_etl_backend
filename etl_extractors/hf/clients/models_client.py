from __future__ import annotations

from typing import Optional, List, Dict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from huggingface_hub import HfApi, ModelCard
from datasets import load_dataset
import logging

from ..hf_helper import HFHelper


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HFModelsClient:
    """
    Client for interacting with HuggingFace models (metadata + model cards).
    """

    def __init__(self, api_token: Optional[str] = None) -> None:
        self.token: Optional[str] = api_token
        self.api = HfApi(token=api_token) if api_token else HfApi()

    def get_model_metadata_dataset(
        self, update_recent: bool = True, limit: int = 5, threads: int = 4
    ) -> pd.DataFrame:
        try:
            logger.info("Loading models from HuggingFace dataset")
            dataset = load_dataset(
                "librarian-bots/model_cards_with_metadata",
                revision="4e7edd391342ee5c182afd08a6f62bff38f44535",
            )["train"].to_pandas()

            logger.info("Loaded %s models from the dataset", len(dataset))

            if update_recent:
                latest_modification = dataset["last_modified"].max()
                recent_models = self.get_recent_models_metadata(limit, latest_modification, threads)
                dataset = pd.concat([dataset, recent_models], ignore_index=True)
                dataset = dataset.drop_duplicates(subset=["modelId"], keep="last")
                dataset = dataset.sort_values("last_modified", ascending=False)

            dataset = self.filter_models(dataset)
            dataset = dataset[: min(limit, len(dataset))]
            return dataset
        except Exception as exc:  # noqa: BLE001
            raise Exception(
                f"Error loading or updating model cards dataset: {exc}"
            ) from exc

    def get_recent_models_metadata(
        self, limit: int, latest_modification: datetime, threads: int = 4
    ) -> pd.DataFrame:
        models = self.api.list_models(limit=limit, sort="lastModified", direction=-1, full=True)

        def process_model(model):
            if model.last_modified <= latest_modification:
                return None
            try:
                card = ModelCard.load(model.modelId, token=self.token) if self.token else ModelCard.load(
                    model.modelId
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Error loading model card for %s: %s", model.id, e)
                return None

            model_info = {
                "modelId": model.id,
                "mlentory_id": HFHelper.generate_mlentory_entity_hash_id("Model", model.id),
                "author": model.author,
                "last_modified": model.last_modified,
                "downloads": model.downloads,
                "likes": model.likes,
                "library_name": model.library_name,
                "tags": model.tags,
                "pipeline_tag": model.pipeline_tag,
                "createdAt": model.created_at,
                "card": card.content if card else "",
                "enriched": True,
                "entity_type": "Model",
                "platform": "HF",
            }
            return model_info if self.has_model_enough_information(model_info) else None

        model_data: List[dict] = []
        with ThreadPoolExecutor(max_workers=threads) as executor:
            future_to_model = {executor.submit(process_model, model): model for model in models}
            for future in as_completed(future_to_model):
                result = future.result()
                if result is not None:
                    model_data.append(result)
        return pd.DataFrame(model_data)

    def get_specific_models_metadata(self, model_ids: List[str], threads: int = 2) -> pd.DataFrame:
        model_data: List[dict] = []

        def process_model(model_id: str):
            models_to_process = self.api.list_models(model_name=model_id, limit=1, full=True)
            results = []
            for model in models_to_process:
                try:
                    card = (
                        ModelCard.load(model.modelId, token=self.token)
                        if self.token
                        else ModelCard.load(model.modelId)
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("Error loading model card for %s: %s", model_id, e)
                    continue

                model_info = {
                    "modelId": model.id,
                    "mlentory_id": HFHelper.generate_mlentory_entity_hash_id("Model", model.id),
                    "author": model.author,
                    "last_modified": model.last_modified,
                    "downloads": model.downloads,
                    "likes": model.likes,
                    "library_name": model.library_name,
                    "tags": model.tags,
                    "pipeline_tag": model.pipeline_tag,
                    "createdAt": model.created_at,
                    "card": card.content if card else "",
                    "enriched": True,
                    "entity_type": "Model",
                    "platform": "HF",
                }
                if self.has_model_enough_information(model_info):
                    results.append(model_info)
            return results

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(process_model, model_id) for model_id in model_ids]
            for future in as_completed(futures):
                results = future.result()
                if results:
                    model_data.extend(results)

        df = pd.DataFrame(model_data)
        if not df.empty:
            df = df.drop_duplicates(subset=["modelId"], keep="last")
        return df

    def filter_models(self, dataset: pd.DataFrame) -> pd.DataFrame:
        filtered_dataset = dataset[dataset.apply(self.has_model_enough_information, axis=1)]
        removed_count = len(dataset) - len(filtered_dataset)
        if removed_count > 0:
            logger.info("Filtered out %s models with insufficient/default card content", removed_count)
        return filtered_dataset

    def has_model_enough_information(self, model_info: Dict) -> bool:
        pipeline_tag = model_info.get("pipeline_tag")
        if isinstance(pipeline_tag, str):
            if pipeline_tag == "" or pipeline_tag is None:
                return False
        else:
            if pipeline_tag is None or getattr(pipeline_tag, "isna", lambda: False)():
                return False

        tags = model_info.get("tags", [])
        if len(tags) == 0:
            return False

        card_text: str = model_info.get("card", "")
        if len(card_text) < 200:
            return False

        default_indicators = [
            "<!-- Provide a quick summary of what the model is/does. -->",
            "This is the model card of a 🤗 transformers model that has been pushed on the Hub. This model card has been automatically generated.",
            "[More Information Needed]",
            "<!-- Address questions around how the model is intended to be used, including the foreseeable users of the model and those affected by the model. -->",
            "<!-- This relates heavily to the Technical Specifications. Content here should link to that section when it is relevant to the training procedure. -->",
            "<!-- This section is meant to convey recommendations with respect to the bias, risk, and technical limitations. -->",
            "<!-- Provide the basic links for the model. -->",
            "## Model Card Contact",
        ]

        def is_default_card(card_text: str) -> bool:
            indicator_count = sum(1 for indicator in default_indicators if indicator in card_text)
            more_info_needed_count = card_text.count("[More Information Needed]")
            return more_info_needed_count >= 38 and indicator_count >= 7

        if is_default_card(card_text):
            return False
        return True


