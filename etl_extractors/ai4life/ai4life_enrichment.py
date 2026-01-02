"""
Entity enrichment orchestrator for HF models.

Coordinates the identification and extraction of related entities.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime
import logging
import pandas as pd
from .ai4life_helper import AI4LifeHelper
from .ai4life_extractor import AI4LifeExtractor
from .entity_identifiers.base import EntityIdentifier
from .entity_identifiers.dataset_identifier import DatasetIdentifier 

logger = logging.getLogger(__name__)

class AI4LifeEnrichment:
    """
    Orchestrates the identification and extraction of related entities for AI4Life models.
    
    Workflow:
    1. Load raw AI4Life models JSON
    2. Identify related entities (datasets, keywords, licenses)
    3. Download metadata for each entity type
    4. Persist enriched data to /data/raw/ai4life/<entity_type>/
    """
    def __init__(
        self,
        extractor: Optional[AI4LifeExtractor] = None,
    ) -> None:
        self.extractor = extractor or AI4LifeExtractor()
        
        # Register entity identifiers
        self.identifiers: Dict[str, EntityIdentifier] = {
            "datasets": DatasetIdentifier(),
           }
        
    