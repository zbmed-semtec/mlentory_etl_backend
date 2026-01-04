"""
Keyword metadata client with CSV cache and Wikidata enrichment with semantic search.
"""

from __future__ import annotations
from typing import List, Dict, Any, Optional
from pathlib import Path
import pandas as pd
import requests
import logging
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import numpy as np

from ..hf_helper import HFHelper



logger = logging.getLogger(__name__)


class HFKeywordClient:
    """
    Enriches keywords with definitions using:
    1. Curated CSV cache (/data/refs/keywords.csv)
    2. Wikidata API with semantic search and type filtering
    
    Prioritizes ML/AI/CS concepts through:
    - Type filtering (P31/P279 claims against relevant Q-IDs)
    - Semantic similarity with context-enriched queries
    
    Performance optimizations:
    - Embedding cache (avoids re-computing embeddings for repeated entities)
    - LRU-cache for Wikidata API calls
    - Parallel processing with ThreadPoolExecutor
    """

    # Relevant Wikidata Q-IDs for ML/AI/CS concepts
    RELEVANT_TYPES = {
        'Q11660',   # artificial intelligence
        'Q2539',    # machine learning
        'Q21198',   # computer science
        'Q7397',    # software
        'Q11344',   # algorithm
        'Q166142',  # programming language
        'Q9143',    # neural network
    }
    
    # Context terms for semantic enrichment
    CONTEXT_TERMS = [
        "machine learning",
        "artificial intelligence",
        "software",
        "deep learning",
        "computer science",
    ]

    def __init__(
        self,
        csv_path: Path | str = "/data/refs/keywords.csv",
        user_agent: str = "MLentory/1.0 (https://github.com/mlentory)",
        similarity_threshold: float = 0.5,
        embedding_cache_size: int = 5000,
    ) -> None:
        self.csv_path = Path(csv_path)
        self.user_agent = user_agent
        self.similarity_threshold = similarity_threshold
        self.curated_definitions: Dict[str, Dict[str, Any]] = {}
        
        # Lazy load sentence transformer
        self._sentence_model = None
        
        # Embedding cache to avoid re-computing embeddings for repeated entities
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self._embedding_cache_size = embedding_cache_size
        
        # Load curated CSV if it exists
        if self.csv_path.exists():
            self._load_curated_csv()
        else:
            logger.warning("Curated keywords CSV not found at %s", self.csv_path)
    
    @property
    def sentence_model(self):
        """Lazy load sentence transformer model."""
        if self._sentence_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Loaded sentence transformer model: all-MiniLM-L6-v2")
            except Exception as e:
                logger.error("Failed to load sentence transformer: %s", e)
                raise
        return self._sentence_model

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

    @lru_cache(maxsize=1000)
    def _wikidata_fetch(self, url: str, params: tuple, user_agent: str) -> Dict[str, Any]:
        """Cached fetch from Wikidata API with User-Agent header."""
        try:
            headers = {"User-Agent": user_agent}
            response = requests.get(url, params=dict(params), headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.debug("Error fetching Wikidata: %s", e)
            return {}
    
    def _wikidata_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search Wikidata for entities matching the query.
        Generates multiple query variations for better coverage.
        """
        if not query:
            return []
        
        # Generate query variations
        query_strings = set(re.split(r" |_|-|\+|\*|\(|\)|\[|\]", query)) - {''}
        query_strings.add(query)
        if ' ' in query:
            query_strings.add(query.replace(' ', ''))
        
        url = 'https://www.wikidata.org/w/api.php'
        base_params = {
            'action': 'wbsearchentities',
            'format': 'json',
            'language': 'en'
        }
        
        search_results = set()
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_query = {
                executor.submit(
                    self._wikidata_fetch, 
                    url, 
                    tuple(sorted(list(base_params.items()) + [('search', qs)])),
                    self.user_agent
                ): qs for qs in query_strings
            }
            
            for future in as_completed(future_to_query):
                res = future.result()
                if res.get('success'):
                    search_results.update({
                        json.dumps({
                            'id': r['id'],
                            'url': r.get('url', ''),
                            'label': r.get('label', ''),
                            'aliases': r.get('aliases', []),
                            'description': r.get('description', ''),
                            'type': ''
                        }) for r in res.get('search', [])
                    })
        
        if not search_results:
            return []
        
        return [json.loads(r) for r in search_results]
    
    def _fetch_entity_details(self, entity_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch detailed entity information including claims (P31, P279).
        Returns dict mapping entity_id -> entity details.
        """
        if not entity_ids:
            return {}
        
        url = 'https://www.wikidata.org/w/api.php'
        entity_details = {}
        
        # Process in batches of 50
        batch_size = 50
        for i in range(0, len(entity_ids), batch_size):
            batch_ids = entity_ids[i:i+batch_size]
            params = {
                'action': 'wbgetentities',
                'ids': '|'.join(batch_ids),
                'format': 'json',
                'languages': 'en'
            }
            
            entities = self._wikidata_fetch(url, tuple(sorted(params.items())), self.user_agent)
            if entities.get('success') and 'entities' in entities:
                for entity_id, entity_data in entities['entities'].items():
                    # Extract instance of (P31) and subclass of (P279) claims
                    type_qids = set()
                    for prop in ['P31', 'P279']:
                        for claim in entity_data.get('claims', {}).get(prop, []):
                            if 'mainsnak' in claim and 'datavalue' in claim['mainsnak']:
                                type_qid = claim['mainsnak']['datavalue']['value'].get('id')
                                if type_qid:
                                    type_qids.add(type_qid)
                    
                    # Get type label (use first P31 if available)
                    type_label = ''
                    first_type_qid = next(iter(type_qids), None)
                    if first_type_qid:
                        type_params = {
                            'action': 'wbgetentities',
                            'ids': first_type_qid,
                            'format': 'json',
                            'languages': 'en'
                        }
                        type_data = self._wikidata_fetch(url, tuple(sorted(type_params.items())), self.user_agent)
                        try:
                            type_label = type_data['entities'][first_type_qid]['labels']['en']['value']
                        except (KeyError, TypeError):
                            type_label = ''
                    
                    entity_details[entity_id] = {
                        'type_qids': type_qids,
                        'type_label': type_label,
                    }
        
        return entity_details
    
    def _filter_by_relevant_types(
        self, 
        candidates: List[Dict[str, Any]], 
        entity_details: Dict[str, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filter candidates to only those with relevant ML/AI/CS types.
        Updates candidates with type information.
        """
        filtered = []
        for candidate in candidates:
            entity_id = candidate['id']
            details = entity_details.get(entity_id, {})
            type_qids = details.get('type_qids', set())
            
            # Check if any type matches our relevant types
            if type_qids & self.RELEVANT_TYPES:
                candidate['type'] = details.get('type_label', '')
                candidate['type_qids'] = list(type_qids)
                filtered.append(candidate)
        
        return filtered
    
    def _get_cached_embedding(self, text: str) -> np.ndarray:
        """
        Get embedding from cache or compute and cache it.
        Uses FIFO eviction when cache exceeds max size.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as numpy array
        """
        if text not in self._embedding_cache:
            # Check cache size and evict oldest entries if needed
            if len(self._embedding_cache) >= self._embedding_cache_size:
                # Remove oldest 20% of entries (simple FIFO eviction)
                num_to_remove = max(1, self._embedding_cache_size // 5)
                for _ in range(num_to_remove):
                    self._embedding_cache.pop(next(iter(self._embedding_cache)))
                logger.debug("Evicted %d embeddings from cache", num_to_remove)
            
            # Compute and cache embedding
            embedding = self.sentence_model.encode([text])[0]
            self._embedding_cache[text] = embedding
            
        return self._embedding_cache[text]
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the embedding cache.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            'cache_size': len(self._embedding_cache),
            'cache_max_size': self._embedding_cache_size,
            'cache_usage_percent': (len(self._embedding_cache) / self._embedding_cache_size * 100) 
                                   if self._embedding_cache_size > 0 else 0,
        }
    
    def _calculate_similarity(self, query: str, candidates: List[Dict[str, Any]]) -> np.ndarray:
        """
        Calculate cosine similarity between query and candidates using sentence transformers.
        Uses embedding cache to avoid re-computing embeddings for repeated entities.
        """
        if not candidates:
            return np.array([])
        
        # Get query embedding (cache it too as it might be reused with different context terms)
        query_embedding = self._get_cached_embedding(query)
        
        # Get candidate embeddings (with caching)
        candidate_embeddings = []
        for candidate in candidates:
            # Combine label, aliases, type, and description
            aliases_str = ', '.join(candidate.get('aliases', []))
            candidate_text = f"{candidate['label']}, {aliases_str}, {candidate.get('type', '')}, {candidate.get('description', '')}".lower()
            candidate_embedding = self._get_cached_embedding(candidate_text)
            candidate_embeddings.append(candidate_embedding)
        
        # Stack embeddings
        candidate_embeddings_matrix = np.vstack(candidate_embeddings)
        
        # Calculate cosine similarity
        from sklearn.metrics.pairwise import cosine_similarity
        similarities = cosine_similarity([query_embedding], candidate_embeddings_matrix).flatten()
        
        return similarities
    
    def _enrich_keyword(self, keyword: str) -> Optional[Dict[str, Any]]:
        """
        Enrich keyword using Wikidata with type filtering and semantic search.
        
        Steps:
        1. Search Wikidata for keyword variations
        2. Filter by relevant types (P31/P279)
        3. Rank by semantic similarity with context-enriched query
        4. Return best match above threshold
        """
        try:
            # Step 1: Search Wikidata
            candidates = self._wikidata_search(keyword)
            if not candidates:
                logger.debug("No Wikidata candidates found for: %s", keyword)
                return None
            
            # Step 2: Fetch entity details and filter by type
            entity_ids = [c['id'] for c in candidates]
            entity_details = self._fetch_entity_details(entity_ids)
            filtered_candidates = self._filter_by_relevant_types(candidates, entity_details)
            
            if not filtered_candidates:
                logger.debug("No relevant ML/AI/CS candidates for: %s", keyword)
                return None
            
            # Step 3: Semantic ranking with context-enriched queries
            best_score = 0.0
            best_match = None
            
            # Try each context term
            for context_term in self.CONTEXT_TERMS:
                context_query = f"{keyword} ({context_term})"
                similarities = self._calculate_similarity(context_query, filtered_candidates)
                
                if len(similarities) > 0:
                    max_idx = np.argmax(similarities)
                    max_score = similarities[max_idx]
                    
                    if max_score > best_score:
                        best_score = max_score
                        best_match = filtered_candidates[max_idx]
            
            # Step 4: Check threshold
            if best_score < self.similarity_threshold:
                logger.debug(
                    "Best match for '%s' below threshold: %.3f < %.3f", 
                    keyword, best_score, self.similarity_threshold
                )
                return None
            
            # Step 5: Construct result
            if best_match:
                return {
                    'keyword': keyword,
                    'mlentory_id': HFHelper.generate_mlentory_entity_hash_id("Keyword", keyword),
                    'definition': best_match.get('description', ''),
                    'source': 'wikidata',
                    'url': best_match.get('url', '').strip('/'),
                    'aliases': best_match.get('aliases', []) + [best_match.get('label', '')],
                    'wikidata_qid': best_match['id'],
                    'enriched': True,
                    'entity_type': 'Keyword',
                    'platform': 'HF',
                    'extraction_metadata': {
                        'extraction_method': 'Wikidata API + Semantic Search',
                        'confidence': float(best_score),
                        'wikidata_type': best_match.get('type', ''),
                        'type_qids': best_match.get('type_qids', []),
                    }
                }
        
        except Exception as e:
            logger.debug("Error enriching keyword %s: %s", keyword, e)
            return None
    
    def _process_single_keyword(self, keyword: str) -> Dict[str, Any]:
        """
        Process a single keyword: check cache or fetch from Wikidata.
        Used for parallel processing.
        """
        # 1. Check CSV cache first
        if keyword in self.curated_definitions:
            return self.curated_definitions[keyword]
        
        # 2. Fallback to Wikidata with semantic search
        keyword_data = self._enrich_keyword(keyword)
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
                    'extraction_method': 'Wikidata API',
                    'confidence': 0.0,
                }
            }

    def get_keywords_metadata(self, keywords: List[str]) -> pd.DataFrame:
        """
        Retrieve metadata for keywords using CSV cache + Wikidata with semantic search.
        Uses parallel processing for API requests.
        
        Uses type filtering (P31/P279) to prioritize ML/AI/CS concepts and semantic
        similarity to disambiguate between candidates.
        
        Args:
            keywords: List of keyword strings
            
        Returns:
            DataFrame with columns: keyword, mlentory_id, definition, source, url, 
            aliases, wikidata_qid, enriched, entity_type, platform, extraction_metadata
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


