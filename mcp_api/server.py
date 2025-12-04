"""
MLentory MCP Server.

FastMCP server that exposes ML model search and retrieval functionality
through the Model Context Protocol (MCP).

This server provides tools for AI assistants to search and retrieve ML model
metadata from the MLentory knowledge graph (Elasticsearch + Neo4j).

Usage:
    # Run the server
    python -m mcp_api.server
    
    # Or with uvx (recommended)
    uvx mcp_api.server

Architecture:
    - FastMCP framework for MCP protocol handling
    - Reuses api/services for database access
    - Shares Elasticsearch and Neo4j connections with REST API
    - Runs as a separate container in Docker Compose

Available Tools:
    - search_models: Search for ML models with text queries and pagination
    - get_model_detail: Get detailed information about a specific model
    - get_related_models_by_entity: Find models related to a given entity
    - get_schema: Retrieve schema property definitions
    - refine_query: Normalize user queries for better search results

Example Client Usage:
    # Using Claude Desktop or other MCP client
    {
      "mcpServers": {
        "mlentory": {
          "command": "docker",
          "args": ["exec", "-i", "mlentory-mcp-api", "python", "-m", "mcp_api.server"]
        }
      }
    }
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP

from mcp_api.tools import (
    get_model_detail,
    search_models,
    get_schema_name_definitions,
    get_related_models_by_entity as get_related_models_by_entity_tool,
    normalize_query
)

from starlette.responses import JSONResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Create FastMCP server
mcp = FastMCP(
    name="MLentory MCP API",
    version="1.0.0",
)


@mcp.tool(description=(
        "Search ML models in the MLentory knowledge graph. Supports text queries, "
        "pagination, and faceted filtering. Returns matching models, available facets, "
        "and pagination metadata. Use when the user needs to search or browse ML models."
    ))
def search_ml_models(
    query: str = "",
    page: int = 1,
    page_size: int = 20,
    filters: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """
    Search for ML models in the MLentory knowledge graph with faceted filtering.

    Searches across model names, descriptions, and keywords using full-text search
    with advanced faceting capabilities.

    Args:
        query: Text search query (searches name, description, keywords). Leave empty for all models.
        page: Page number (1-based, default: 1)
        page_size: Results per page (1-100, default: 20)
        filters: Optional filters to narrow results. Dictionary with facet names as keys
                and lists of values to match. Available facets:
                - mlTask: ML task types (e.g., ["fill-mask", "text-classification"])
                - license: License identifiers (e.g., ["apache-2.0", "mit"])
                - keywords: Model tags/keywords (e.g., ["bert", "transformer"])
                - platform: Hosting platform (e.g., ["Hugging Face"])
                - sharedBy: Author/organization (e.g., ["google", "meta"])

    Returns:
        Dictionary containing:
        - models: List of model objects with cleaned descriptions
        - total: Total number of matching models
        - page: Current page number
        - page_size: Number of results per page
        - has_next: Whether more results are available
        - has_prev: Whether previous results exist
        - facets: Available facet values with counts for further filtering
        - filters: Echo of applied filters

    Examples:
        # Find all transformer models
        search_ml_models(query="transformer", page_size=5)
        
        # Find BERT models for fill-mask task
        search_ml_models(
            query="bert",
            filters={"mlTask": ["fill-mask"]}
        )
        
        # Find Apache 2.0 licensed models from Google
        search_ml_models(
            filters={
                "license": ["apache-2.0"],
                "sharedBy": ["google"]
            }
        )
        
        # Browse all models and explore available facets
        result = search_ml_models(page_size=10)
        # Check result['facets'] to see available filter options
    """
    logger.info(f"search_ml_models called: query='{query}', page={page}, page_size={page_size}, filters={filters}")
    
    # Convert empty string to None for the underlying service
    search_query = query if query else None
    
    result = search_models(
        query=search_query,
        page=page,
        page_size=page_size,
        filters=filters,
    )
    
    logger.info(f"search_ml_models returned {result.get('total', 0)} total models")
    return result


@mcp.tool(description=(
        "Retrieve detailed information about a specific ML model by ID. Supports "
        "optional resolution of related entities such as licenses, datasets, authors, "
        "and publications. Use when the user requests full metadata for a known model."
    ))
def get_ml_model_detail(
    model_id: str,
    resolve_properties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific ML model.

    Retrieves comprehensive model information from Elasticsearch and optionally
    fetches related entities from the Neo4j graph database.

    Args:
        model_id: Model identifier (URI or alphanumeric ID).
                 Can be a full URI like "https://w3id.org/mlentory/model/abc123"
                 or just the ID portion like "abc123"
        resolve_properties: Optional list of relationship types to resolve from Neo4j.
                          Common relationships:
                          - "schema__license": License information
                          - "schema__author": Author details
                          - "fair4ml__trainedOn": Training datasets
                          - "fair4ml__evaluatedOn": Evaluation datasets
                          - "fair4ml__fineTunedFrom": Base model information
                          - "codemeta__referencePublication": Related papers

    Returns:
        Dictionary containing:
        - identifier: Model URI(s)
        - name: Model name
        - description: Model description
        - sharedBy: Author/organization
        - license: License identifier
        - mlTask: List of ML tasks
        - keywords: List of keywords/tags
        - platform: Hosting platform
        - related_entities: Dict of resolved related entities (if resolve_properties provided)

    Examples:
        # Get basic model information
        get_ml_model_detail(model_id="bert-base-uncased")
        
        # Get model with license details
        get_ml_model_detail(
            model_id="bert-base-uncased",
            resolve_properties=["schema__license"]
        )
        
        # Get model with full context (datasets, papers, base model)
        get_ml_model_detail(
            model_id="distilbert-base-uncased",
            resolve_properties=[
                "schema__license",
                "fair4ml__trainedOn",
                "fair4ml__fineTunedFrom",
                "codemeta__referencePublication"
            ]
        )
    """
    logger.info(f"get_ml_model_detail called: model_id='{model_id}', resolve_properties={resolve_properties}")
    
    result = get_model_detail(
        model_id=model_id,
        resolve_properties=resolve_properties,
    )
    
    if "error" in result:
        logger.warning(f"get_ml_model_detail error: {result['error']}")
    else:
        logger.info(f"get_ml_model_detail returned model: {result.get('name')}")
    
    return result

