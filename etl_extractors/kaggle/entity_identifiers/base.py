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

    Each subclass extracts a specific type of related entity (e.g., instances,
    keywords) from raw Kaggle model metadata.
    """

    @property
    @abstractmethod
    def entity_type(self) -> str:
        """Return the entity type this identifier handles (e.g., 'instances')."""
        pass

    @abstractmethod
    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """
        Extract entity IDs/names from the models DataFrame.

        Args:
            models_df: DataFrame containing raw Kaggle model metadata

        Returns:
            Set of entity identifiers
        """
        pass

    @abstractmethod
    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract entity IDs/names per model from the models DataFrame.

        Args:
            models_df: DataFrame containing raw Kaggle model metadata

        Returns:
            Dict mapping model_id to list of entity identifiers for that model
        """
        pass

    @staticmethod
    def parse_json_field(value: Any) -> List[str]:
        """
        Helper to read a list field from a normalized row.

        Normalized Kaggle rows store list values as JSON strings, but the same
        column may still hold a real list when read straight from a dataframe,
        so both are accepted.

        Args:
            value: The raw column value

        Returns:
            List of string values
        """
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str) and value.strip():
            import json
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                return [value]
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v]
            return [str(parsed)] if parsed else []
        return []