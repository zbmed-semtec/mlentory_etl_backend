"""
Keyword metadata client with CSV cache and Wikipedia/Wikidata enrichment.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd
import logging
import json
import wikipediaapi
from wikidata.client import Client as WikidataClient

from ..hf_helper import HFHelper



logger = logging.getLogger(__name__)


class HFKeywordClient:
    """
    Enriches keywords with definitions using:
    1. Curated CSV cache (/data/refs/keywords.csv)
    2. Wikipedia + Wikidata API fallback
    """

    def __init__(
        self,
        csv_path: Path | str = "/data/refs/keywords.csv",
        user_agent: str = "MLentory/1.0 (https://github.com/mlentory)",
    ) -> None:
        self.csv_path = Path(csv_path)
        self.user_agent = user_agent
        self.curated_definitions: Dict[str, Dict[str, Any]] = {}
        
        # Load curated CSV if it exists
        if self.csv_path.exists():
            self._load_curated_csv()
        else:
            logger.warning("Curated keywords CSV not found at %s", self.csv_path)
        
        # Initialize Wikipedia API
        self.wiki = wikipediaapi.Wikipedia(
            language='en',
            user_agent=self.user_agent
        )
        
        # Initialize Wikidata client
        self.wikidata_client = WikidataClient()

    def _load_curated_csv(self) -> None:
        """Load the curated keywords CSV into memory."""
        try:
            df = pd.read_csv(self.csv_path)
            for _, row in df.iterrows():
                keyword = row['keyword']
                # Parse aliases if it's a JSON string
                aliases = row.get('aliases', '[]')
                if isinstance(aliases, str):
                    try:
                        aliases = json.loads(aliases)
                    except json.JSONDecodeError:
                        aliases = []
                
                self.curated_definitions[keyword] = {
                    'keyword': keyword,
                    'mlentory_id': HFHelper.generate_entity_hash("Keyword", keyword),
                    'definition': row['definition'],
                    'aliases': aliases,
                    'source': 'curated_csv',
                    'url': None,
                    'wikidata_qid': None,
                    'enriched': True,
                    'entity_type': 'Keyword',
                    'platform': 'HF',
                    'extraction_metadata': {
                        'extraction_method': 'Curated CSV',
                        'confidence': 1.0,
                    }
                }
            logger.info("Loaded %d curated keywords from CSV", len(self.curated_definitions))
        except Exception as e:  # noqa: BLE001
            logger.error("Error loading curated keywords CSV: %s", e)

    def get_keywords_metadata(self, keywords: List[str]) -> pd.DataFrame:
        """
        Retrieve metadata for keywords using CSV cache + Wikipedia/Wikidata fallback.
        
        Args:
            keywords: List of keyword strings
            
        Returns:
            DataFrame with columns: keyword, definition, source, url, aliases, wikidata_qid, extraction_metadata
        """
        all_keyword_data: List[Dict[str, Any]] = []
        
        for keyword in keywords:
            # 1. Check CSV cache first
            if keyword in self.curated_definitions:
                all_keyword_data.append(self.curated_definitions[keyword])
                continue
            
            # 2. Fallback to Wikipedia + Wikidata
            keyword_data = self._fetch_from_wikipedia(keyword)
            if keyword_data:
                all_keyword_data.append(keyword_data)
            else:
                # No data found, create stub entity
                all_keyword_data.append({
                    'keyword': keyword,
                    'mlentory_id': HFHelper.generate_entity_hash("Keyword", keyword),
                    'definition': None,
                    'source': 'not_found',
                    'url': None,
                    'aliases': [],
                    'wikidata_qid': None,
                    'enriched': False,
                    'entity_type': 'Keyword',
                    'platform': 'HF',
                    'extraction_metadata': {
                        'extraction_method': 'Wikipedia API',
                        'confidence': 1.0,
                    }
                })
        
        return pd.DataFrame(all_keyword_data)

    def _fetch_from_wikipedia(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Fetch keyword definition from Wikipedia and enrich with Wikidata."""
        if not self.wiki:
            return None
        
        try:
            # Search Wikipedia
            page = self.wiki.page(keyword)
            
            if not page.exists():
                logger.debug("Wikipedia page not found for keyword: %s", keyword)
                return None
            
            # Get summary (first 500 chars)
            definition = page.summary[:500] if page.summary else None
            if not definition:
                return None
            
            # Enrich with Wikidata if available
            aliases = []
            wikidata_qid = None
            
            if self.wikidata_client and hasattr(page, 'pageid'):
                try:
                    # Try to get Wikidata entity
                    # Note: This is a simplified approach; production might need more robust lookup
                    wikidata_qid = self._get_wikidata_qid(page.title)
                    if wikidata_qid:
                        entity = self.wikidata_client.get(wikidata_qid, load=True)
                        if hasattr(entity, 'data') and 'aliases' in entity.data:
                            en_aliases = entity.data['aliases'].get('en', [])
                            aliases = [alias['value'] for alias in en_aliases]
                except Exception as e:  # noqa: BLE001
                    logger.debug("Error fetching Wikidata for %s: %s", keyword, e)
            
            return {
                'keyword': keyword,
                'mlentory_id': HFHelper.generate_entity_hash("Keyword", keyword),
                'definition': definition,
                'source': 'wikipedia',
                'url': page.fullurl,
                'aliases': aliases,
                'wikidata_qid': wikidata_qid,
                'enriched': True,
                'entity_type': 'Keyword',
                'platform': 'HF',
                'extraction_metadata': {
                    'extraction_method': 'Wikipedia API' + (' + Wikidata' if wikidata_qid else ''),
                    'confidence': 0.8,
                }
            }
        except Exception as e:  # noqa: BLE001
            logger.debug("Error fetching Wikipedia data for %s: %s", keyword, e)
            return None

    def _get_wikidata_qid(self, wikipedia_title: str) -> Optional[str]:
        """
        Get Wikidata QID from Wikipedia title.
        This is a simplified implementation.
        """
        # In production, you'd use the Wikidata API to lookup by Wikipedia title
        # For now, return None (Wikidata integration is optional)
        return None

