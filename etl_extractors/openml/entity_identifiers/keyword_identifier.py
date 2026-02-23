"""
Identifier for keywords/tags from OpenML metadata (runs, flows, datasets).
"""

from __future__ import annotations
from typing import Set, Dict, List
import pandas as pd
import logging

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class KeywordIdentifier(EntityIdentifier):
    """
    Extracts keywords (tags) from OpenML metadata.
    
    Collects:
    - Tags from datasets, flows, and runs
    """

    @property
    def entity_type(self) -> str:
        return "keywords"

    def identify(self, metadata_df: pd.DataFrame) -> Set[str]:
        keywords = set()

        if metadata_df.empty:
            return keywords

        # Helper to extract tags from a row
        # OpenML tags are often lists of strings
        if "tags" in metadata_df.columns:
            for tags in metadata_df["tags"]:
                if isinstance(tags, list):
                    for tag in tags:
                        if isinstance(tag, str) and tag.strip():
                            keywords.add(tag.strip())
                elif isinstance(tags, str) and tags.strip():
                     keywords.add(tags.strip())

        logger.info("Identified %d unique keywords", len(keywords))
        return keywords

