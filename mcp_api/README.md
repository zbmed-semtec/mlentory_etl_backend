# MLentory MCP API

Model Context Protocol (MCP) interface for the MLentory knowledge graph, enabling AI assistants to search and retrieve ML model metadata.

## Overview

The MLentory MCP API exposes ML model search and retrieval functionality through the Model Context Protocol (MCP), allowing AI assistants like Claude to interact with the MLentory knowledge graph directly.

### What is MCP?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) is an open protocol that standardizes how AI assistants connect to data sources and tools. Instead of traditional REST endpoints, MCP uses a client-server architecture where:

- **Servers** expose tools and resources that AI assistants can use
- **Clients** (AI assistants) discover and invoke these tools
- **Communication** happens via stdio, SSE, or other transports

### Architecture

```
AI Assistant (Claude, etc.)
         |
         | MCP Protocol (stdio)
         v
   MCP API Server
         |
         +---> api/services/elasticsearch_service.py
         |          |
         |          v
         |     Elasticsearch (model search)
         |
         +---> api/services/graph_service.py
                    |
                    v
               Neo4j (relationships)
```

**Key Features:**
- Reuses existing `api/` services to avoid code duplication
- Shares database connections with the REST API
- Runs as a separate Docker container
- Exposes tools for model search and retrieval

## Available Tools

### 1. `search_ml_models`

Search for ML models with text queries and pagination.

**Parameters:**
- `query` (string, optional): Text search across name, description, keywords. Empty string returns all models.
- `page` (integer, default: 1): Page number (1-based)
- `page_size` (integer, default: 20): Results per page (1-100)

**Returns:**
```json
{
  "models": [
    {
      "db_identifier": "https://w3id.org/mlentory/model/abc123",
      "name": "bert-base-uncased",
      "description": "BERT base model, uncased",
      "sharedBy": "google",
      "license": "apache-2.0",
      "mlTask": ["fill-mask", "text-classification"],
      "keywords": ["bert", "transformer", "nlp"],
      "platform": "Hugging Face"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "has_next": true,
  "has_prev": false
}
```

**Example Usage:**
```
Search for transformer models:
  query: "transformer"
  page: 1
  page_size: 10
```

### 2. `get_ml_model_detail`

Get detailed information about a specific ML model.

**Parameters:**
- `model_id` (string, required): Model identifier (URI or alphanumeric ID)
  - Examples: `"https://w3id.org/mlentory/model/abc123"` or `"abc123"`
- `resolve_properties` (list of strings, optional): Relationship types to resolve as full entities
  - Examples: `["schema__license", "schema__author", "fair4ml__relatedDataset"]`

**Returns:**
```json
{
  "identifier": ["https://w3id.org/mlentory/model/abc123"],
  "name": "bert-base-uncased",
  "description": "BERT base model, uncased",
  "sharedBy": "google",
  "license": "apache-2.0",
  "mlTask": ["fill-mask"],
  "keywords": ["bert", "transformer"],
  "platform": "Hugging Face",
  "related_entities": {
    "schema__license": [
      {
        "uri": "https://spdx.org/licenses/Apache-2.0",
        "name": "Apache License 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0"
      }
    ]
  }
}
```

**Example Usage:**
```
Get model details with license information:
  model_id: "bert-base-uncased"
  resolve_properties: ["schema__license"]
```

## Running the MCP API

### Prerequisites

- Docker and Docker Compose
- Elasticsearch and Neo4j running (via `docker-compose`)
- Data loaded via the MLentory ETL pipeline

### Docker Compose (Recommended)

The MCP API is included in the main `docker-compose.yml`:

```bash
# Start MCP API with dependencies
docker compose --profile mcp up

# Or start everything
docker compose --profile complete up

# View logs
docker logs -f mlentory-mcp-api

# Stop services
docker compose --profile mcp down
```

### Standalone (Development)

```bash
# Install dependencies
pip install fastmcp

# Set environment variables (same as REST API)
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your-password
export ELASTIC_HOST=localhost
export ELASTIC_PORT=9201
# ... other environment variables

# Run the server
python -m mcp_api.server
```

### Using ngrok

If you want to make the mcp server public for development proposes you can use ngrok to expose it.

You need to get an API key from ngrok and set it in the NGROK_AUTHTOKEN environment variable.
```bash
export NGROK_AUTHTOKEN=<your-ngrok-api-key>
```

Then you have two options:

1. We use a docker container to run ngrok, you can run it yourself:
```bash
docker pull ngrok/ngrok
docker run --net=host -it -e NGROK_AUTHTOKEN=$NGROK_AUTHTOKEN ngrok/ngrok:latest http --url=believably-graphitic-ann.ngrok-free.dev 80
```

