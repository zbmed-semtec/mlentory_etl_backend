# MLentory API Architecture

This document provides a technical overview of the MLentory API architecture, explaining how components interact and how data flows through the system.

## System Context

The MLentory API is the query interface for the MLentory knowledge graph. It sits on top of two data stores populated by the ETL pipeline:

```
┌─────────────────────────────────────────────────────────────┐
│                      MLentory System                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐        ┌──────────────┐                    │
│  │   Sources   │        │     ETL      │                     │
│  │             │───────>│   Pipeline   │                     │
│  │ • HF        │        │  (Dagster)   │                     │
│  │ • OpenML    │        └──────┬───────┘                     │
│  │ • Papers    │               │                             │
│  └─────────────┘               │                             │
│                                 │                             │
│                    ┌────────────┴────────────┐               │
│                    │                         │               │
│                    ▼                         ▼               │
│            ┌──────────────┐        ┌──────────────┐         │
│            │Elasticsearch │        │    Neo4j     │         │
│            │  (Indexed)   │        │   (Graph)    │         │
│            └──────┬───────┘        └──────┬───────┘         │
│                   │                       │                  │
│                   └───────────┬───────────┘                  │
│                               │                              │
│                               ▼                              │
│                      ┌─────────────────┐                     │
│                      │  MLentory API   │                     │
│                      │   (FastAPI)     │                     │
│                      └────────┬────────┘                     │
│                               │                              │
└───────────────────────────────┼──────────────────────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   Clients    │
                         │              │
                         │ • Web Apps   │
                         │ • CLI Tools  │
                         │ • Notebooks  │
                         └──────────────┘
```

## Component Architecture

### Layered Architecture

The API follows a clean layered architecture:

```
┌─────────────────────────────────────────────────────────┐
│                  Presentation Layer                      │
│  ┌─────────────────────────────────────────────────┐    │
│  │  FastAPI App (main.py)                          │    │
│  │  • CORS middleware                              │    │
│  │  • OpenAPI documentation                        │    │
│  │  • Error handling                               │    │
│  └─────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                    Routing Layer                        │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Routers (routers/models.py)                    │    │
│  │  • Endpoint definitions                         │    │
│  │  • Request validation                           │    │
│  │  • Response serialization                       │    │
│  └─────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                   Service Layer                         │
│  ┌──────────────────────┐  ┌──────────────────────┐     │
│  │ ElasticsearchService │  │   Neo4jService       │     │
│  │ • Model search       │  │ • Relationship       │     │
│  │ • Pagination         │  │   queries            │     │
│  │ • Result transform   │  │ • Entity fetching    │     │
│  └──────────────────────┘  └──────────────────────┘     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│              Configuration & Data Access                │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Config Module (config.py)                      │    │
│  │  • Reuses ETL configs                          │    │
│  │  • Singleton instances                         │    │
│  └─────────────────────────────────────────────────┘    │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────┐     │
│  │ etl_loaders/         │  │ etl_loaders/         │     │
│  │ elasticsearch_store  │  │ rdf_store            │     │
│  └──────────────────────┘  └──────────────────────┘     │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                    Data Layer                           │
│  ┌──────────────────────┐  ┌──────────────────────┐     │
│  │   Elasticsearch      │  │      Neo4j           │     │
│  └──────────────────────┘  └──────────────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### Component Responsibilities

#### 1. Presentation Layer (`main.py`)
- **Purpose**: Application entry point and global configuration
- **Responsibilities**:
  - Initialize FastAPI application
  - Configure CORS middleware
  - Register routers
  - Handle application lifecycle (startup/shutdown)
  - Provide root and health endpoints
  - Generate OpenAPI documentation

#### 2. Routing Layer (`routers/`)
- **Purpose**: HTTP endpoint definitions and request handling
- **Responsibilities**:
  - Define endpoint paths and HTTP methods
  - Validate request parameters with Pydantic
  - Orchestrate service calls
  - Build pagination URLs
  - Handle HTTP errors
  - Serialize responses

#### 3. Service Layer (`services/`)
- **Purpose**: Business logic and data access orchestration
- **Components**:
  - **ElasticsearchService**: Queries indexed model data
  - **Neo4jService**: Queries graph relationships
- **Responsibilities**:
  - Execute database queries
  - Transform database results to domain models
  - Implement search and pagination logic
  - Handle service-level errors

#### 4. Configuration Layer (`config.py`)
- **Purpose**: Centralized configuration management
- **Responsibilities**:
  - Load configuration from environment variables
  - Provide singleton instances of configs and clients
  - Reuse ETL loader configurations
  - Implement lazy initialization

#### 5. Schema Layer (`schemas/`)
- **Purpose**: Data validation and serialization
- **Components**:
  - **ModelListItem**: Lightweight model for list views
  - **ModelDetail**: Full model (extends FAIR4ML MLModel)
  - **RelatedEntities**: Graph relationship container
  - **Entity models**: License, Dataset, Article, etc.
  - **PaginatedResponse**: Generic pagination wrapper
- **Responsibilities**:
  - Validate response data
  - Define JSON serialization format
  - Provide OpenAPI schema documentation
  - Extend FAIR4ML schemas

## Data Flow

### List Models Flow

```
Client
  │
  │ GET /api/v1/models?page=1&page_size=20&search=bert
  │
  ▼
