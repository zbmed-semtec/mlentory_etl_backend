"""
Graph Exploration API Router.

This module defines endpoints for exploring the knowledge graph structure
starting from any entity.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.schemas.entities import EntityBatchRequest, EntityBatchResponse, RelatedEntitiesResponse, EntityURIResponse, RelatedModelsResponse

from api.schemas.graph import GraphResponse, GroupedFacetValuesResponse
from api.services.graph_service import graph_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/graph/entities_by_ids_batch", response_model=EntityBatchResponse)
async def get_entities_batch(request: EntityBatchRequest) -> EntityBatchResponse:
    """
    📦 Batch fetch entity properties by ID.

    Retrieves properties for a list of entity URIs. Useful for bulk data fetching
    in frontend components.

    **Request Body:**
    - `entity_ids`: List of entity URIs (can include angle brackets `<>`)
    - `properties`: Optional list of property names to fetch. If omitted, returns all properties.

    **Response:**
    - `entities`: Map of URI -> {property: [values]}
    - `count`: Number of entities found
    """
    try:
        logger.info(f"Batch fetching {len(request.entity_ids)} entities")
        
        entities_data = graph_service.get_entities_properties_batch(
            entity_ids=request.entity_ids,
            properties=request.properties
        )
        
        return EntityBatchResponse(
            count=len(entities_data),
            entities=entities_data,
            # Dummy cache stats until caching is implemented
            cache_stats={"hits": 0, "misses": len(entities_data), "hit_rate": 0.0}
        )

    except Exception as e:
        logger.error(f"Error in batch entity fetch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/graph/related_entities", response_model=RelatedEntitiesResponse)
async def get_related_entities(
    entity_ids: List[str] = Query(
        ...,
        description="List of entity IDs to fetch related entities for"
    )
) -> RelatedEntitiesResponse:
    """
    🔗 Fetch related entities by entity IDs.

    This endpoint retrieves all properties and relationships for the given entity IDs.
    Plus the neighboring entities for each entity.

    **Parameters:**
    - `entity_ids`: List of entity IDs (can be compact IDs or full URIs)

    **Response:**
    - `related_entities`: Map of URI -> {property/relation: [values]}
    - `count`: Total number of entities found

    **Example:**
    ```
    GET /api/v1/entities/related_by_prefix?entity_ids=model_123&entity_ids=model_456
    ```
    """
    try:
        logger.info(f"Fetching related entities for {len(entity_ids)} entity IDs")
        
        related_data = graph_service.get_related_entities(entity_ids=entity_ids)
        
        return RelatedEntitiesResponse(
            count=len(related_data),
            related_entities=related_data
        )

    except Exception as e:
        logger.error(f"Error in related entities fetch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/graph/grouped_facet_values", response_model=GroupedFacetValuesResponse)
async def grouped_facet_values(entity_type: List = Query(
    ["fair4ml__mlTask", "schema__keywords", "schema__license", "schema__sharedBy", "fair4ml__trainedOn", "fair4ml__testedOn", "fair4ml__validatedOn", "fair4ml__evaluatedOn"], 
    description="Entity type to list"
)) -> GroupedFacetValuesResponse:
    """
    📋 List all entities grouped by relationship type.

    Retrieves a list of entities in the graph filtered by the given relationship
    types to `fair4ml__MLModel` nodes. Entities are grouped by normalized
    relationship keys (e.g., "keywords", "mlTask", "license", "sharedBy", "datasets").

    Args:
        entity_type: A list of relationship types to include. Defaults to
            ["fair4ml__mlTask", "schema__keywords", "schema__license", "fair4ml__sharedBy",
            "fair4ml__trainedOn", "fair4ml__testedOn",
            "fair4ml__validatedOn", "fair4ml__evaluatedOn"].

    Returns:
        GroupedFacetValuesResponse: Contains facets (grouped entities by relationship type)
        and the total count of entities returned.
    """
    try:
        grouped_facet_values, total_count = graph_service.grouped_facet_values(entity_type=entity_type)
        
        return GroupedFacetValuesResponse(
            facets=grouped_facet_values,
            count=total_count
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/graph/{entity_id}", response_model=GraphResponse)
async def get_entity_graph(
    entity_id: str,
    depth: int = Query(1, ge=1, le=3, description="Traversal depth (1-3)"),
    direction: str = Query("both", description="Traversal direction", enum=["outgoing", "incoming", "both"]),
    entity_type: str = Query(
        "MLModel",
        description="Entity type/label for the start node (e.g., 'MLModel', 'License', 'DefinedTerm')",
    ),
    relationships: Optional[List[str]] = Query(
        None,
        description="List of relationship types to follow (e.g., 'HAS_LICENSE', 'CITED_IN')"
    ),
) -> GraphResponse:
    """
    🕸️ Explore the knowledge graph starting from a specific entity.

    This endpoint performs a variable-depth traversal of the graph to retrieve
    a subgraph surrounding the target entity.

    **Parameters:**
    - `entity_id`: The alphanumeric ID fragment of the starting entity (no URI)
    - `depth`: How many hops to traverse (1-3, default 1)
    - `direction`: Direction of relationships to follow (outgoing/incoming/both)
    - `entity_type`: Type/label of the starting entity (MLModel, License, DefinedTerm)
    - `relationships`: Optional filter for specific relationship types

    **Use Cases:**
    - Visualizing the neighborhood of a model
    - Exploring connections between entities
    - Debugging graph structure

    **Example:**
    ```
    GET /api/v1/graph/123abc?depth=2&direction=outgoing
    ```
    """
    try:
        # Decode URI if needed, but FastAPI handles path params well.
        # However, :path in route definition captures slashes, so entity_id is the full URI.
        
        logger.info(
            "Fetching graph for %s (type=%s, depth=%s, dir=%s)",
            entity_id,
            entity_type,
            depth,
            direction,
        )
        
        graph_data = graph_service.get_entity_graph(
            entity_id=entity_id,
            depth=depth,
            relationships=relationships,
            direction=direction,
            entity_label=entity_type,
        )
        
        # logger.info("\n--------------------------------\n")
        # logger.info(f"Graph data: {graph_data}")
        # logger.info("\n--------------------------------\n")
        
        if not graph_data.nodes:
            # Check if it's just because the entity doesn't exist vs having no neighbors
            # The service handles "not found" logic implicitly by returning what it finds
            # If metadata has error, raise it
            if graph_data.metadata.get("error") == "Entity not found":
                raise HTTPException(status_code=404, detail="Entity not found")
                
        return graph_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/graph/entities/get_entity_uri", response_model=EntityURIResponse)
async def find_entity_uri_by_name(
    name: str = Query(..., description="Entity name to search for (exact match, case-insensitive)")
) -> EntityURIResponse:
    """
    🔍 Find entity URI by name.
    
    Searches for an entity by its exact name (case-insensitive) and returns its URI.
    
    **Parameters:**
    - `name`: The entity name to search for
    
    **Response:**
    - `uri`: The entity URI
    - `name`: The entity name
    - `entity_types`: List of entity type labels
    
    **Example:**
        """
    try:
        result = graph_service.find_entity_uri_by_name(entity_name=name)
        
        if not result:
            raise HTTPException(
                status_code=404, 
                detail=f"Entity with name '{name}' not found"
            )
        
        return EntityURIResponse(
            uri=result["uri"],
            name=result.get("name"),
            entity_types=result.get("entity_types", [])
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error finding entity URI by name: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/graph/entities/related_models", response_model=RelatedModelsResponse)
async def get_models_by_entity_uri(
    entity_uri: str = Query(
        ...,
        description="The full entity URI to find related models for "
        "(e.g. 'https://w3id.org/mlentory/mlentory_graph/<entity-id>')",
    )
) -> RelatedModelsResponse:
    """
    📋 Get all models related to an entity.
    
    Retrieves all ML models that are connected to the given entity URI via any relationship.
    
    **Parameters:**
    - `entity_uri`: The entity URI to find related models for
    
    **Response:**
    - `entity_uri`: The queried entity URI
    - `models`: List of related models with properties and relationship types
    - `count`: Total number of related models

    **Example:**
    ```
    GET /api/v1/entities/related_models?entity_uri=https://w3id.org/mlentory/mlentory_graph/fd5b71...
    ```
    """
    try:
        models = graph_service.get_models_by_entity_uri(entity_uri=entity_uri)
        
        return RelatedModelsResponse(
            entity_uri=entity_uri,
            models=models,
            count=len(models)
        )
    
    except Exception as e:
        logger.error(f"Error getting models for entity URI: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")