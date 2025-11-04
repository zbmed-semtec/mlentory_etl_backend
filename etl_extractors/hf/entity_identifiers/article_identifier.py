"""
Identifier for arXiv articles referenced in model metadata.
"""

from __future__ import annotations
from typing import Set, Dict, List
import pandas as pd
import re
import logging

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class ArticleIdentifier(EntityIdentifier):
    """
    Extracts arXiv paper IDs from HF model metadata.
    
    Looks for:
    - Tags like 'arxiv:2106.09685'
    - arXiv URLs in model cards
    - arXiv IDs in various formats
    """

    # arXiv ID patterns (e.g., 2106.09685, 1706.03762v1)
    ARXIV_PATTERN = re.compile(r'\b(\d{4}\.\d{4,5})(v\d+)?\b')
    
    @property
    def entity_type(self) -> str:
        return "articles"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        articles = set()

        if models_df.empty:
            return articles

        for _, row in models_df.iterrows():
            # Extract from tags
            tags = row.get("tags", [])
            articles.update(self.extract_from_tags(tags, "arxiv:"))

            # Extract from model card text
            card_text = row.get("card", "")
            if isinstance(card_text, str):
                arxiv_matches = self.ARXIV_PATTERN.findall(card_text)
                for match in arxiv_matches:
                    # match is a tuple (id, version)
                    arxiv_id = match[0]
                    articles.add(arxiv_id)

        logger.info("Identified %d unique arXiv articles", len(articles))
        return articles

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract arXiv article IDs per model.

        Returns:
            Dict mapping model_id to list of arXiv IDs referenced by that model
        """
        model_articles: Dict[str, List[str]] = {}

        if models_df.empty:
            return model_articles

        for _, row in models_df.iterrows():
            model_id = row.get("modelId", "")
            if not model_id:
                continue

            articles = set()

            # Extract from tags
            tags = row.get("tags", [])
            articles.update(self.extract_from_tags(tags, "arxiv:"))

            if articles:
                model_articles[model_id] = list(articles)
            else:
                model_articles[model_id] = []

        logger.info("Identified arXiv articles for %d models", len(model_articles))
        return model_articles

