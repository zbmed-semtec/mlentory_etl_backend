"""
Identifier for OpenML datasets referenced in run metadata.
"""

from __future__ import annotations
from typing import Set
import pandas as pd
import logging

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class DatasetIdentifier(EntityIdentifier):
    """
    Extracts dataset IDs from OpenML run metadata.
    
    Looks for dataset_id field in run records.
    """

    @property
    def entity_type(self) -> str:
        return "datasets"

    def identify(self, runs_df: pd.DataFrame) -> Set[int]:
        datasets = set()
        
        if runs_df.empty:
            return datasets

        # Extract dataset IDs from the dataset_id column
        datasets = self.extract_ids_from_column(runs_df, "dataset_id")
        
        logger.info("Identified %d unique datasets", len(datasets))
        return datasets