FastAPI Router (routers/models.py)
  │
  │ 1. Validate query parameters
  │ 2. Call elasticsearch_service.search_models()
  │
  ▼
ElasticsearchService (services/elasticsearch_service.py)
  │
  │ 3. Build Elasticsearch query
  │    • Full-text search on name, description, keywords
  │    • Calculate pagination offset
  │    • Sort by name
  │
  ▼
Elasticsearch
  │
  │ 4. Execute search query
  │ 5. Return matching documents + total count
  │
  ▼
ElasticsearchService
  │
  │ 6. Transform ES hits to ModelListItem objects
  │ 7. Return (models, total_count)
  │
  ▼
FastAPI Router
  │
  │ 8. Calculate next/prev URLs
  │ 9. Build PaginatedResponse
  │
  ▼
Client (receives paginated JSON)
```

### Get Model Detail Flow

```
Client
  │
  │ GET /api/v1/models/{id}?include_entities=license,datasets
  │
  ▼
FastAPI Router (routers/models.py)
  │
  │ 1. Validate model_id and include_entities
  │
  ▼
ElasticsearchService
  │
  │ 2. Query model by db_identifier
  │ 3. Return ModelListItem or None
  │
  ▼
FastAPI Router
  │
  │ 4. If not found → 404 error
  │ 5. If include_entities specified:
  │
  ▼
Neo4jService (services/neo4j_service.py)
  │
  │ 6. For each requested entity type:
  │    • _get_license() if "license" requested
  │    • _get_datasets() if "datasets" requested
  │    • etc.
  │
  ▼
Neo4j
  │
  │ 7. Execute Cypher queries
  │    MATCH (m:MLModel {uri: $uri})-[:RELATIONSHIP]->(entity)
  │    RETURN entity properties
  │
  ▼
Neo4jService
  │
  │ 8. Transform Neo4j records to entity models
  │ 9. Return RelatedEntities object
  │
  ▼
FastAPI Router
  │
  │ 10. Combine ES data + Neo4j entities
  │ 11. Build ModelDetail response
  │
  ▼
Client (receives complete model JSON with relationships)
```

## Database Query Patterns

### Elasticsearch Queries

The API uses the `elasticsearch-dsl` library for type-safe queries:

```python
# Full-text search across multiple fields
search = HFModelDocument.search(using=client, index="hf_models")
search = search.query(
    Q("multi_match", 
      query="bert", 
      fields=["name", "description", "keywords"])
)

# Pagination with slicing
search = search[offset:offset + page_size]

# Execute and get results
response = search.execute()
```

### Neo4j Queries

The API uses Cypher queries via the `_run_cypher` helper from `etl_loaders`:

```cypher
-- Get license for a model
MATCH (m:MLModel {uri: $model_uri})-[:HAS_LICENSE|:license]->(l:License)
RETURN l.uri as uri, l.name as name, l.url as url
LIMIT 1

-- Get related datasets
MATCH (m:MLModel {uri: $model_uri})-[:USES_DATASET|:dataset|:trainingData]->(d:Dataset)
RETURN DISTINCT d.uri as uri, d.name as name, d.description as description, d.url as url
```

**Relationship Pattern Notes:**
- Multiple edge types (e.g., `[:HAS_LICENSE|:license]`) handle variations in graph structure
- `DISTINCT` prevents duplicate results from multiple paths
- Property access uses `.` notation (e.g., `l.name`)

## Configuration Reuse Strategy

The API avoids configuration duplication by importing from ETL loaders:

```python
# api/config.py
from etl_loaders.elasticsearch_store import (
    ElasticsearchConfig,
    create_elasticsearch_client
)
from etl_loaders.rdf_store import Neo4jConfig, _run_cypher

# Same environment variables as ETL
es_config = ElasticsearchConfig.from_env()  # Uses ELASTIC_* vars
neo4j_config = Neo4jConfig.from_env()       # Uses NEO4J_* vars
```

**Benefits:**
- Single source of truth for configurations
- Consistent connection parameters across ETL and API
- Shared helper utilities (e.g., `_run_cypher`)
- Reduced maintenance burden

## Schema Extension Strategy

The API extends FAIR4ML schemas rather than duplicating them:

```python
# api/schemas/responses.py
from schemas.fair4ml.mlmodel import MLModel

class ModelDetail(MLModel):
    """Extends FAIR4ML MLModel with API-specific fields."""
    
    # Add platform (not in FAIR4ML)
    platform: Optional[str] = Field(default=None)
    
    # Add related entities (graph relationships)
    related_entities: RelatedEntities = Field(default_factory=RelatedEntities)
