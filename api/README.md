# MLentory API

FastAPI-based REST API for querying ML model metadata from the MLentory knowledge graph.

## Overview

The MLentory API provides a REST interface to search and retrieve ML model metadata stored in Elasticsearch and Neo4j. It reuses the existing ETL loader configurations and schemas to ensure consistency across the entire MLentory pipeline.

## Architecture

```
api/
├── main.py                    # FastAPI application entrypoint
├── config.py                  # Configuration management (reuses ETL configs)
├── routers/
│   └── models.py             # Model-related endpoints
├── schemas/
│   └── responses.py          # Pydantic response models (extends FAIR4ML schemas)
└── services/
    ├── elasticsearch_service.py  # Elasticsearch query logic
    └── neo4j_service.py          # Neo4j relationship queries
```

### Design Principles

1. **Reuse ETL Components**: All database configurations and helper utilities are imported from `etl_loaders/`
2. **FAIR4ML Compliance**: Response schemas extend the existing FAIR4ML `MLModel` schema from `schemas/fair4ml/`
3. **Separation of Concerns**: Clear separation between routing, business logic, and data access
4. **Type Safety**: Full Pydantic validation for all request/response models

## Components

### Configuration (`config.py`)

Centralizes access to Elasticsearch and Neo4j configurations by reusing the existing ETL loader configs:

```python
from etl_loaders.elasticsearch_store import ElasticsearchConfig, create_elasticsearch_client
from etl_loaders.rdf_store import Neo4jConfig
```

**Key features:**
- Singleton pattern for config instances
- Lazy initialization of database clients
- Environment-based configuration

### Services

#### Elasticsearch Service (`services/elasticsearch_service.py`)

Handles all Elasticsearch queries for model search and retrieval.

**Responsibilities:**
- Paginated model search with text queries
- Single model retrieval by identifier
- Result transformation to API response models

**Key methods:**
- `search_models(search_query, page, page_size)` - Paginated search
- `get_model_by_id(model_id)` - Single model retrieval

#### Neo4j Service (`services/neo4j_service.py`)

Handles all Neo4j queries for fetching related entities.

**Responsibilities:**
- Fetch related entities by type (license, datasets, articles, etc.)
- Transform graph data to entity response models

**Supported entity types:**
- `license` - Model license information
- `datasets` - Related training/test datasets
- `articles` - Scholarly articles about the model
- `keywords` - Keywords/tags
- `tasks` - ML tasks the model performs
- `languages` - Supported natural languages

**Key method:**
- `get_related_entities(model_uri, entities)` - Fetch specified related entities

### Schemas (`schemas/responses.py`)

Pydantic models for API responses that extend FAIR4ML schemas.

**Key models:**
- `PaginatedResponse[T]` - Generic pagination wrapper
- `ModelListItem` - Lightweight model info for list views
- `ModelDetail` - Full model info (extends `MLModel` from `schemas.fair4ml.mlmodel`)
- `RelatedEntities` - Container for related entities from Neo4j
- Entity models: `LicenseEntity`, `DatasetEntity`, `ArticleEntity`, etc.

### Routers (`routers/models.py`)

Defines the API endpoints for model operations.

## API Endpoints

### Core Endpoints

#### `GET /`
Root endpoint with API information.

**Response:**
```json
{
  "name": "MLentory API",
  "version": "1.0.0",
  "description": "API for querying ML model metadata from FAIR4ML knowledge graph",
  "docs": "/docs",
  "health": "/health"
}
```

#### `GET /health`
Health check endpoint that tests connections to Elasticsearch and Neo4j.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "elasticsearch": true,
  "neo4j": true
}
```

### Model Endpoints

#### `GET /api/v1/models`
List models with pagination and search.

**Query Parameters:**
- `page` (int, default: 1) - Page number (1-based)
- `page_size` (int, default: 20, max: 100) - Items per page
- `search` (string, optional) - Text search across name, description, keywords

**Example Request:**
```bash
GET /api/v1/models?page=1&page_size=20&search=bert
```

**Response:**
```json
{
  "count": 150,
  "next": "/api/v1/models?page=2&page_size=20&search=bert",
  "prev": null,
  "results": [
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
  ]
}
```

#### `GET /api/v1/models/{model_id}`
Get detailed model information with optional related entities.

**Path Parameters:**
- `model_id` (string) - Model URI/identifier

**Query Parameters:**
- `include_entities` (list[string], optional) - Related entities to include
  - Valid values: `license`, `datasets`, `articles`, `keywords`, `tasks`, `languages`

**Example Request:**
```bash
GET /api/v1/models/https%3A%2F%2Fw3id.org%2Fmlentory%2Fmodel%2Fabc123?include_entities=license&include_entities=datasets
```

**Response:**
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
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "Google Research",
  "dateCreated": "2018-11-03T00:00:00Z",
  "related_entities": {
    "license": {
      "uri": "https://spdx.org/licenses/Apache-2.0",
      "name": "Apache License 2.0",
      "url": "https://www.apache.org/licenses/LICENSE-2.0"
    },
    "datasets": [
      {
        "uri": "https://w3id.org/mlentory/dataset/xyz789",
        "name": "Wikipedia + BookCorpus",
        "description": "Training data for BERT",
        "url": null
      }
    ],
    "articles": [],
    "keywords": [],
    "tasks": [],
    "languages": []
  }
}
```

## Configuration

The API uses environment variables for configuration, reusing the same variables as the ETL pipeline:

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

## Running the API

### Development (Standalone)

