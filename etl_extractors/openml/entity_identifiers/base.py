"""
Base interface for entity identifiers.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Set
import pandas as pd


class EntityIdentifier(ABC):
    """
    Abstract base class for identifying related entities from OpenML run metadata.
    
    Each subclass extracts a specific type of related entity (e.g., datasets, flows, tasks)
    from raw OpenML run metadata.
    """

    @property
    @abstractmethod
    def entity_type(self) -> str:
        """Return the entity type this identifier handles (e.g., 'datasets', 'flows')."""
        pass

    @abstractmethod
    def identify(self, runs_df: pd.DataFrame) -> Set[int]:
        """
        Extract entity IDs from the runs DataFrame.
        
        Args:
            runs_df: DataFrame containing raw OpenML run metadata
            
        Returns:
            Set of entity identifiers (dataset IDs, flow IDs, etc.)
        """
        pass

    def extract_ids_from_column(
        self, df: pd.DataFrame, column_name: str
    ) -> Set[int]:
        """
        Helper to extract unique IDs from a DataFrame column.
        
        Args:
            df: DataFrame containing the data
            column_name: Name of the column containing IDs
            
        Returns:
            Set of unique IDs
        """
        if column_name not in df.columns:
            return set()

        ids = set()
        for _, row in df.iterrows():
            # Handle wrapped metadata format
            value = row.get(column_name)
            if isinstance(value, list) and len(value) > 0:
                # Extract from wrapped metadata: [{"data": id, ...}]
                data = value[0].get("data")
                if data is not None and isinstance(data, (int, float)):
                    ids.add(int(data))
            elif isinstance(value, (int, float)):
                ids.add(int(value))

        return ids


