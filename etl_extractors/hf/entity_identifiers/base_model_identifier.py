"""
Identifier for base models (models that were fine-tuned to create other models).
"""

from __future__ import annotations
from typing import Dict, List, Set
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

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract base model IDs per model.

        Returns:
            Dict mapping model_id to list of base model IDs for that model
        """
        model_base_models: Dict[str, List[str]] = {}
        
        if models_df.empty:
            return model_base_models

        for _, row in models_df.iterrows():
            model_id = row.get("modelId", "")
            if not model_id:
                continue

            base_models = set()
            
            for tag in row.get("tags", []):
                if isinstance(tag, str) and tag.startswith("base_model:"):
                    base_model = tag.split(":")[-1].strip()
                    if base_model:
                        base_models.add(base_model)

            if base_models:
                model_base_models[model_id] = list(base_models)
            else:
                model_base_models[model_id] = []

        logger.info("Identified base models for %d models", len(model_base_models))
        return model_base_models