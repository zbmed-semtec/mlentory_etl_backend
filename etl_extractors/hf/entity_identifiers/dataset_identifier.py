"""
Identifier for HF datasets referenced in model metadata.
"""

from __future__ import annotations
from typing import Set
import pandas as pd
import logging

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class DatasetIdentifier(EntityIdentifier):
    """
    Extracts dataset names from HF model metadata.
    
    Looks for:
    - Tags like 'dataset:squad', 'dataset:glue'
    - Model card references (future enhancement)
    """

    @property
    def entity_type(self) -> str:
        return "datasets"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        datasets = set()
        
        if models_df.empty:
            return datasets
            
        for _, row in models_df.iterrows():
            # Extract from tags
            tags = row.get("tags", [])
            datasets.update(self.extract_from_tags(tags, "dataset:"))
            
            # TODO: Future enhancement - parse model card for dataset mentions
            
        logger.info("Identified %d unique datasets", len(datasets))
        return datasets

