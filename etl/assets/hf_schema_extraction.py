"""
Dagster assets for Hugging Face LLM schema property extraction.

Extraction-stage assets that preprocess model cards and (later) run LLM extraction.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Tuple

from dagster import AssetIn, asset

from etl_extractors.hf import HFHelper
from etl_extractors.hf.hf_card_preprocessor import preprocess_card_for_llm

logger = logging.getLogger(__name__)

PREPROCESSED_CARDS_FILENAME = "preprocessed_model_cards.json"


def build_preprocessed_model_cards(models_json_path: str | Path) -> Dict[str, str]:
    """
    Load raw HF models JSON and return preprocessed card text per modelId.

    Args:
        models_json_path: Path to ``hf_models_with_ancestors.json`` (or equivalent).

    Returns:
        Mapping of modelId to preprocessed card text for LLM prompts.
    """
    models_df = HFHelper.load_models_dataframe(models_json_path)
    preprocessed: Dict[str, str] = {}

    if models_df.empty:
        logger.warning("No models found in %s", models_json_path)
        return preprocessed

    for _, row in models_df.iterrows():
        model_id = row.get("modelId", "")
        if not model_id:
            continue
        card = row.get("card", "") or ""
        preprocessed[str(model_id)] = preprocess_card_for_llm(str(card))

    logger.info("Preprocessed model cards for %s models", len(preprocessed))
    return preprocessed


@asset(
    group_name="hf_enrichment",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl", "stage": "extract"},
)
def hf_preprocessed_model_cards(models_data: Tuple[str, str]) -> str:
    """
    Preprocess model card markdown for LLM schema extraction.

    Strips code blocks and rebuilds heading + prose text, writing one JSON file
    per run folder.

    Args:
        models_data: Tuple of (models_json_path, run_folder) from
            ``hf_add_ancestor_models``.

    Returns:
        Absolute path to ``preprocessed_model_cards.json`` in the run folder.
    """
    models_json_path, run_folder = models_data
    preprocessed = build_preprocessed_model_cards(models_json_path)

    output_path = Path(run_folder) / PREPROCESSED_CARDS_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(preprocessed, f, indent=2, ensure_ascii=False)

    logger.info("Wrote preprocessed model cards to %s", output_path)
    return str(output_path)
