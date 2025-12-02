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

from mcp_api.tools import get_model_detail, search_models

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


@mcp.tool()
def search_ml_models(
    query: str = "",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    """
    Search for ML models in the MLentory knowledge graph.

    Searches across model names, descriptions, and keywords using full-text search.
    Results are paginated for efficient retrieval.

    Args:
        query: Text search query (searches name, description, keywords). Leave empty for all models.
        page: Page number (1-based, default: 1)
        page_size: Results per page (1-100, default: 20)

    Returns:
        Dictionary with models list, total count, and pagination info
    """
    logger.info(f"search_ml_models called: query='{query}', page={page}, page_size={page_size}")
    
    # Convert empty string to None for the underlying service
    search_query = query if query else None
    
    result = search_models(
        query=search_query,
        page=page,
        page_size=page_size,
    )
    
    logger.info(f"search_ml_models returned {result.get('total', 0)} total models")
    return result


@mcp.tool()
def get_ml_model_detail(
    model_id: str,
    resolve_properties: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific ML model.

    Retrieves comprehensive model information from Elasticsearch and optionally
    fetches related entities from the Neo4j graph database.

    Args:
        model_id: Model identifier (URI or alphanumeric ID)
        resolve_properties: Optional list of relationship types to resolve
                          (e.g., ["HAS_LICENSE", "author", "dataset"])

    Returns:
        Dictionary with model details and optional related entities
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

@mcp.custom_route("/health", methods=["GET"])
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

