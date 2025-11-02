"""
Identifier for licenses referenced in model metadata.
"""

from __future__ import annotations
from typing import Set
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
            
        for _, row in models_df.iterrows():
            # Extract from tags
            tags = row.get("tags", [])
            licenses.update(self.extract_from_tags(tags, "license:"))
            
            # TODO: Future enhancement - parse model card for license info
            
        logger.info("Identified %d unique licenses", len(licenses))
        return licenses

