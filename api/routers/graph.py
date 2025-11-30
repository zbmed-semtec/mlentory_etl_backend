"""
Graph Exploration API Router.

This module defines endpoints for exploring the knowledge graph structure
starting from any entity.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.schemas.entities import EntityBatchRequest, EntityBatchResponse
from api.schemas.graph import GraphResponse
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
    GET /api/v1/graph/https%3A%2F%2Fw3id.org%2Fmlentory%2Fmodel%2F123?depth=2&direction=outgoing
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
            entity_uri=entity_id,
            depth=depth,
            relationships=relationships,
            direction=direction,
            entity_label=entity_type,
        )
        
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

