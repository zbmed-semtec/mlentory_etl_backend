"""
Identifier for languages referenced in model metadata.
"""

from __future__ import annotations
from typing import Dict, List, Set
import pandas as pd
import logging

from .base import EntityIdentifier

import pycountry

logger = logging.getLogger(__name__)


class LanguageIdentifier(EntityIdentifier):
    """
    Extracts language identifiers from HF model metadata.
    
    Looks for:
    - Tags like 'en', 'tr'
    """

    @property
    def entity_type(self) -> str:
        return "languages"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        languages = set()
        
        if models_df.empty:
            return languages
            
        for _, row in models_df.iterrows():
            # Extract from tags
            tags = row.get("tags", [])
            for tag in tags:
                if isinstance(tag, str) and is_language_code(tag):
                    languages.add(tag)
            
        logger.info("Identified %d unique languages", len(languages))
        return languages

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Extract language codes per model.

        Returns:
            Dict mapping model_id to list of language codes referenced by that model
        """
        model_languages: Dict[str, List[str]] = {}

        if models_df.empty:
            return model_languages

        for _, row in models_df.iterrows():
            model_id = row.get("modelId", "")
            if not model_id:
                continue

            languages = set()

            tags = row.get("tags", [])
            for tag in tags:
                if isinstance(tag, str) and is_language_code(tag):
                    languages.add(tag)
            
            model_languages[model_id] = list(languages)

        logger.info("Identified languages for %d models", len(model_languages))
        return model_languages

def is_language_code(code: str) -> bool:
    """
    Check if a code is a valid language code.
    
    Args:
        code: Language code to check
        
    Returns:
        True if the code is a valid language code, False otherwise
    """
    return (pycountry.languages.get(alpha_2=code) or
            pycountry.languages.get(alpha_3=code)) is not None