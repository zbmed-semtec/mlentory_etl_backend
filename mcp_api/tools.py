"""
MCP Tools for MLentory Model Search and Retrieval.

This module defines the MCP tools that expose model search and retrieval
functionality to AI assistants through the Model Context Protocol.

Tools:
    - search_models: Search for ML models with text queries and pagination
    - get_model_detail: Get detailed information about a specific model

Example:
    >>> from mcp_api.tools import search_models, get_model_detail
    >>> 
    >>> # Search for models
    >>> result = search_models(query="bert", page=1, page_size=10)
    >>> print(f"Found {result['total']} models")
    >>> 
    >>> # Get model details
    >>> model = get_model_detail(model_id="https://w3id.org/mlentory/model/abc123")
    >>> print(model['name'])
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from api.services.elasticsearch_service import elasticsearch_service
from api.services.graph_service import graph_service

logger = logging.getLogger(__name__)


def search_models(
    query: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """
    Search for ML models in the MLentory knowledge graph.

    This tool searches across model names, descriptions, and keywords using
    Elasticsearch full-text search. Results are paginated for efficient retrieval.

    Args:
        query: Optional text search query. If not provided, returns all models.
               Searches across model name, description, and keywords.
        page: Page number (1-based). Default is 1.
        page_size: Number of results per page (1-100). Default is 20.

    Returns:
        Dictionary containing:
            - models: List of model objects with basic information
            - total: Total number of matching models
            - page: Current page number
            - page_size: Number of results per page
            - has_next: Whether there are more results
            - has_prev: Whether there are previous results

    Example:
        >>> result = search_models(query="transformer", page=1, page_size=10)
        >>> print(f"Found {result['total']} models")
        >>> for model in result['models']:
        ...     print(f"- {model['name']}")
    """
    try:
        # Validate and constrain parameters
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        # Call the existing elasticsearch service
        models, total_count = elasticsearch_service.search_models(
            search_query=query,
            page=page,
            page_size=page_size,
        )

        # Convert Pydantic models to dictionaries
        models_list = [
            {
                "db_identifier": model.db_identifier,
                "name": model.name,
                "description": model.description,
                "sharedBy": model.sharedBy,
                "license": model.license,
                "mlTask": model.mlTask,
                "keywords": model.keywords,
                "platform": model.platform,
            }
            for model in models
        ]

        # Calculate pagination info
        has_next = (page * page_size) < total_count
        has_prev = page > 1

        return {
            "models": models_list,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "has_next": has_next,
            "has_prev": has_prev,
        }

    except Exception as e:
        logger.error(f"Error searching models: {e}", exc_info=True)
        return {
            "error": str(e),
            "models": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "has_next": False,
            "has_prev": False,
        }


def get_model_detail(
    model_id: str,
    resolve_properties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific ML model.

    This tool retrieves comprehensive model information from Elasticsearch and
    optionally fetches related entities from the Neo4j graph database.

    Args:
        model_id: Model identifier (URI or alphanumeric ID).
                 Examples: "https://w3id.org/mlentory/model/abc123" or "abc123"
        resolve_properties: Optional list of relationship types to resolve as full entities.
                          Examples: ["HAS_LICENSE", "author", "dataset"]
                          If not provided, only basic model info is returned.

    Returns:
        Dictionary containing:
            - identifier: List of model URIs
            - name: Model name
            - description: Model description
            - sharedBy: Author/organization
            - license: License identifier
            - mlTask: List of ML tasks
            - keywords: List of keywords/tags
            - platform: Hosting platform
            - related_entities: Dict of related entities (if resolve_properties provided)

    Example:
        >>> # Get basic model info
        >>> model = get_model_detail(model_id="abc123")
        >>> print(f"{model['name']}: {model['description']}")
        >>> 
        >>> # Get model with related entities
        >>> model = get_model_detail(
        ...     model_id="abc123",
        ...     resolve_properties=["HAS_LICENSE", "dataset"]
        ... )
        >>> print(f"License: {model['related_entities']['HAS_LICENSE']}")
    """
    try:
        # Get basic model info from Elasticsearch
        model = elasticsearch_service.get_model_by_id(model_id)
        
        if not model:
            return {
                "error": f"Model not found: {model_id}",
                "identifier": [],
                "name": None,
                "description": None,
            }

        # Build basic response
        model_dict = {
            "identifier": [model.db_identifier],
            "name": model.name,
            "description": model.description,
            "sharedBy": model.sharedBy,
            "license": model.license,
            "mlTask": model.mlTask,
            "keywords": model.keywords,
            "platform": model.platform,
            "related_entities": {},
        }

        # If no properties to resolve, return basic info
        if not resolve_properties:
            return model_dict

        # Get related entities from Neo4j
        try:
            graph_data = graph_service.get_entity_graph(
                entity_id=model_id,
                depth=1,
                relationships=resolve_properties,
                direction="outgoing",
                entity_label="MLModel",
            )

            # Map nodes by ID for easy lookup
            nodes_map = {n.id: n for n in graph_data.nodes}
            start_uri = graph_data.metadata.get("start_uri")

            # Group neighbor nodes by relationship type
            related_entities: Dict[str, List[Dict[str, Any]]] = {}
            
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
                        
                        related_entities[rel_type].append(entity_dict)

            model_dict["related_entities"] = related_entities

        except Exception as graph_error:
            logger.warning(f"Error fetching related entities: {graph_error}")
            # Continue with basic model info even if graph query fails
            model_dict["related_entities"] = {"error": str(graph_error)}

        return model_dict

    except Exception as e:
        logger.error(f"Error getting model detail for {model_id}: {e}", exc_info=True)
        return {
            "error": str(e),
            "identifier": [],
            "name": None,
            "description": None,
        }

