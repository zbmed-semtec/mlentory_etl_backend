"""
Dagster assets for Hugging Face LLM schema property extraction.

Extraction-stage assets that preprocess model cards and (later) run LLM extraction.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from dagster import AssetIn, asset

from etl.config import is_llm_schema_extraction_enabled
from etl_extractors.hf import HFHelper
from etl_extractors.hf.hf_card_preprocessor import preprocess_card_for_llm
from etl_extractors.hf.hf_llm_schema_extractor import HFLLMSchemaExtractor

logger = logging.getLogger(__name__)

PREPROCESSED_CARDS_FILENAME = "preprocessed_model_cards.json"
LLM_SCHEMA_PROPERTIES_FILENAME = "llm_schema_properties.json"


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


def _maybe_limit_models(preprocessed_cards: Dict[str, str]) -> Dict[str, str]:
    """Optional dev cap via ``HF_LLM_SCHEMA_MAX_MODELS``."""
    raw_limit = os.getenv("HF_LLM_SCHEMA_MAX_MODELS", "").strip()
    if not raw_limit:
        return preprocessed_cards
    try:
        limit = max(0, int(raw_limit))
    except ValueError:
        logger.warning("Invalid HF_LLM_SCHEMA_MAX_MODELS=%r; ignoring", raw_limit)
        return preprocessed_cards
    if limit == 0:
        return {}
    return dict(list(preprocessed_cards.items())[:limit])


def run_llm_schema_extraction(preprocessed_cards: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """
    Run LLM schema extraction on preprocessed model card text.

    Cards are already preprocessed; the extractor will not preprocess again.
    """
    cards = _maybe_limit_models(preprocessed_cards)
    if not cards:
        logger.warning("No preprocessed model cards available for LLM extraction")
        return {}

    extractor = HFLLMSchemaExtractor(preprocess_cards=False)
    try:
        return extractor.extract_properties(cards)
    finally:
        extractor.client.close()


@asset(
    group_name="hf_enrichment",
    ins={"preprocessed_cards_path": AssetIn("hf_preprocessed_model_cards")},
    tags={"pipeline": "hf_etl", "stage": "extract"},
)
def hf_llm_schema_properties(preprocessed_cards_path: str) -> str:
    """
    Extract FAIR4ML/INSILICO schema properties from preprocessed model cards via vLLM.

    Writes ``llm_schema_properties.json`` to the same run folder. When disabled via
    config/env, writes an empty object without calling the LLM.

    Args:
        preprocessed_cards_path: Path to ``preprocessed_model_cards.json``.

    Returns:
        Absolute path to ``llm_schema_properties.json``.
    """
    output_path = Path(preprocessed_cards_path).parent / LLM_SCHEMA_PROPERTIES_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not is_llm_schema_extraction_enabled():
        logger.info("LLM schema extraction disabled; writing empty %s", output_path.name)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)
        return str(output_path)

    with open(preprocessed_cards_path, "r", encoding="utf-8") as f:
        preprocessed_cards = json.load(f)
    if not isinstance(preprocessed_cards, dict):
        logger.warning("Expected dict in %s; writing empty results", preprocessed_cards_path)
        preprocessed_cards = {}

    logger.info(
        "Running LLM schema extraction for %s models",
        len(preprocessed_cards),
    )
    results = run_llm_schema_extraction(preprocessed_cards)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info("Wrote LLM schema properties for %s models to %s", len(results), output_path)
    return str(output_path)
