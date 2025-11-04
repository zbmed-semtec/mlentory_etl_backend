"""
Identifier for licenses referenced in model metadata.
"""

from __future__ import annotations
from typing import Set
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