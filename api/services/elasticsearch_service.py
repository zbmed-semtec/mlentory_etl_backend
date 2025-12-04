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
from typing import Dict, List, Optional, Tuple, Any

from elasticsearch_dsl import Q, Search

from api.config import get_es_client, get_es_config
from api.schemas.responses import ModelListItem, FacetValue, FacetConfig
from api.services.faceted_search import FacetedSearchMixin
from etl_loaders.hf_index_loader import HFModelDocument

logger = logging.getLogger(__name__)


class ElasticsearchService(FacetedSearchMixin):
    """Service for querying ML models in Elasticsearch."""

    def __init__(self):
        """Initialize the Elasticsearch service."""
        self.client = get_es_client()
        self.config = get_es_config()

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

        # Create search object
        search = HFModelDocument.search(using=self.client, index=self.config.hf_models_index)

        # Add search query if provided
        if search_query:
            search = search.query(
                Q("multi_match", query=search_query, fields=["name", "description", "keywords"])
            )

        # Add sorting (by name for consistency)
        search = search.sort("name.raw")

        # Execute search with pagination
        response = search[from_offset:from_offset + page_size].execute()

        # Convert to ModelListItem objects
        models: List[ModelListItem] = []
        for hit in response:
            model = ModelListItem(
                db_identifier=hit.db_identifier,
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
        search = HFModelDocument.search(using=self.client, index=self.config.hf_models_index)
        search = search.query(Q("term", db_identifier=model_id))

        response = search.execute()

        if response.hits.total.value == 0:
            return None

        hit = response[0]
        return ModelListItem(
            db_identifier=hit.db_identifier,
            name=hit.name or "",
            description=hit.description,
            sharedBy=hit.shared_by,  # Note: ES field is snake_case, but schema uses camelCase
            license=hit.license,
            mlTask=hit.ml_tasks or [],  # Note: ES field is snake_case, but schema uses camelCase
            keywords=hit.keywords or [],
            datasets=getattr(hit, "datasets", None) or [],
            platform=hit.platform or "Unknown",
        )




# Global service instance
elasticsearch_service = ElasticsearchService()