2. You can use the one configured in the docker-compose.yml file:
```bash
docker compose up ngrok
```

## Configuration

The MCP API uses the same environment variables as the REST API:

### Elasticsearch
- `ELASTIC_HOST` - Elasticsearch hostname (default: `mlentory-elasticsearch`)
- `ELASTIC_PORT` - Elasticsearch port (default: `9201`)
- `ELASTIC_SCHEME` - Connection scheme (default: `http`)
- `ELASTIC_USER` - Elasticsearch username (default: `elastic`)
- `ELASTIC_PASSWORD` - Elasticsearch password (default: `changeme`)
- `ELASTIC_HF_MODELS_INDEX` - Index name for models (default: `hf_models`)

### Neo4j
- `NEO4J_URI` - Neo4j connection URI (e.g., `bolt://mlentory-neo4j:7687`)
- `NEO4J_USER` - Neo4j username
- `NEO4J_PASSWORD` - Neo4j password
- `NEO4J_DATABASE` - Neo4j database name (default: `neo4j`)

## Using with AI Assistants

### Claude Desktop

Add to your Claude Desktop configuration (`claude_desktop_config.json`):

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

Then restart Claude Desktop. The MLentory tools will be available in the conversation.

### Connecting to HF chat

You have to specify the MCP link in the HF chat.
For development proposes we use ngrok to expose the MCP API to the internet.

The final link will be something like this:
```
https://<ngrok-subdomain>.ngrok-free.app/mcp
```
You need to specify the full link in the HF chat and add `/mcp` to the end.


## Differences from REST API

| Feature | REST API | MCP API |
|---------|----------|---------|
| **Protocol** | HTTP/REST | MCP (stdio) |
| **Endpoints** | Multiple HTTP endpoints | Tools (functions) |
| **Client** | Any HTTP client | MCP-compatible AI assistants |
| **Use Case** | Web apps, integrations | AI assistant interactions |
| **Features** | Full (search, graph, stats, facets) | Minimal (search, detail) |
| **Port** | 8008 |8009 |

The MCP API is designed for AI assistant interactions, while the REST API is for web applications and integrations. Both share the same underlying services and database connections.

## Development

### Project Structure

```
mcp_api/
├── __init__.py       # Package initialization
├── server.py         # FastMCP server entrypoint
├── tools.py          # Tool implementations
├── Dockerfile        # Container configuration
└── README.md         # This file
```

### Adding New Tools

1. Implement the tool function in `tools.py`:
```python
def my_new_tool(param: str) -> Dict[str, Any]:
    """Tool description."""
    # Implementation using existing services
    return result
```

2. Register the tool in `server.py`:
```python
@mcp.tool()
def my_new_mcp_tool(param: str) -> Dict[str, Any]:
    """Tool description for MCP."""
    return my_new_tool(param)
```

3. Rebuild the container:
```bash
docker compose build mlentory-mcp-api
docker compose up mlentory-mcp-api
```

### Code Reuse

The MCP API reuses services from the `api/` folder:
- `api/services/elasticsearch_service.py` - Model search
- `api/services/graph_service.py` - Graph traversal
- `api/config.py` - Database configuration

This ensures consistency between the REST API and MCP API without code duplication.

## Troubleshooting

### Connection Errors

**Issue**: `Elasticsearch connection failed`
- Ensure Elasticsearch is running: `docker compose ps elasticsearch`
- Check environment variables in `.env`
- View logs: `docker logs elasticsearch`

**Issue**: `Neo4j connection failed`
- Ensure Neo4j is running: `docker compose ps neo4j`
- Check environment variables in `.env`
- View logs: `docker logs neo4j`

### MCP Client Issues

**Issue**: Tools not appearing in Claude Desktop
- Ensure the MCP API container is running
- Check Claude Desktop configuration is correct
- Restart Claude Desktop after configuration changes
- View MCP API logs: `docker logs mcp-api`

**Issue**: "Module not found" errors
- Rebuild the container: `docker build mcp-api`
- Ensure all volumes are mounted correctly in `docker-compose.yml`

### Empty Results

**Issue**: Search returns no models
- Ensure data has been loaded via the ETL pipeline
- Check Elasticsearch index exists: `curl http://localhost:9201/_cat/indices`
- Verify Neo4j has data: Open Neo4j Browser at http://localhost:7474

## Future Enhancements

Potential additions to the MCP API:

- [ ] **Graph exploration tool**: Traverse the knowledge graph from any entity
- [ ] **Faceted search tool**: Advanced filtering with dynamic facets
- [ ] **MCP resources**: Expose models as readable resources

## Related Documentation

- [MLentory REST API](../api/README.md)
- [MLentory ETL Pipeline](../README.md)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)

## License

See the main project [LICENSE](../LICENSE) file.

