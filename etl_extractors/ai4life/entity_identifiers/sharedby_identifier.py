from __future__ import annotations

from typing import Dict, List, Set
import logging

import pandas as pd

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class SharedByIdentifier(EntityIdentifier):
    """Identify sharedBy entities from AI4Life model metadata."""

    @property
    def entity_type(self) -> str:
        return "sharedby"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        values: Set[str] = set()
        if models_df is None or models_df.empty:
            return values

        for _, row in models_df.iterrows():
            sharedby = self._extract_sharedby(row)
            if sharedby:
                values.add(sharedby)

        logger.info("Identified %d unique AI4Life sharedBy entities", len(values))
        return values

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        model_values: Dict[str, List[str]] = {}
        if models_df is None or models_df.empty:
            return model_values

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id") or row.get("model_id") or row.get("name")
            if not model_id:
                continue
            sharedby = self._extract_sharedby(row)
            model_values[str(model_id)] = [sharedby] if sharedby else []

        logger.info("Identified AI4Life sharedBy values for %d models", len(model_values))
        return model_values

    @staticmethod
    def _extract_sharedby(row: pd.Series) -> str:
        value = row.get("sharedBy")
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text.lower() == "none":
            return ""
        return text

