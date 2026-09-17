"""
Identify model instance references from Kaggle model metadata.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set

import pandas as pd

from etl_extractors.kaggle.entity_identifiers.base import EntityIdentifier

logger = logging.getLogger(__name__)


class InstanceIdentifier(EntityIdentifier):
    """
    Identify model instances referenced by Kaggle models.

    A Kaggle model is a container; its downloadable artifacts are instances,
    one per framework and variation. ``Microsoft/phi-3`` has three
    (pyTorch/mini, pyTorch/moe, keras/vision), each with its own license,
    version, size and URL.

    Instance ids mirror the Kaggle URL path
    (``owner/model/framework/variation``) so they round-trip to a real page.
    """

    @property
    def entity_type(self) -> str:
        return "instances"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """Extract the full set of instance ids across all models."""
        instances: Set[str] = set()
        for _, per_model in self.identify_per_model(models_df).items():
            instances.update(per_model)
        return instances

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """Extract instance ids per model."""
        if models_df is None or models_df.empty:
            return {}

        if "modelId" not in models_df.columns:
            logger.warning("Models dataframe has no modelId column")
            return {}

        model_instances: Dict[str, List[str]] = {}
        for _, row in models_df.iterrows():
            model_id = str(row.get("modelId", "")).strip()
            if not model_id:
                continue

            instance_ids = self.extract_from_urls(
                self.parse_json_field(row.get("instance_urls", ""))
            )
            if instance_ids:
                model_instances[model_id] = instance_ids

        logger.info("Identified instances for %d models", len(model_instances))
        return model_instances

    @staticmethod
    def extract_from_urls(urls: List[str]) -> List[str]:
        """
        Turn Kaggle instance URLs into ``owner/model/framework/variation`` ids.

        Args:
            urls: Full Kaggle instance URLs

        Returns:
            Ordered, de-duplicated list of instance ids
        """
        marker = "/models/"
        instance_ids: List[str] = []
        for url in urls:
            if not isinstance(url, str) or marker not in url:
                continue
            ref = url.split(marker, 1)[1].strip("/")
            if ref and ref not in instance_ids:
                instance_ids.append(ref)
        return instance_ids