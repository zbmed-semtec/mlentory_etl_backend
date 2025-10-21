from __future__ import annotations

from typing import Optional, List, Dict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import itertools
import requests
import pandas as pd
from huggingface_hub import HfApi
import logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HFDatasetsClient:
    """
    Client for interacting with HuggingFace datasets (Croissant metadata).
    """

    def __init__(self, api_token: Optional[str] = None) -> None:
        self.token: Optional[str] = api_token
        self.api = HfApi(token=api_token) if api_token else HfApi()

    def get_datasets_metadata(self, limit: int, latest_modification: datetime | None, threads: int = 4) -> pd.DataFrame:
        datasets = list(
            itertools.islice(self.api.list_datasets(sort="lastModified", direction=-1), limit + 1000)
        )

        dataset_data: List[dict] = []
        futures = []

        def process_dataset(dataset):
            if latest_modification is not None:
                last_modified = dataset.last_modified.replace(tzinfo=latest_modification.tzinfo)
                if last_modified <= latest_modification:
                    return None
            croissant_metadata = self.get_croissant_metadata(dataset.id)
            if croissant_metadata == {}:
                return None
            return {
                "datasetId": dataset.id,
                "croissant_metadata": croissant_metadata,
                "extraction_metadata": {
                    "extraction_method": "Downloaded_from_HF_Croissant_endpoint",
                    "confidence": 1.0,
                    "extraction_time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                },
            }

        with ThreadPoolExecutor(max_workers=threads) as executor:
            for ds in datasets:
                future = executor.submit(process_dataset, ds)
                futures.append(future)
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    dataset_data.append(result)
                    if len(dataset_data) >= limit:
                        for f in futures:
                            f.cancel()
                        break

        dataset_data = dataset_data[:limit]
        return pd.DataFrame(dataset_data)

    def get_croissant_metadata(self, dataset_id: str) -> Dict:
        api_url = f"https://huggingface.co/api/datasets/{dataset_id}/croissant"
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = requests.get(api_url, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json()
        return {}

    def get_specific_datasets_metadata(self, dataset_names: List[str], threads: int = 4) -> pd.DataFrame:
        if not dataset_names:
            raise ValueError("dataset_names list cannot be empty")

        dataset_data: List[dict] = []

        def process_dataset(dataset_id: str):
            try:
                croissant_metadata = self.get_croissant_metadata(dataset_id)
                if croissant_metadata == {}:
                    logger.warning("No croissant metadata found for dataset '%s'", dataset_id)
                    return None
                return {
                    "datasetId": dataset_id,
                    "croissant_metadata": croissant_metadata,
                    "extraction_metadata": {
                        "extraction_method": "Downloaded_from_HF_Croissant_endpoint",
                        "confidence": 1.0,
                        "extraction_time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                    },
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("Error processing dataset '%s': %s", dataset_id, e)
                return None

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(process_dataset, dataset_id) for dataset_id in dataset_names]
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    dataset_data.append(result)
        return pd.DataFrame(dataset_data)


