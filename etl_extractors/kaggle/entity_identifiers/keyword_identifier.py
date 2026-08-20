"""
Identify keyword (tag) references from Kaggle model metadata.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Set

import pandas as pd

from etl_extractors.kaggle.entity_identifiers.base import EntityIdentifier

logger = logging.getLogger(__name__)


class KeywordIdentifier(EntityIdentifier):
    """
    Identify keywords referenced by Kaggle models.

    Kaggle returns curated tag objects on each model, each carrying a stable
    ``ref`` ("nlp", "classification"), a human description, and a
    ``fullPath`` that places it in a taxonomy ("analysis > nlp",
    "task > classification"). The ``ref`` is what identifies the keyword.

    Coverage is sparse - most models carry no tags at all - so keyword
    grouping reaches only a subset of the catalog.
    """

    @property
    def entity_type(self) -> str:
        return "keywords"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """Extract the full set of keyword refs across all models."""
        keywords: Set[str] = set()
        for _, per_model in self.identify_per_model(models_df).items():
            keywords.update(per_model)
        return keywords

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """Extract keyword refs per model."""
        if models_df is None or models_df.empty:
            return {}

        if "modelId" not in models_df.columns:
            logger.warning("Models dataframe has no modelId column")
            return {}

        model_keywords: Dict[str, List[str]] = {}
        for _, row in models_df.iterrows():
            model_id = str(row.get("modelId", "")).strip()
            if not model_id:
                continue

            refs = self.extract_from_tags(row.get("keywords", ""))
            if refs:
                model_keywords[model_id] = refs

        logger.info("Identified keywords for %d models", len(model_keywords))
        return model_keywords

    @staticmethod
    def extract_from_tags(tags: Any) -> List[str]:
        """
        Pull keyword refs out of Kaggle's tag objects.

        Normalized rows store the tag list as a JSON string, so accept both
        that and a real list. Falls back to ``name`` when ``ref`` is absent,
        and tolerates plain strings in case the shape ever changes.

        Args:
            tags: Tag list, or its JSON-string form

        Returns:
            Ordered, de-duplicated list of keyword refs
        """
        if isinstance(tags, str):
            if not tags.strip():
                return []
            try:
                tags = json.loads(tags)
            except (ValueError, TypeError):
                return [tags.strip()]

        if not isinstance(tags, list):
            return []

        refs: List[str] = []
        for tag in tags:
            if isinstance(tag, dict):
                ref = str(tag.get("ref") or tag.get("name") or "").strip()
            elif isinstance(tag, str):
                ref = tag.strip()
            else:
                continue
            if ref and ref not in refs:
                refs.append(ref)
        return refs