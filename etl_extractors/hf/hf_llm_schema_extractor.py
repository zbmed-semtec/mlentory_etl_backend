"""
Orchestrate LLM-based schema property extraction from Hugging Face model cards.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from etl.config import get_hf_config

from .hf_card_preprocessor import preprocess_card_for_llm
from .hf_llm_prompt_builder import LLMSchemaPromptBuilder
from .hf_llm_response_parser import parse_llm_property_response
from .hf_llm_schema_client import VLLMSchemaClient

logger = logging.getLogger(__name__)

EXTRACTION_METADATA_KEY = "_extraction_metadata"
DEFAULT_CONFIDENCE = 0.85


class HFLLMSchemaExtractor:
    """Extract configured FAIR4ML/INSILICO properties from model card text."""

    def __init__(
        self,
        *,
        metadata_dir: Optional[str] = None,
        client: Optional[VLLMSchemaClient] = None,
        prompt_builder: Optional[LLMSchemaPromptBuilder] = None,
        preprocess_cards: bool = True,
    ) -> None:
        cfg = get_hf_config()
        self.metadata_dir = metadata_dir or cfg.llm_schema_metadata_dir
        self.batch_size = cfg.llm_schema_batch_size
        self.max_tokens = cfg.llm_schema_max_tokens
        self.preprocess_cards = preprocess_cards

        self.prompt_builder = prompt_builder or LLMSchemaPromptBuilder()
        if not self.prompt_builder.property_names:
            self.prompt_builder.load_metadata(self.metadata_dir)

        self.client = client or VLLMSchemaClient.from_env(max_tokens=self.max_tokens)

    def extract_properties(
        self,
        model_cards: Dict[str, str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Extract all configured schema properties for each model card.

        Args:
            model_cards: Mapping of ``modelId`` to raw or preprocessed card text.

        Returns:
            ``{model_id: {property_name: value|None, _extraction_metadata: {...}}}``
        """
        results: Dict[str, Dict[str, Any]] = {}
        model_items = list(model_cards.items())
        total_models = len(model_items)

        for batch_start in range(0, total_models, self.batch_size):
            batch = model_items[batch_start : batch_start + self.batch_size]
            batch_num = batch_start // self.batch_size + 1
            batch_total = (total_models + self.batch_size - 1) // self.batch_size
            logger.info(
                "LLM schema extraction batch %s/%s (%s models)",
                batch_num,
                batch_total,
                len(batch),
            )

            for model_id, card_text in batch:
                results[model_id] = self._extract_model_properties(model_id, card_text)

        return results

    def _extract_model_properties(
        self,
        model_id: str,
        card_text: str,
    ) -> Dict[str, Any]:
        prepared_text = card_text
        if self.preprocess_cards:
            prepared_text = preprocess_card_for_llm(card_text)

        model_result: Dict[str, Any] = {EXTRACTION_METADATA_KEY: {}}

        for property_name in self.prompt_builder.property_names:
            value, meta = self._extract_single_property(
                model_id=model_id,
                property_name=property_name,
                card_text=prepared_text,
            )
            model_result[property_name] = value
            model_result[EXTRACTION_METADATA_KEY][property_name] = meta

        return model_result

    def _extract_single_property(
        self,
        *,
        model_id: str,
        property_name: str,
        card_text: str,
    ) -> tuple[Optional[str], Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "extraction_method": "LLM_schema_extraction",
            "confidence": DEFAULT_CONFIDENCE,
            "source_field": "card",
            "notes": f"model={self.client.model_name}",
        }

        if not card_text.strip():
            meta["notes"] = "empty card after preprocessing"
            return None, meta

        try:
            prompt = self.prompt_builder.build_property_prompt(property_name, card_text)
            raw_response = self.client.chat_completion(prompt.to_chat_messages())
            value = parse_llm_property_response(raw_response)
            meta["llm_response"] = raw_response
            return value, meta
        except Exception as exc:
            logger.error(
                "LLM extraction failed for model=%s property=%s: %s",
                model_id,
                property_name,
                exc,
                exc_info=True,
            )
            meta["notes"] = f"extraction_error: {exc}"
            return None, meta