@mcp.tool(description=(
        "Find ML models connected to a specific entity name (e.g., dataset, license, "
        "organization, author, ML task, or keyword). Resolves the entity in the graph "
        "and returns all related models. Use when the user wants models associated with "
        "a dataset, organization, keyword, or other named entity."
    ))
def get_related_models_by_entity(
    entity_name: str,
) -> Dict[str, Any]:
    """
    Get ML models that are related to a given entity name in the MLentory graph.

    Performs a two-step lookup in the Neo4j-backed knowledge graph:
    it first resolves a human-readable entity name (for example, a dataset
    title, license name, or organization) to its canonical graph URI, and then
    retrieves all ML models that are connected to that entity.

    Args:
        entity_name: Human-readable name of the entity to search for.
                     Examples include:
                     - Dataset names (e.g., "GLUE", "MNLI")
                     - Licenses (e.g., "Apache-2.0")
                     - Organizations or authors (e.g., "Google", "Meta AI")
                     - Model names (e.g., "BERT", "GPT-3")
                     - Keywords (e.g., "bert", "transformer")
                     - MLTask (e.g., "fill-mask", "text-classification")

    Returns:
        Dictionary containing either:
        - On success:
            - models: List of related model objects associated with the entity
            - count: Total number of related models found
        - On failure:
            - error: Error message describing what went wrong
                     (for example, when the entity cannot be found)

    Examples:
        # Find models trained on a well-known dataset
        get_related_models_by_entity(entity_name="GLUE")

        # Find models associated with a particular organization
        get_related_models_by_entity(entity_name="Google")

        # Handle entity-not-found cases in a client
        result = get_related_models_by_entity(entity_name="Nonexistent Dataset")
        if "error" in result:
            print(result["error"])
    """
    logger.info(f"get_related_models_by_entity called: entity_uri='{entity_name}'")
    result = get_related_models_by_entity_tool(entity_name=entity_name)

    if "error" in result:
        logger.warning(f"get_related_models_by_entity error: {result['error']}")
    else:
        logger.info(f"get_related_models_by_entity returned {result.get('count', 0)} related models")
    
    return result

@mcp.tool(description=(
        "Retrieve definitions and meanings of MLentory schema properties. Call this "
        "tool when the user asks what a field/property represents OR when you, the LLM, "
        "are unsure about the meaning of a property in a query. Accepts an optional "
        "list of property names, or returns all schema definitions if not specified."
    ))
def get_schema(
    properties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get definitions about schema properties.

    Retrieves detailed definitions and explanations for one or more
    schema properties used in the MLentory knowledge graph.
    
    Args:
        properties: Optional list of schema property names to retrieve.
                    If None, returns all available properties.
    Returns:
        Dictionary containing the definition of one or more schema properties.

    Examples:
        # Get all schema property definitions
        get_schema(["name", "description", "license"])        
    """
    logger.info("get_schema called")

    result = get_schema_name_definitions(
        properties=properties
    )
    
    if "error" in result:
        logger.warning(f"get_schema error: {result['error']}")
    else:
        logger.info("get_schema returned")
    
    return result


@mcp.tool(description=(
        "Normalize and refine a natural-language query into a structured ML model "
        "search query. This tool extracts possible filters (e.g., license, task, "
        "platform), maps ambiguous terms to known properties, and removes noise from "
        "the query. Call this when the user's query is unclear, conversational, "
        "contains unmapped terms, or could benefit from refinement before calling "
        "search_ml_models."
    ))
def refine_query(query: str) -> Dict[str, Any]:
    """
    Refines and normalizes a user query for improved model search.

    Extracts filters (license, task, platform), maps ambiguous terms to properties,
    and removes noise. Use when the query is conversational, ambiguous, or contains
    unmapped terms, before calling search_ml_models.
    
    Args:
        query: Original user query string.
    Returns:
        Dictionary containing:
        - query: Refined query string.
        - filters: Extracted filters for model search.
    
    Examples:
        # Refine a user query
        refine_query("find me an image-classification model under apache-2.0 license on openml")        
    """
    logger.info("refine_query called")
    result = normalize_query(user_query=query)
    if "error" in result:
        logger.warning(f"refine_query error: {result['error']}")
    else:
        logger.info("refine_query returned")

    return result


@mcp.custom_route("/health", methods=["POST"])
async def health_check(request):
    return JSONResponse({"status": "healthy", "service": "mcp-server"})

def main():
    """Run the MCP server."""
    logger.info("Starting MLentory MCP API server...")
    logger.info("Available tools: search_ml_models, get_ml_model_detail")
    
    # Run the FastMCP server
    # This will handle the MCP protocol communication via stdio
    mcp.run(transport="http", host="0.0.0.0", port=8009)


if __name__ == "__main__":
    main()

