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
from etl_extractors.hf.hf_readme_parser import MarkdownParser
from schemas.fair4ml.mlmodel import MLModel

logger = logging.getLogger(__name__)


def _clean_description(description: Optional[str], max_section_length: int = 300) -> Optional[str]:
    """
    Clean and format model description by removing tables/lists and truncating long sections.
    
    Args:
        description: Raw description text (markdown format)
        max_section_length: Maximum length for each section before truncation
        
    Returns:
        Cleaned description text or None if input is None/empty
    """
    if not description or not description.strip():
        return description
    
    try:
        parser = MarkdownParser()
        
        # Remove tables and lists (set max_lines to 0 to remove them entirely)
        cleaned_text = parser.trim_tables_and_lists(description, max_lines=0)
        
        # Extract sections and truncate long ones
        sections = parser.extract_hierarchical_sections(cleaned_text, max_section_length=max_section_length)
        
        # Build final cleaned text from sections
        cleaned_parts = []
        for section in sections:
            content = section.content.strip()
            if content:
                # Truncate if longer than max_section_length
                if len(content) > max_section_length:
                    content = content[:max_section_length].rsplit(' ', 1)[0] + "..."
                cleaned_parts.append(content)
        
        # Join sections with double newline
        result = "\n\n".join(cleaned_parts)
        
        # If cleaning resulted in empty text, return original
        return result if result.strip() else description
        
    except Exception as e:
        logger.warning(f"Error cleaning description: {e}", exc_info=True)
        # Fall back to original description on error
        return description


def search_models(
    query: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    filters: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """
    Search for ML models in the MLentory knowledge graph with faceted navigation.

    This tool searches across model names, descriptions, and keywords using
    Elasticsearch full-text search with advanced faceting capabilities. 
    Results are paginated for efficient retrieval, and descriptions are 
    cleaned to remove tables and overly long sections.

    Args:
        query: Optional text search query. If not provided, returns all models.
               Searches across model name, description, and keywords.
        page: Page number (1-based). Default is 1.
        page_size: Number of results per page (1-100). Default is 20.
        filters: Optional dictionary of filters to apply. Keys are facet names,
                values are lists of filter values to match.
                Available facets: mlTask, license, keywords, platform, sharedBy

    Returns:
        Dictionary containing:
            - models: List of model objects with basic information and cleaned descriptions
            - total: Total number of matching models
            - page: Current page number
            - page_size: Number of results per page
            - has_next: Whether there are more results
            - has_prev: Whether there are previous results
            - facets: Dictionary of facet aggregations with counts
            - filters: Applied filters (echo back)

    Examples:
        >>> # Basic text search
        >>> result = search_models(query="transformer", page=1, page_size=10)
        >>> print(f"Found {result['total']} models")
        >>> 
        >>> # Search with filters
        >>> result = search_models(
        ...     query="bert",
        ...     filters={"mlTask": ["fill-mask"], "license": ["apache-2.0"]}
        ... )
        >>> print(f"Found {result['total']} BERT models for fill-mask with Apache 2.0 license")
        >>> 
        >>> # Filter by platform and shared by
        >>> result = search_models(
        ...     filters={"platform": ["Hugging Face"], "sharedBy": ["google"]}
        ... )
        >>> print(f"Found {result['total']} Google models on Hugging Face")
        >>> 
        >>> # Explore available facet values
        >>> result = search_models(query="nlp")
        >>> print("Available ML tasks:", [f['value'] for f in result['facets']['mlTask']])
        >>> print("Available licenses:", [f['value'] for f in result['facets']['license']])
    """
    try:
        # Validate and constrain parameters
        page = max(1, page)
        page_size = max(1, min(10, page_size))

        # Call the faceted search service
        models, total_count, facet_results = elasticsearch_service.search_models_with_facets(
            query=query or "",
            filters=filters,
            page=page,
            page_size=page_size,
            facets=["mlTask", "license", "keywords", "platform", "sharedBy"],
            facet_size=20,
            facet_query=None,
        )

        # Convert Pydantic models to dictionaries and clean descriptions
        models_list = [
            {
                "db_identifier": model.db_identifier,
                "name": model.name,
                "description": _clean_description(model.description),
                "sharedBy": model.sharedBy,
                "license": model.license,
                "mlTask": model.mlTask,
                "keywords": model.keywords,
                "platform": model.platform,
            }
            for model in models
        ]

        # Convert facet results to dictionaries
        facets_dict = {
            facet_key: [
                {"value": fv.value, "count": fv.count}
                for fv in facet_values
            ]
            for facet_key, facet_values in facet_results.items()
        }

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
            "facets": facets_dict,
            "filters": filters or {},
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
            "facets": {},
            "filters": filters or {},
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

def get_schema_name_definitions(properties: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Return the name and description of MLModel fields based on input properties.

    Args:
        properties: Optional list of property names to include.
                    If None, returns all fields.

    Returns:
        Dictionary mapping field name -> {"name": <field name>, "description": <field description>}
    """
    result: Dict[str, Dict[str, Any]] = {}
    all_schema_properties = MLModel.model_fields.keys()
    try:
        for property in properties:
            if property in all_schema_properties:
                alias = MLModel.model_fields[property].alias
                description = MLModel.model_fields[property].description
                result[property] = {
                    "alias": alias or "",
                    "description": description or "",
                }
        return result
    except Exception as e:
        logger.error(f"Error getting schema name/definitions: {e}", exc_info=True)
        return {"error": str(e)}


def get_related_models_by_entity(
    entity_name: str,
) -> Dict[str, Any]:
    """
    Get the related models by an entity name.
    """
    logger.info(f"get_related_models_by_entity called: entity_name='{entity_name}'")
    try:
        result = graph_service.find_entity_uri_by_name(entity_name=entity_name)
        if not result:
            return {
                "error": f"Entity not found: {entity_name}",
            }
        result = graph_service.get_models_by_entity_uri(entity_uri=result["uri"])
        return {
            "models": result,
            "count": len(result),
        }
    except Exception as e:
        logger.error(f"Error getting related models by entity: {e}", exc_info=True)
        return {
            "error": str(e),
        }