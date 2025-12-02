"""
Keyword metadata client with CSV cache and Wikipedia/Wikidata enrichment.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd
import requests
import logging
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
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
                    'mlentory_id': HFHelper.generate_mlentory_entity_hash_id("Keyword", keyword),
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

    def _process_single_keyword(self, keyword: str) -> Dict[str, Any]:
        """
        Process a single keyword: check cache or fetch from Wikipedia.
        Used for parallel processing.
        """
        # 1. Check CSV cache first
        if keyword in self.curated_definitions:
            return self.curated_definitions[keyword]
        
        # 2. Fallback to Wikipedia + Wikidata
        keyword_data = self._fetch_from_wikipedia(keyword)
        if keyword_data:
            return keyword_data
        else:
            # No data found, create stub entity
            return {
                'keyword': keyword,
                'mlentory_id': HFHelper.generate_mlentory_entity_hash_id("Keyword", keyword),
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
            }

    def get_keywords_metadata(self, keywords: List[str]) -> pd.DataFrame:
        """
        Retrieve metadata for keywords using CSV cache + Wikipedia/Wikidata fallback.
        Uses parallel processing for API requests.
        
        Args:
            keywords: List of keyword strings
            
        Returns:
            DataFrame with columns: keyword, definition, source, url, aliases, wikidata_qid, extraction_metadata
        """
        all_keyword_data: List[Dict[str, Any]] = []
        
        # Use ThreadPoolExecutor for parallel processing
        # Max workers set to 10 to be polite to Wikipedia API while still getting speedup
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_keyword = {
                executor.submit(self._process_single_keyword, keyword): keyword 
                for keyword in keywords
            }
            
            for future in as_completed(future_to_keyword):
                keyword = future_to_keyword[future]
                try:
                    result = future.result()
                    all_keyword_data.append(result)
                except Exception as e:
                    logger.error("Error processing keyword %s: %s", keyword, e)
                    # Add basic stub on error to keep pipeline moving
                    all_keyword_data.append({
                        'keyword': keyword,
                        'mlentory_id': HFHelper.generate_mlentory_entity_hash_id("Keyword", keyword),
                        'definition': None,
                        'source': 'error',
                        'url': None,
                        'aliases': [],
                        'wikidata_qid': None,
                        'enriched': False,
                        'entity_type': 'Keyword',
                        'platform': 'HF',
                        'extraction_metadata': {
                            'extraction_method': 'Error',
                            'confidence': 0.0,
                            'error': str(e)
                        }
                    })
        
        return pd.DataFrame(all_keyword_data)

    def _search_wikipedia(self, keyword: str) -> Optional[str]:
        """
        Search Wikipedia for keyword with technology/AI context.
        Returns the title of the most relevant page.
        """
        url = "https://en.wikipedia.org/w/api.php"
        # Prioritize technology and AI context
        search_query = f"{keyword} AI"
        
        params = {
            "action": "query",
            "list": "search",
            "srsearch": search_query,
            "format": "json",
            "srlimit": 1
        }
        
        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.get(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                search_results = data.get("query", {}).get("search", [])
                if search_results:
                    return search_results[0]["title"]
        except Exception as e:
            logger.debug("Wikipedia search failed for %s: %s", keyword, e)
            
        return None

    def _fetch_from_wikipedia(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Fetch keyword definition from Wikipedia and enrich with Wikidata."""
        if not self.wiki:
            return None
        
        try:
            # 1. Try to find a more relevant page title using context search
            page_title = self._search_wikipedia(keyword) or keyword
            
            # 2. Fetch the page
            page = self.wiki.page(page_title)
            
            if not page.exists():
                # Fallback to original keyword if the search result (if any) failed/didn't exist
                if page_title != keyword:
                    logger.debug("Context search failed for '%s', falling back to exact match", page_title)
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
                'mlentory_id': HFHelper.generate_mlentory_entity_hash_id("Keyword", keyword),
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