```

**Benefits:**
- All FAIR4ML fields inherited automatically
- Validation rules from FAIR4ML apply
- Changes to MLModel propagate to API
- API can add non-FAIR fields as needed

## Error Handling

The API uses FastAPI's exception handling:

```python
try:
    model = elasticsearch_service.get_model_by_id(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
except HTTPException:
    raise  # Re-raise HTTP exceptions
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail="Internal server error")
```

**HTTP Status Codes:**
- `200 OK` - Successful request
- `404 Not Found` - Model/resource not found
- `422 Unprocessable Entity` - Invalid request parameters (automatic via Pydantic)
- `500 Internal Server Error` - Server-side error

## Performance Considerations

### Query Optimization

1. **Elasticsearch (List Endpoint)**:
   - Indexed search is fast (sub-100ms for most queries)
   - Pagination limits memory usage
   - Sorting by `name.raw` uses keyword field (faster than analyzed text)

2. **Neo4j (Detail Endpoint)**:
   - Relationships fetched only when requested (`include_entities`)
   - Each entity type is a separate query (parallelization possible)
   - `LIMIT 1` on singular relationships (e.g., license)
   - `DISTINCT` prevents duplicate traversals

### Caching Opportunities

Current implementation doesn't cache, but potential caching layers:

1. **Application-level**: Cache model details for X minutes
2. **HTTP-level**: Add `Cache-Control` headers for CDN caching
3. **Database-level**: Elasticsearch query cache (automatic)

### Scalability

The API is stateless and can scale horizontally:
- No session state stored in API instances
- Database connections per request
- Independent service instances can run in parallel
- Load balancer can distribute requests

## Security Considerations

### Current State (MVP)
- No authentication (open access)
- No rate limiting
- CORS allows all origins (`allow_origins=["*"]`)

### Production Recommendations
1. **Authentication**: Add API key or OAuth2
2. **Rate Limiting**: Implement per-client throttling
3. **CORS**: Restrict to specific origins
4. **Input Validation**: Already handled by Pydantic
5. **Database Security**: Use read-only database credentials
6. **HTTPS**: Terminate SSL at load balancer or reverse proxy

## Testing Strategy

### Unit Tests
- Test service methods with mocked database clients
- Test schema validation with invalid data
- Test pagination URL generation

### Integration Tests
- Test endpoints with test Elasticsearch index
- Test endpoints with test Neo4j database
- Test error handling with missing data

### End-to-End Tests
- Test full request/response cycle
- Test with realistic data volumes
- Test concurrent requests

## Monitoring and Observability

### Health Checks
The `/health` endpoint tests database connectivity:
```python
{
  "status": "healthy",  # or "degraded"
  "elasticsearch": true,
  "neo4j": true
}
```

### Logging
All modules use Python's `logging` framework:
```python
logger = logging.getLogger(__name__)
logger.info("Processing request...")
logger.error("Error occurred", exc_info=True)
```

### Metrics (Future)
Potential metrics to track:
- Request rate (requests/second)
- Response time (p50, p95, p99)
- Error rate by endpoint
- Database query latency
- Result set sizes

## Deployment

### Docker Deployment
The API runs as a Docker container in the main `docker-compose.yml`:

```yaml
api:
  build:
    context: .
    dockerfile: api/Dockerfile
  ports:
    - "8000:8000"
  env_file:
    - .env
  depends_on:
    - neo4j
    - elasticsearch
  networks:
    - mlentory-network
```

### Environment Configuration
All configuration via environment variables (12-factor app):
- Development: `.env` file
- Production: Kubernetes secrets, AWS Parameter Store, etc.

### Container Lifecycle
1. Load environment variables
2. Initialize FastAPI app
3. Import routers (lazy-load configs)
4. Start uvicorn server
5. Handle requests
6. Shutdown gracefully on SIGTERM

## Future Enhancements

### Short-term
1. **Filtering**: Add filters for license, task, platform
2. **Aggregations**: Return facet counts (e.g., models per license)
3. **Sorting**: Allow sorting by different fields
4. **Field Selection**: Allow clients to specify which fields to return

### Medium-term
1. **GraphQL**: Alternative query interface for complex traversals
2. **Batch Operations**: Get multiple models in one request
3. **Caching**: Add Redis for response caching
4. **Authentication**: API key or OAuth2

### Long-term
1. **WebSocket**: Real-time updates when models change
2. **Export Formats**: RDF/Turtle, JSON-LD, CSV
3. **Analytics**: Track popular models, common queries
4. **Recommendations**: "Models similar to X"

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Elasticsearch DSL](https://elasticsearch-dsl.readthedocs.io/)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/)
- [FAIR4ML Specification](https://rda-fair4ml.github.io/FAIR4ML-schema/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
