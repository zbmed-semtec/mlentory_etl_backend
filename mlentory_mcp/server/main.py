"""
Simple FastMCP Server that wraps the MLentory FastAPI endpoints.

This uses FastMCP (stdio-based) which is much simpler than HTTP/SSE.
The MCP client will spawn this process and communicate via stdin/stdout.
"""

from typing import Optional
import httpx
from mcp.server.fastmcp import FastMCP

# Create FastMCP server instance
mcp = FastMCP("mlentory-mcp")

# Base URL for your FastAPI application
# Adjust this if your API runs on a different port
API_BASE_URL = "http://localhost:8008"


@mcp.tool()
async def list_models(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> dict:
    """
    List ML models from the MLentory API.
    
    This calls the GET /api/v1/models endpoint from your FastAPI application.
    """
    params = {
        "page": page,
        "page_size": page_size,
    }
    if search:
        params["search"] = search
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/models",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_model_detail(
    model_id: str,
    resolve_properties: Optional[list[str]] = None,
) -> dict:
    """
    Get detailed information about a specific ML model.
    
    This calls the GET /api/v1/models/{model_id} endpoint.
    
    Args:
        model_id: The model identifier (URI or ID)
        resolve_properties: Optional list of relationships to resolve (e.g., ['HAS_LICENSE', 'author'])
    """
    params = {}
    if resolve_properties:
        params["resolve_properties"] = resolve_properties
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/models/{model_id}",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def search_models_with_facets(
    query: str = "",
    filters: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    facets: Optional[str] = None,
    facet_size: int = 20,
) -> dict:
    """
    Search for models with faceted navigation.
    
    This calls the GET /api/v1/models/search endpoint.
    
    Args:
        query: Text search query
        filters: JSON string of filters (e.g., '{"license": ["MIT"]}')
        page: Page number
        page_size: Results per page
        facets: JSON array of facet fields (e.g., '["mlTask", "license"]')
        facet_size: Maximum values per facet
    """
    params = {
        "query": query,
        "page": page,
        "page_size": page_size,
        "facet_size": facet_size,
    }
    if filters:
        params["filters"] = filters
    if facets:
        params["facets"] = facets
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/models/search",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_facets_config() -> dict:
    """
    Get configuration for all available facets.
    
    This calls the GET /api/v1/models/facets/config endpoint.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/models/facets/config",
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_facet_values(
    field: str,
    search_query: str = "",
    limit: int = 50,
    filters: Optional[str] = None,
) -> dict:
    """
    Get values for a specific facet field.
    
    This calls the GET /api/v1/models/facets/values endpoint.
    
    Args:
        field: Facet field name (e.g., 'keywords', 'mlTask', 'license')
        search_query: Optional search term to filter facet values
        limit: Maximum values to return
        filters: JSON string of current filters
    """
    params = {
        "field": field,
        "search_query": search_query,
        "limit": limit,
    }
    if filters:
        params["filters"] = filters
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{API_BASE_URL}/api/v1/models/facets/values",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    print("🚀 MLentory MCP Server (FastMCP) starting...")
    print("📡 Server is ready for client connections via stdio")
    print(f"🔗 Will connect to FastAPI at: {API_BASE_URL}")
    # FastMCP runs over stdin/stdout - the client spawns this process
    mcp.run()



