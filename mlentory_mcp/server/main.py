from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP


# Create an MCP server instance.
# The name here ("mlentory-mcp") is what MCP clients will see.
mcp = FastMCP("mlentory-mcp")


@mcp.tool()
async def list_models(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
) -> dict:
    """
    List ML models from the MLentory backend.

    This wraps the GET http://localhost:8008/api/v1/models endpoint.
    """

    params: dict[str, object] = {
        "page": page,
        "page_size": page_size,
    }
    if search:
        params["search"] = search

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8008/api/v1/models",
            params=params,
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    # This starts the MCP server over stdin/stdout.
    # Any MCP-compatible client can spawn this process as its tool server.
    mcp.run()



