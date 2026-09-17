"""
Identify framework references from Kaggle model metadata.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from etl_extractors.kaggle.entity_identifiers.base import EntityIdentifier

logger = logging.getLogger(__name__)


class FrameworkIdentifier(EntityIdentifier):
    """
    Extracts framework names from model metadata.

    On Kaggle the framework belongs to the *instance*, not the model, and one
    model can carry instances under different frameworks (PyTorch for one
    variation, Keras for another). ``models_client`` therefore writes a
    ``frameworks`` JSON array alongside the joined ``modelArchitecture``
    display string; this reads the array where available.

    The values are frameworks - PyTorch, Keras, TensorFlow2, ScikitLearn -
    not architectures in the ResNet/BERT sense. They describe the file format
    an instance ships in.

    Coverage is near-complete: almost every instance declares a framework,
    unlike tags which are sparse.
    """

    @property
    def entity_type(self) -> str:
        return "frameworks"

    def _get_framework_value(self, row) -> Optional[object]:
        """
        Read frameworks off a row, preferring the structured array.

        Falls back to ``modelArchitecture`` for rows written before
        ``frameworks`` existed.
        """
        for column in ("frameworks", "modelArchitecture"):
            value = row.get(column, None)
            if value is None or value == "":
                continue
            if column == "frameworks":
                parsed = self._parse_json_field(value)
                if parsed:
                    return parsed
                continue
            return value
        return None

    @staticmethod
    def _parse_json_field(value: Any) -> List[str]:
        """Read a list field that may arrive as a JSON string or a real list."""
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                return [value.strip()]
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
            return [str(parsed).strip()] if parsed else []
        return []

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """
        Unique frameworks across all models.
        """
        frameworks: Set[str] = set()
        if models_df is None or models_df.empty:
            return frameworks

        for _, row in models_df.iterrows():
            fw = self._get_framework_value(row)
            if fw is None or fw == "":
                continue

            if isinstance(fw, (list, tuple, set)):
                for x in fw:
                    if x:
                        frameworks.add(str(x))
            else:
                frameworks.add(str(fw))

        logger.info("Identified %d unique frameworks", len(frameworks))
        return frameworks

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        model_id -> [framework(s)]
        """
        model_frameworks: Dict[str, List[str]] = {}
        if models_df is None or models_df.empty:
            return model_frameworks

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id")
            if not model_id:
                continue

            fw = self._get_framework_value(row)
            if fw is None or fw == "":
                model_frameworks[str(model_id)] = []
                continue

            if isinstance(fw, (list, tuple, set)):
                vals = [str(x) for x in fw if x]
            else:
                vals = [str(fw)]

            model_frameworks[str(model_id)] = vals

        logger.info("Identified frameworks for %d models", len(model_frameworks))
        return model_frameworks