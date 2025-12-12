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

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from api.schemas.responses import (
    FacetedSearchResponse,
    FacetValuesResponse,
    ModelDetail,
    ModelListItem,
    PaginatedResponse,
)
from api.services.elasticsearch_service import elasticsearch_service
from api.services.graph_service import graph_service

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


# NOTE: Static routes MUST be defined BEFORE dynamic {model_id} route
# Otherwise FastAPI will match "search", "facets", etc. as model IDs

@router.get("/models/search", response_model=FacetedSearchResponse)
async def search_models_with_facets(
    query: str = Query("", description="Text search query across model fields"),
    filters: str = Query(
        '{}',
        description="JSON string of property filters (e.g., {'license': ['MIT', 'Apache-2.0']})",
        examples=['{"license": ["MIT"], "mlTask": ["text-generation"]}'],
    ),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=1000, description="Results per page (max 1000)"),
    facets: str = Query(
        '["mlTask", "license", "keywords", "datasets", "platform"]',
        description="JSON array of facet field names to aggregate",
        examples=['["mlTask", "license", "keywords", "datasets"]'],
    ),
    facet_size: int = Query(20, ge=1, le=100, description="Maximum values per facet (max 100)"),
    facet_query: str = Query(
        '{}',
        description="JSON object for searching within specific facets (e.g., {'keywords': 'medical'})",
        examples=['{"keywords": "medical", "mlTask": "text"}'],
    ),
) -> FacetedSearchResponse:
    """
    🔍 Search for models with dynamic faceted navigation.

    This endpoint provides flexible faceted search with:
    - **Multi-word text search** across name, description, keywords, tasks
    - **Dynamic facet selection** - choose which facets to aggregate
    - **Multiple filters** - filter by license, tasks, keywords, platform
    - **Facet value search** - search within specific facets
    - **High performance** - optimized Elasticsearch aggregations

    **Example Requests:**

    Simple text search:
    ```
    GET /api/v1/models/search?query=image classification
    ```

    Search with filters:
    ```
    GET /api/v1/models/search?query=bert&filters={"license":["MIT"],"mlTask":["text-classification"]}
    ```

    Custom facets:
    ```
    GET /api/v1/models/search?facets=["license","sharedBy"]&facet_size=50
    ```

    Search within facets:
    ```
    GET /api/v1/models/search?facet_query={"keywords":"medical"}
    ```

    **Response includes:**
    - `models`: Matching models for current page
    - `total`: Total number of matching models
    - `page`, `page_size`: Pagination info
    - `filters`: Applied filters
    - `facets`: Dynamic facet aggregations with counts
    - `facet_config`: Configuration for requested facets
    """
    try:
        # Parse JSON parameters
        filter_dict = json.loads(filters) if filters else {}
        facets_list = json.loads(facets) if facets else ["mlTask", "license", "keywords", "platform"]
        facet_query_dict = json.loads(facet_query) if facet_query else {}

        # Validate inputs
        if not isinstance(filter_dict, dict):
            raise ValueError("Filters must be a JSON object/dictionary")
        if not isinstance(facets_list, list):
            raise ValueError("Facets must be a JSON array/list")
        if not isinstance(facet_query_dict, dict):
            raise ValueError("Facet query must be a JSON object/dictionary")

        for key, values in filter_dict.items():
            if not isinstance(values, list):
                raise ValueError(f"Filter values for '{key}' must be a list")

        # Execute faceted search
        models, total_count, facet_results = elasticsearch_service.search_models_with_facets(
            query=query,
            filters=filter_dict,
            page=page,
            page_size=page_size,
            facets=facets_list,
            facet_size=facet_size,
            facet_query=facet_query_dict,
        )

        # Get facet configuration for requested facets
        all_facet_config = elasticsearch_service.get_facets_config()
        facet_config = {k: v for k, v in all_facet_config.items() if k in facets_list}

        return FacetedSearchResponse(
            models=models,
            total=total_count,
            page=page,
            page_size=page_size,
            filters=filter_dict,
            facets={k: v for k, v in facet_results.items()},
            facet_config=facet_config,
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except json.JSONDecodeError as je:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(je)}")
    except Exception as e:
        logger.error(f"Error in faceted search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@router.get("/models/facets/config")
async def get_facets_configuration():
    """
    📋 Get configuration metadata for all available facets.

    Returns facet configuration that drives dynamic UI rendering:
    - **Field mappings** and data types
    - **Display labels** and icons
    - **Cardinality information** (for performance optimization)
    - **Search capabilities** per facet
    - **Default settings**

    **Use this endpoint to:**
    - Build dynamic filter UI components
    - Understand available facet fields
    - Configure facet search behavior
    - Display appropriate icons and labels

    **Example Response:**
    ```json
    {
      "facet_config": {
        "mlTask": {
          "field": "ml_tasks",
          "label": "ML Tasks",
          "type": "keyword",
          "icon": "mdi-brain",
          "is_high_cardinality": false,
          "default_size": 20,
          "supports_search": true,
          "pinned": true
        },
        "keywords": {
          "field": "keywords",
          "label": "Keywords",
          "type": "keyword",
          "icon": "mdi-tag",
          "is_high_cardinality": true,
          "default_size": 20,
          "supports_search": true,
          "pinned": true
        }
      }
    }
    ```
    """
    try:
        config = elasticsearch_service.get_facets_config()
        return {"facet_config": config}
    except Exception as e:
        logger.error(f"Error retrieving facet configuration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving facet configuration: {str(e)}")


@router.get("/models/facets/values", response_model=FacetValuesResponse)
async def get_facet_values(
    field: str = Query(..., description="Facet field name (e.g., 'keywords', 'mlTask', 'license')"),
    search_query: str = Query("", description="Optional search term to filter facet values"),
    after_key: str = Query("", description="Pagination cursor for getting more values"),
    limit: int = Query(50, ge=1, le=200, description="Maximum values to return (max 200)"),
    filters: str = Query(
        '{}',
        description="JSON string of current filters for context",
        examples=['{"license": ["MIT"], "mlTask": ["text-generation"]}'],
    ),
) -> FacetValuesResponse:
    """
    🔎 Fetch values for a specific facet with search and pagination.

    This endpoint is designed for **high-cardinality facets** and supports:
    - **Facet value search** - Find specific values within a facet using partial matching
    - **Pagination** - Handle large facet value lists efficiently with cursor-based pagination
    - **Contextual filtering** - Facet values reflect current search and filter state
    - **Performance** - Uses Elasticsearch composite aggregations for efficiency

    **Use Cases:**

    1. **Typeahead Search**: Filter facet values as user types
    ```
    GET /api/v1/models/facets/values?field=keywords&search_query=medical
    ```

    2. **Load More**: Paginate through large facet value lists
    ```
    GET /api/v1/models/facets/values?field=keywords&after_key=previous_value&limit=50
    ```

    3. **Contextual Counts**: Show how many models match each facet value given current filters
    ```
    GET /api/v1/models/facets/values?field=keywords&filters={"license":["MIT"]}
    ```

    **Example Response:**
    ```json
    {
      "values": [
        {"value": "medical-imaging", "count": 15},
        {"value": "medical-diagnosis", "count": 12},
        {"value": "medical-research", "count": 8}
      ],
      "after_key": "medical-research",
      "has_more": true
    }
    ```

    **Supported Fields:**
    - `mlTask` - ML tasks
    - `license` - Licenses
    - `keywords` - Keywords/tags
    - `datasets` - Datasets the model was trained/validated on
    - `sharedBy` - Model authors/organizations
    - `platform` - Hosting platforms
    """
    try:
        # Parse filters
        filter_dict = json.loads(filters) if filters else {}
        if not isinstance(filter_dict, dict):
            raise ValueError("Filters must be a JSON object/dictionary")

        # Validate field parameter
        if not field or not field.strip():
            raise ValueError("Field parameter is required")

        # Fetch facet values
        values, next_after_key, has_more = elasticsearch_service.fetch_facet_values(
            field=field,
            search_query=search_query,
            after_key=after_key,
            limit=limit,
            current_filters=filter_dict,
        )

        return FacetValuesResponse(
            values=values,
            after_key=next_after_key,
            has_more=has_more,
        )

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format in filters parameter")
    except Exception as e:
        logger.error(f"Error retrieving facet values: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving facet values: {str(e)}")


# Dynamic route MUST be last - it catches all /models/{anything}
@router.get("/models/{model_id}", response_model=ModelDetail)
async def get_model_detail(
    model_id: str,
    resolve_properties: List[str] = Query(
        [],
        description="List of properties/relationships to resolve as full entities (e.g., 'schema__DefinedTerm', 'schema__author')",
        examples=["schema__license", "schema__author", "fair4ml__trainedOn"],
    ),
) -> ModelDetail:
    """
    Get detailed information about a specific ML model.

    Returns basic model info from Elasticsearch plus optional related entities from Neo4j.
    The model_id can be the full URI or the alphanumeric ID.
    
    To include related entities, specify the relationship types in `resolve_properties` or leave it empty to get all the information.
    """
    try:
        # First get basic model info from Elasticsearch
        
        if not model_id.startswith("https://"):
            model_id = f"https://w3id.org/mlentory/mlentory_graph/{model_id}"
        
        model = elasticsearch_service.get_model_by_id(model_id)
        
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        
        model_response = ModelDetail(
            identifier=model.db_identifier,
            name=model.name,
            description=model.description,
            sharedBy=model.sharedBy,
            license=model.license,
            mlTask=model.mlTask,
            keywords=model.keywords,
            platform=model.platform,
            related_entities={}
        )

        # Get related entities from Neo4j using GraphService
        # We traverse outgoing relationships matching the requested types
        graph_data = graph_service.get_entity_graph(
            entity_id=model_id,
            depth=2,
            relationships=resolve_properties,
            direction="outgoing",
            entity_label="MLModel",
        )

        related_entities: Dict[str, List[Dict[str, Any]]] = {}
        
        # Map nodes by ID for easy lookup
        nodes_map = {n.id: n for n in graph_data.nodes}
        start_uri = graph_data.metadata.get("start_uri")
        
        # Add default properties to the model response
        logger.info("node_map: %s", nodes_map)
        logger.info("start_uri: %s", start_uri)
        logger.info(graph_data.nodes[0].properties)
        logger.info("\n--------------------------------\n")

        # Group neighbor nodes by relationship type
        for edge in graph_data.edges:
            # Only care about edges starting from our model
            if edge.source == start_uri:
                rel_type = edge.type
                target_node = nodes_map.get(edge.target)
                
                if target_node:
                    if rel_type not in related_entities:
                        related_entities[rel_type] = []
                    
                    # Create entity dict from node properties + uri
                    entity_dict = target_node.properties.copy()
                    entity_dict["uri"] = target_node.id
                    
                    # Linking the entities to the corresponding model response property
                    property_name = (rel_type.split("__")[1])
                    
                    if type(model_response.__getattribute__(property_name)) == list:
                        if target_node.id not in model_response.__getattribute__(property_name):
                            model_response.__setattr__(property_name, [*model_response.__getattribute__(property_name), target_node.id])
                    else:
                        model_response.__setattr__(property_name, target_node.id)
                    
                    related_entities[rel_type].append(entity_dict)

        model_response.related_entities = related_entities
        
        
        return model_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting model detail for {model_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
