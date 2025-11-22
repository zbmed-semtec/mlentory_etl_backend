"""
Models API Router.

This module defines the API endpoints for querying ML models from the MLentory
knowledge graph. It provides both lightweight list views (from Elasticsearch)
and detailed single-model views (with Neo4j relationships).

Example Requests:
    # List all models (paginated)
    GET /api/v1/models?page=1&page_size=20
    
    # Search for BERT models
    GET /api/v1/models?search=bert&page_size=50
    
    # Get model with license and dataset info
    GET /api/v1/models/MODEL_URI?include_entities=license&include_entities=datasets
    
    # Get full model details with all relationships
    GET /api/v1/models/MODEL_URI?include_entities=license&include_entities=datasets&include_entities=articles&include_entities=keywords&include_entities=tasks&include_entities=languages
"""

from __future__ import annotations

import logging
from typing import List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.schemas.responses import ModelDetail, ModelListItem, PaginatedResponse, RelatedEntities
from api.services.elasticsearch_service import elasticsearch_service
from api.services.neo4j_service import neo4j_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/models", response_model=PaginatedResponse[ModelListItem])
async def list_models(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    search: Optional[str] = Query(None, description="Search query across name, description, keywords"),
) -> PaginatedResponse[ModelListItem]:
    """
    Get paginated list of ML models from Elasticsearch.

    Supports text search across model names, descriptions, and keywords.
    Results are sorted by name for consistency.
    """
    try:
        models, total_count = elasticsearch_service.search_models(
            search_query=search,
            page=page,
            page_size=page_size,
        )

        # Calculate pagination URLs
        base_url = "/api/v1/models"
        query_params = {}
        if search:
            query_params["search"] = search
        if page_size != 20:
            query_params["page_size"] = page_size

        next_url = None
        if (page * page_size) < total_count:
            next_params = query_params.copy()
            next_params["page"] = page + 1
            next_url = f"{base_url}?{urlencode(next_params)}"

        prev_url = None
        if page > 1:
            prev_params = query_params.copy()
            prev_params["page"] = page - 1
            prev_url = f"{base_url}?{urlencode(prev_params)}"

        return PaginatedResponse[ModelListItem](
            count=total_count,
            next=next_url,
            prev=prev_url,
            results=models,
        )

    except Exception as e:
        logger.error(f"Error listing models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/models/{model_id}", response_model=ModelDetail)
async def get_model_detail(
    model_id: str,
    include_entities: List[str] = Query(
        [],
        description="List of related entities to include from Neo4j",
        examples=["license", "datasets", "articles", "keywords", "tasks", "languages"],
    ),
) -> ModelDetail:
    """
    Get detailed information about a specific ML model.

    Returns basic model info from Elasticsearch plus optional related entities from Neo4j.
    The model_id should be the full URI/identifier of the model.
    """
    try:
        # First get basic model info from Elasticsearch
        model = elasticsearch_service.get_model_by_id(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")

        # If no entities requested, return just the basic model info
        if not include_entities:
            return ModelDetail(
                identifier=[model.db_identifier],  # MLModel expects list of identifiers
                name=model.name,
                description=model.description,
                sharedBy=model.sharedBy,  # Use camelCase field name
                license=model.license,
                mlTask=model.mlTask,  # Use camelCase field name
                keywords=model.keywords,
                platform=model.platform,
                related_entities=RelatedEntities(),  # Empty related entities
            )

        # Get related entities from Neo4j
        related_entities = neo4j_service.get_related_entities(model_id, include_entities)

        return ModelDetail(
            identifier=[model.db_identifier],  # MLModel expects list of identifiers
            name=model.name,
            description=model.description,
            sharedBy=model.sharedBy,  # Use camelCase field name
            license=model.license,
            mlTask=model.mlTask,  # Use camelCase field name
            keywords=model.keywords,
            platform=model.platform,
            related_entities=related_entities,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model detail for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
