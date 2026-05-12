"""
Identifier for AI4Life datasets referenced in model metadata.
"""

from __future__ import annotations
from typing import Set, Dict, List
import pandas as pd
import logging

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class DatasetIdentifier(EntityIdentifier):
    """
    Extracts dataset names from AI4Life model metadata.
    """

    @property
    def entity_type(self) -> str:
        return "datasets"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        datasets = set()

        if models_df.empty:
            return datasets

        for _, row in models_df.iterrows():
            dataset_id = row.get("trainedOn", '')
            datasets.update(dataset_id)

        logger.info("Identified %d unique datasets", len(datasets))
        return datasets

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract dataset names per model.

        Returns:
            Dict mapping model_id to list of dataset names referenced by that model
        """
        model_datasets: Dict[str, str] = {}

        if models_df.empty:
            return model_datasets

        for _, row in models_df.iterrows():
            model_id = row.get("modelId", "")
            if not model_id:
                continue

            # Extract from tags
            dataset_id = row.get("trainedOn", [])
            datasets = list()
            datasets.append(dataset_id)
        

            if datasets:
                model_datasets[model_id] = datasets
            else:
                model_datasets[model_id] = []

        logger.info("Identified datasets for %d models", len(model_datasets))
        return model_datasets

