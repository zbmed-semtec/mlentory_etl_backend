# MLentory MCP API - Quick Start Guide

## What Was Created

A new fastMCP-based API that mirrors the model search and retrieval functionality from the existing REST API.

### Files Created

```
mcp_api/
├── __init__.py          # Package initialization
├── server.py            # FastMCP server with tool registration
├── tools.py             # search_models and get_model_detail implementations
├── Dockerfile           # Container configuration
├── README.md            # Full documentation
└── QUICK_START.md       # This file
```

### Files Modified

- `docker-compose.yml` - Added `mcp-api` service

## Quick Start

### 1. Start the MCP API

```bash
# Start with all dependencies
docker-compose --profile api up mcp-api

# Or start everything
docker-compose --profile complete up -d
```

### 2. Verify It's Running

```bash
# Check container status
docker-compose ps mcp-api

# View logs
docker-compose logs -f mcp-api
```

### 3. Test with Claude Desktop

Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mlentory": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "mlentory-mcp-api",
        "python",
        "-m",
        "mcp_api.server"
      ]
    }
  }
}
```

Restart Claude Desktop, and you'll see the MLentory tools available!

## Available Tools

### 1. `search_ml_models`
Search for ML models with text queries and pagination.

**Example prompts:**
- "Search for BERT models in MLentory"
- "Find transformer models"
- "Show me the first 10 image classification models"

### 2. `get_ml_model_detail`
Get detailed information about a specific model.

**Example prompts:**
- "Tell me about the bert-base-uncased model"
- "Get details for model abc123 including its license"
- "What datasets were used to train this model?"

## Architecture

```
Claude Desktop
     |
     | MCP Protocol (stdio via docker exec)
     v
MCP API Container (mcp-api)
     |
     +---> api/services/elasticsearch_service.py
     |          |
     |          v
     |     Elasticsearch Container
     |
     +---> api/services/graph_service.py
                |
                v
           Neo4j Container
```

**Key Points:**
- ✅ Reuses existing `api/services/` code (no duplication)
- ✅ Shares database connections with REST API
- ✅ Runs in separate container for isolation
- ✅ Uses same environment variables as REST API

## Environment Variables

The MCP API uses the same `.env` file as the REST API. Required variables:

```bash
# Elasticsearch
ELASTIC_HOST=mlentory-elasticsearch
ELASTIC_PORT=9201
ELASTIC_SCHEME=http
ELASTIC_USER=elastic
ELASTIC_PASSWORD=changeme
ELASTIC_HF_MODELS_INDEX=hf_models

# Neo4j
NEO4J_URI=bolt://mlentory-neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password
NEO4J_DATABASE=neo4j
```

## Troubleshooting

### Container won't start
```bash
# Rebuild the container
docker-compose build mcp-api

# Check for errors
docker-compose logs mcp-api
```

### Tools not appearing in Claude Desktop
1. Ensure container is running: `docker-compose ps mcp-api`
2. Check configuration file syntax (valid JSON)
3. Restart Claude Desktop completely
4. Check Claude Desktop logs for errors

### "Module not found" errors
```bash
# Rebuild with no cache
docker-compose build --no-cache mcp-api
docker-compose up mcp-api
```

### Empty search results
- Ensure data is loaded via ETL pipeline
- Check Elasticsearch: `curl http://localhost:9201/_cat/indices`
- Check Neo4j: Open browser at http://localhost:7474

## Next Steps

1. **Test the tools** - Try searching for models in Claude Desktop
2. **Explore the code** - See how tools reuse existing services
3. **Add more tools** - Extend with graph exploration, statistics, etc.
4. **Customize** - Adjust tool parameters or add new functionality

## Differences from REST API

| Feature | REST API | MCP API |
|---------|----------|---------|
| Protocol | HTTP/REST | MCP (stdio) |
| Port | 8008 | N/A |
| Client | Any HTTP client | MCP-compatible AI |
| Scope | Full (search, graph, stats, facets) | Minimal (search, detail) |
| Use Case | Web apps | AI assistants |

Both APIs share the same backend services and database connections!

## Resources

- [Full Documentation](./README.md)
- [REST API Documentation](../api/README.md)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP](https://github.com/jlowin/fastmcp)

## Support

For issues or questions:
1. Check the logs: `docker-compose logs mcp-api`
2. Review the [full README](./README.md)
3. Check the [REST API docs](../api/README.md) for service details

