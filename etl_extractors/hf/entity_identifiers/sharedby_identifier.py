"""Identifier for Hugging Face sharedBy (publisher/owner) entities."""

from __future__ import annotations

from typing import Dict, List, Set
import json
import logging

import pandas as pd

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class SharedByIdentifier(EntityIdentifier):
    """Detect sharedBy names from HF model metadata."""

    @property
    def entity_type(self) -> str:
        return "sharedby"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        entities: Set[str] = set()
        if models_df is None or models_df.empty:
            return entities

        for _, row in models_df.iterrows():
            name = self._extract_name(row)
            if name:
                entities.add(name)

        logger.info("Identified %d unique sharedBy entities", len(entities))
        return entities

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        model_entities: Dict[str, List[str]] = {}
        if models_df is None or models_df.empty:
            return model_entities

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id")
            if not model_id:
                continue
            name = self._extract_name(row)
            model_entities[str(model_id)] = [name] if name else []

        logger.info("Identified sharedBy for %d models", len(model_entities))
        return model_entities

    @staticmethod
    def _extract_name(row: pd.Series) -> str:
        for field in ("author", "sharedBy"):
            value = row.get(field)
            if isinstance(value, str):
                cleaned = value.strip()
                if not cleaned:
                    continue
                # Some pipelines serialize list-like values to JSON strings.
                if cleaned.startswith("[") and cleaned.endswith("]"):
                    try:
                        parsed = json.loads(cleaned)
                        if isinstance(parsed, list) and parsed:
                            first = str(parsed[0]).strip()
                            if first:
                                return first
                    except json.JSONDecodeError:
                        pass
                return cleaned
        return ""