```bash
# Install dependencies
poetry install

# Set environment variables
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your-password
# ... other environment variables

# Run the API
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Compose (Recommended)

The API is included in the main `docker-compose.yml`:

```bash
# Start all services (Neo4j, Elasticsearch, API)
docker-compose up --profile=api -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Common errors:

```bash
------
 > [api internal] load build context:
------
failed to solve: error from sender: open /mnt/mlentory_volume/mlentory_etl_backend/config/neo4j/import: permission denied
```

You need to change the permissions of the directory `config/neo4j/import` to be writable by the user running the container.
```bash
sudo chmod -R 777 config/neo4j/import
```


The API will be available at:
- **API**: http://localhost:8000
- **Interactive docs**: http://localhost:8000/docs
- **Alternative docs**: http://localhost:8000/redoc

## Example Usage

### Using cURL

```bash
# List first page of models
curl http://localhost:8000/api/v1/models

# Search for models
curl "http://localhost:8000/api/v1/models?search=transformer&page=1&page_size=10"

# Get model details with related entities
curl "http://localhost:8000/api/v1/models/MODEL_URI?include_entities=license&include_entities=datasets"

# Health check
curl http://localhost:8000/health
```

### Using Python

```python
import requests

# List models
response = requests.get("http://localhost:8000/api/v1/models", params={
    "page": 1,
    "page_size": 20,
    "search": "bert"
})
data = response.json()
print(f"Found {data['count']} models")

# Get model details
model_id = "https://w3id.org/mlentory/model/abc123"
response = requests.get(
    f"http://localhost:8000/api/v1/models/{model_id}",
    params={"include_entities": ["license", "datasets", "articles"]}
)
model = response.json()
print(f"Model: {model['name']}")
print(f"License: {model['related_entities']['license']['name']}")
```

### Using JavaScript/TypeScript

```javascript
// List models
const response = await fetch(
  'http://localhost:8000/api/v1/models?page=1&page_size=20&search=bert'
);
const data = await response.json();
console.log(`Found ${data.count} models`);

// Get model details
const modelId = encodeURIComponent('https://w3id.org/mlentory/model/abc123');
const detailResponse = await fetch(
  `http://localhost:8000/api/v1/models/${modelId}?include_entities=license&include_entities=datasets`
);
const model = await detailResponse.json();
console.log(`Model: ${model.name}`);
```

## Interactive API Documentation

FastAPI automatically generates interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
  - Test endpoints directly in the browser
  - View request/response schemas
  - See example values

- **ReDoc**: http://localhost:8000/redoc
  - Alternative documentation view
  - Better for reading and understanding

## Error Handling

The API returns standard HTTP status codes:

- `200 OK` - Successful request
- `404 Not Found` - Model not found
- `422 Unprocessable Entity` - Invalid request parameters
- `500 Internal Server Error` - Server-side error

**Error Response Format:**
```json
{
  "detail": "Model not found"
}
```

## Development

### Adding New Endpoints

1. Create endpoint function in appropriate router (e.g., `routers/models.py`)
2. Add response schema to `schemas/responses.py` if needed
3. Add service logic to appropriate service file
4. Update this README with endpoint documentation

### Code Style

The codebase follows the MLentory project standards:
- **Formatter**: `black` with 100 char line length
- **Linter**: `ruff` with standard rules
- **Type hints**: Full type annotations required
- **Docstrings**: Google-style docstrings

## Testing

```bash
# Run all tests
pytest tests/

# Run API tests specifically
pytest tests/api/

# Run with coverage
pytest --cov=api tests/
```

## Future Enhancements

Potential additions to the API:

- [ ] **Filtering**: Advanced filtering by license, task, platform, etc.
- [ ] **Aggregations**: Statistics and faceted search (e.g., count by license)
- [ ] **Batch operations**: Get multiple models in one request
- [ ] **GraphQL**: Alternative query interface for complex graph traversals
- [ ] **Authentication**: API key or OAuth2 authentication
- [ ] **Rate limiting**: Request throttling to prevent abuse
- [ ] **Caching**: Redis-based response caching
- [ ] **WebSocket**: Real-time updates for model changes
- [ ] **Export formats**: RDF/Turtle, JSON-LD export options

## Troubleshooting

### Connection Errors

**Issue**: `Elasticsearch connection failed`
- Check that Elasticsearch is running: `docker-compose ps elasticsearch`
- Verify `ELASTIC_HOST` and `ELASTIC_PORT` environment variables
- Check Elasticsearch logs: `docker-compose logs elasticsearch`

**Issue**: `Neo4j connection failed`
- Check that Neo4j is running: `docker-compose ps neo4j`
- Verify `NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD`
- Check Neo4j logs: `docker-compose logs neo4j`

### Import Errors

**Issue**: `ModuleNotFoundError: No module named 'fastapi'`
- Install dependencies: `poetry install`
- Or in Docker: rebuild the container with `docker-compose build api`

### Empty Results

**Issue**: API returns empty results
- Ensure data has been loaded via the ETL pipeline
- Check Elasticsearch index exists: `curl http://localhost:9201/_cat/indices`
- Verify Neo4j has data: Open Neo4j Browser at http://localhost:7474

## Related Documentation

- [MLentory ETL Pipeline](../README.md)
- [FAIR4ML Schema](../schemas/fair4ml/)
- [ETL Loaders](../etl_loaders/)
- [Docker Deployment](../deploy/)

## License

See the main project [LICENSE](../LICENSE) file.
