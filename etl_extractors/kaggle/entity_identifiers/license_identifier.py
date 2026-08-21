"""
Identify license references from Kaggle model metadata.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from etl_extractors.kaggle.entity_identifiers.base import EntityIdentifier

logger = logging.getLogger(__name__)


class LicenseIdentifier(EntityIdentifier):
    """
    Extracts license ids/names from model metadata.

    On Kaggle the license belongs to the *instance*, not the model, and one
    model can carry instances under different licenses (e.g. MIT for a PyTorch
    variation and Apache 2.0 for a Keras one). ``models_client`` therefore
    writes a ``licenses`` JSON array alongside the joined ``license`` display
    string; this reads the array where available.

    Splitting the display string on a comma is deliberately avoided - license
    names legitimately contain punctuation, e.g.
    "Attribution-NonCommercial-ShareAlike 3.0 IGO (CC BY-NC-SA 3.0 IGO)".
    """

    @property
    def entity_type(self) -> str:
        return "licenses"

    def _get_license_value(self, row) -> Optional[object]:
        """
        Read licenses off a row, preferring the structured array.

        Falls back to the single ``license`` field (and the British spelling)
        for rows written before ``licenses`` existed.
        """
        for column in ("licenses", "license", "licence"):
            value = row.get(column, None)
            if value is None or value == "":
                continue
            if column == "licenses":
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
        Unique licenses across all models.
        """
        licenses: Set[str] = set()
        if models_df is None or models_df.empty:
            return licenses

        for _, row in models_df.iterrows():
            lic = self._get_license_value(row)
            if lic is None or lic == "":
                continue

            if isinstance(lic, (list, tuple, set)):
                for x in lic:
                    if x:
                        licenses.add(str(x))
            else:
                licenses.add(str(lic))

        logger.info("Identified %d unique licenses", len(licenses))
        return licenses

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        model_id -> [license(s)]
        """
        model_licenses: Dict[str, List[str]] = {}
        if models_df is None or models_df.empty:
            return model_licenses

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id")
            if not model_id:
                continue

            lic = self._get_license_value(row)
            if lic is None or lic == "":
                model_licenses[str(model_id)] = []
                continue

            if isinstance(lic, (list, tuple, set)):
                vals = [str(x) for x in lic if x]
            else:
                vals = [str(lic)]

            model_licenses[str(model_id)] = vals

        logger.info("Identified licenses for %d models", len(model_licenses))
        return model_licenses