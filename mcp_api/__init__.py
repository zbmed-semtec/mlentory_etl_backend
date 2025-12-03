"""
MCP API - Model Context Protocol Interface for MLentory.

This package provides an MCP server that exposes ML model search and retrieval
functionality through MCP tools, enabling AI assistants to interact with the
MLentory knowledge graph.

Architecture:
    - FastMCP server for tool registration and execution
    - Reuses existing services from api/ to avoid code duplication
    - Shares database connections (Elasticsearch, Neo4j) with REST API

Available Tools:
    - search_models: Search for ML models with pagination
    - get_model_detail: Get detailed information about a specific model

Example:
    # Run the MCP server
    python -m mcp_api.server
"""

__version__ = "1.0.0"

