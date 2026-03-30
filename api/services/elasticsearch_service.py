"""
Elasticsearch Service for ML Model Queries.

Example:
    >>> from api.services.elasticsearch_service import elasticsearch_service
    >>> 
    >>> # Search for models
    >>> models, count = elasticsearch_service.search_models(
    ...     search_query="bert",
    ...     page=1,
    ...     page_size=20
    ... )
    >>> print(f"Found {count} models")
    >>> 
    >>> # Get specific model
    >>> model = elasticsearch_service.get_model_by_id("https://...")
    >>> print(model.name)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Set

from elasticsearch_dsl import Q, Search

from api.config import get_es_client, get_es_config
from api.schemas.responses import ModelListItem, FacetValue, FacetConfig
from api.services.faceted_search import FacetedSearchMixin
from etl_loaders.hf_index_loader import HFModelDocument
from etl_loaders.elasticsearch_store import search

logger = logging.getLogger(__name__)


class ElasticsearchService(FacetedSearchMixin):
    """Service for querying ML models in Elasticsearch."""

    def __init__(self):
        """Initialize the Elasticsearch service."""
        self.client = get_es_client()
        self.config = get_es_config()

    def _source_to_model_item(self, source: Dict[str, Any]) -> ModelListItem:
        """Convert ES source document to ModelListItem."""
        mlentory_id = next(
            (
                identifier
                for identifier in source.get("db_identifier", [])
                if identifier.startswith("https://w3id.org/mlentory/mlentory_graph/")
            ),
            -1,
        )
        return ModelListItem(
            db_identifier=source.get("db_identifier", []),
            mlentory_id=mlentory_id,
            name=source.get("name", ""),
            description=source.get("description"),
            sharedBy=source.get("shared_by"),
            license=source.get("license"),
            mlTask=source.get("ml_tasks", []) or [],
            keywords=source.get("keywords", []) or [],
            datasets=source.get("datasets", []) or [],
            platform=source.get("platform", "Unknown"),
        )

    def search_models(
        self,
        search_query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ModelListItem], int]:
        """
        Search for models in Elasticsearch with pagination.

        Args:
            search_query: Optional text query to search across name, description, keywords
            page: Page number (1-based)
            page_size: Number of results per page (max 100)

        Returns:
            Tuple of (models, total_count)
        """
        # Ensure page_size is within bounds
        page_size = min(max(page_size, 1), 100)

        # Calculate offset
        from_offset = (page - 1) * page_size

        # Create search object using elasticsearch_dsl
        search = Search(using=self.client, index=self.config.hf_models_index)

        # Add search query if provided
        if search_query:
            search = search.query("multi_match", query=search_query, fields=["name", "description", "keywords"])
        else:
            search = search.query("match_all")

        # Apply pagination and execute search
        search = search[from_offset:from_offset + page_size]
        response = search.execute()

        # Convert to ModelListItem objects
        models: List[ModelListItem] = []
        for hit in response:
            mlentory_id = -1
            
            mlentory_id = next(
                (id for id in hit.db_identifier if id.startswith("https://w3id.org/mlentory/mlentory_graph/")),
                -1
            )
                
            model = ModelListItem(
                db_identifier=hit.db_identifier,
                mlentory_id=mlentory_id,
                name=hit.name or "",
                description=hit.description,
                sharedBy=hit.shared_by,  # Note: ES field is snake_case, but schema uses camelCase
                license=hit.license,
                mlTask=hit.ml_tasks or [],  # Note: ES field is snake_case, but schema uses camelCase
                keywords=hit.keywords or [],
                datasets=getattr(hit, "datasets", None) or [],
                platform=hit.platform or "Unknown",
            )
            models.append(model)

        total_count = response.hits.total.value if hasattr(response.hits.total, 'value') else response.hits.total

        logger.debug(f"Elasticsearch search returned {len(models)} models (page {page}, size {page_size})")

        return models, total_count

    def get_model_by_id(self, model_id: str) -> Optional[ModelListItem]:
        """
        Get a single model by its identifier.

        Args:
            model_id: The model identifier/URI

        Returns:
            ModelListItem if found, None otherwise
        """
        # Search for model_id as an element of db_identifier (assuming db_identifier is a list in the ES document)
        # search = HFModelDocument.search(using=self.client, index=self.config.hf_models_index)
        
        search_query = {
                "size": 1,
                "query": {
                    "match": {
                        "db_identifier": model_id
                    }
                }
            }
        response = self.client.search(index=self.config.hf_models_index, body=search_query)
        

        if response["hits"]["total"]["value"] == 0:
            return None

        hit = response["hits"]["hits"][0]["_source"]
        
        mlentory_id = next(
            (id for id in hit["db_identifier"] if id.startswith("https://w3id.org/mlentory/mlentory_graph/")),
            -1
        )
        
        return self._source_to_model_item(hit)

    def find_models_by_exact_field(
        self,
        field_name: str,
        field_value: str,
        exclude_model_uri: Optional[str] = None,
        limit: int = 20,
    ) -> List[ModelListItem]:
        """Find models with an exact field value match."""
        if not field_value:
            return []

        query: Dict[str, Any] = {
            "size": max(1, min(limit, 100)),
            "query": {
                "bool": {
                    "must": [{"term": {field_name: field_value}}],
                    "must_not": [],
                }
            },
        }

        if exclude_model_uri:
            query["query"]["bool"]["must_not"].append({"term": {"db_identifier": exclude_model_uri}})

        try:
            response = self.client.search(index=self.config.hf_models_index, body=query)
            hits = response.get("hits", {}).get("hits", [])
            return [self._source_to_model_item(hit.get("_source", {})) for hit in hits if hit.get("_source")]
        except Exception as e:
            logger.error(f"Error finding models by exact field '{field_name}': {e}", exc_info=True)
            return []

    def find_models_by_overlap_field(
        self,
        field_name: str,
        values: List[str],
        exclude_model_uri: Optional[str] = None,
        limit: int = 20,
    ) -> List[ModelListItem]:
        """Find models sharing one or more values in a multi-valued field."""
        cleaned_values = [v for v in values if v]
        if not cleaned_values:
            return []

        should_clauses = [{"term": {field_name: value}} for value in cleaned_values]
        query: Dict[str, Any] = {
            "size": max(1, min(limit, 100)),
            "query": {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1,
                    "must_not": [],
                }
            },
        }

        if exclude_model_uri:
            query["query"]["bool"]["must_not"].append({"term": {"db_identifier": exclude_model_uri}})

        try:
            response = self.client.search(index=self.config.hf_models_index, body=query)
            hits = response.get("hits", {}).get("hits", [])

            deduped: List[ModelListItem] = []
            seen_uris: Set[str] = set()
            for hit in hits:
                source = hit.get("_source", {})
                model = self._source_to_model_item(source)
                model_uri = next(
                    (identifier for identifier in model.db_identifier if identifier.startswith("https://")),
                    None,
                )
                if model_uri and model_uri in seen_uris:
                    continue
                if model_uri:
                    seen_uris.add(model_uri)
                deduped.append(model)

            return deduped
        except Exception as e:
            logger.error(f"Error finding models by overlap field '{field_name}': {e}", exc_info=True)
            return []




# Global service instance
elasticsearch_service = ElasticsearchService()
