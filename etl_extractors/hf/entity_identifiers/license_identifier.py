"""
Identifier for licenses referenced in model metadata.
"""

from __future__ import annotations
from typing import Set, Dict, List
import pandas as pd
import logging

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class LicenseIdentifier(EntityIdentifier):
    """
    Extracts license identifiers from HF model metadata.
    
    Looks for:
    - Tags like 'license:mit', 'license:apache-2.0'
    """

    @property
    def entity_type(self) -> str:
        return "licenses"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        licenses = set()

        if models_df.empty:
            return licenses

        # Identify licenses from tags
        for _, row in models_df.iterrows():
            # Extract from tags
            tags = row.get("tags", [])
            licenses.update(self.extract_from_tags(tags, "license:"))

        # Identify licenses from model card

        logger.info("Identified %d unique licenses", len(licenses))
        return licenses

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract license IDs per model.

        Returns:
            Dict mapping model_id to list of license IDs referenced by that model
        """
        model_licenses: Dict[str, List[str]] = {}

        if models_df.empty:
            return model_licenses

        for _, row in models_df.iterrows():
            model_id = row.get("modelId", "")
            if not model_id:
                continue

            # Extract from tags
            tags = row.get("tags", [])
            licenses = list(self.extract_from_tags(tags, "license:"))

            # TODO: Future enhancement - parse model card for license info

            if licenses:
                model_licenses[model_id] = licenses
            else:
                model_licenses[model_id] = []

        logger.info("Identified licenses for %d models", len(model_licenses))
        return model_licenses

