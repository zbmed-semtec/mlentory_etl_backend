"""
Identifier for keywords/tags from model metadata.
"""

from __future__ import annotations
from typing import Set, Dict, List
import pandas as pd
import logging

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class KeywordIdentifier(EntityIdentifier):
    """
    Extracts keywords from HF model metadata.
    
    Collects:
    - All tags from models
    - Pipeline tags
    - Library names
    """

    @property
    def entity_type(self) -> str:
        return "keywords"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        keywords = set()

        if models_df.empty:
            return keywords

        for _, row in models_df.iterrows():
            # Collect all tags
            tags = row.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, str) and tag.strip():
                        # Let's descard tags that can be processed as other things
                        unwanted_tag_prefixes = ["dataset:", "arxiv:", "base_model:", "license:"]
                        if any(tag.startswith(prefix) for prefix in unwanted_tag_prefixes):
                            continue

                        if len(tag.split(" ")) > 4:
                            continue

                        keywords.add(tag.strip())

            # Add pipeline_tag
            pipeline_tag = row.get("pipeline_tag")
            if isinstance(pipeline_tag, str) and pipeline_tag.strip():
                keywords.add(pipeline_tag.strip())

            # Add library_name
            library_name = row.get("library_name")
            if isinstance(library_name, str) and library_name.strip():
                keywords.add(library_name.strip())

        logger.info("Identified %d unique keywords", len(keywords))
        return keywords

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract keywords per model.

        Returns:
            Dict mapping model_id to list of keywords associated with that model
        """
        model_keywords: Dict[str, List[str]] = {}

        if models_df.empty:
            return model_keywords

        for _, row in models_df.iterrows():
            model_id = row.get("modelId", "")
            if not model_id:
                continue

            keywords = set()

            # Collect all tags
            tags = row.get("tags", [])
            
            for tag in tags:
                if isinstance(tag, str) and tag.strip():
                    # Let's descard tags that can be processed as other things
                    unwanted_tag_prefixes = ["dataset:", "arxiv:", "base_model:", "license:"]
                    if any(tag.startswith(prefix) for prefix in unwanted_tag_prefixes):
                        continue

                    if len(tag.split(" ")) > 4:
                        continue

                    keywords.add(tag.strip())

            if keywords:
                model_keywords[model_id] = list(keywords)
            else:
                model_keywords[model_id] = []
                

        logger.info("Identified keywords for %d models", len(model_keywords))
        return model_keywords

