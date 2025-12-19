"""
Helper utilities for OpenML extraction and enrichment.
"""

from __future__ import annotations
from pathlib import Path
import logging
import pandas as pd

from etl.utils import generate_mlentory_entity_hash_id

logger = logging.getLogger(__name__)


class OpenMLHelper:
    """
    Helper class containing common utility functions for OpenML data processing.
    """

    @staticmethod
    def generate_mlentory_entity_hash_id(entity_type: str, entity_id: str, platform: str = "OpenML") -> str:
        """
        Generate a consistent hash from entity properties.

        Args:
            entity_type (str): The type of entity (e.g., 'Dataset', 'Model', 'Task')
            entity_id (str): The unique identifier for the entity
            platform (str): The platform name (default: 'OpenML')

        Returns:
            str: A SHA-256 hash of the concatenated properties (mlentory_id)
        """
        return generate_mlentory_entity_hash_id(entity_type=entity_type, entity_id=entity_id, platform=platform)

