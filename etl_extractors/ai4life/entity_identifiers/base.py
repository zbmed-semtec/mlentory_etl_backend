"""
Base interface for entity identifiers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Set, Dict, Any, List
import pandas as pd


class EntityIdentifier(ABC):
    """
    Abstract base class for identifying related entities from model metadata.
    
    Each subclass extracts a specific type of related entity (e.g., datasets, keywords)
    from raw AI4Life model metadata.
    """

    @property
    @abstractmethod
    def entity_type(self) -> str:
        """Return the entity type this identifier handles (e.g., 'datasets', 'keywords')."""
        pass

    @abstractmethod
    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """
        Extract entity IDs/names from the models DataFrame.

        Args:
            models_df: DataFrame containing raw AI4Life model metadata

        Returns:
            Set of entity identifiers (dataset names, arXiv IDs, etc.)
        """
        pass

    @abstractmethod
    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract entity IDs/names per model from the models DataFrame.

        Args:
            models_df: DataFrame containing raw AI4Life model metadata

        Returns:
            Dict mapping model_id to list of entity identifiers for that model
        """
        pass

    def extract_from_tags(self, tags: list, prefix: str) -> Set[str]:
        """
        Helper to extract values from AI4Life tags with a specific prefix.
        
        Args:
            tags: List of AI4Life tags
            prefix: Tag prefix to match (e.g., 'dataset:', 'arxiv:')
            
        Returns:
            Set of values after the prefix
        """
        entities = set()
        if not isinstance(tags, list):
            return entities
            
        for tag in tags:
            if isinstance(tag, str) and tag.startswith(prefix):
                entity_name = tag.replace(prefix, "").strip()
                if entity_name:
                    entities.add(entity_name)
        return entities

