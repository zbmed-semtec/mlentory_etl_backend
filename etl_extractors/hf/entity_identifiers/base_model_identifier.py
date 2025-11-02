"""
Identifier for base models (models that were fine-tuned to create other models).
"""

from __future__ import annotations
from typing import Set
import pandas as pd
import logging

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class BaseModelIdentifier(EntityIdentifier):
    """
    Extracts base model IDs from HF model metadata.
    
    Looks for:
    - Tags like 'base_model:bert-base-uncased'
    - Model card references to fine-tuning source
    """

    @property
    def entity_type(self) -> str:
        return "base_models"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        base_models = set()
        
        if models_df.empty:
            return base_models
            
        for _, row in models_df.iterrows():
            # Extract from tags
            tags = row.get("tags", [])
            # logger.info(f"Row: {row.get('modelId', '')}")
            # logger.info(f"Tags: {tags}")
            for tag in tags:
                if isinstance(tag, str) and tag.startswith("base_model:"):
                    base_model = tag.split(":")[-1].strip()
                    if base_model:
                        base_models.add(base_model)
            
        logger.info("Identified %d unique base models", len(base_models))
        return base_models

