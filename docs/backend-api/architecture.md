# API Architecture

This document provides a technical overview of the MLentory API architecture, explaining how components interact and how data flows through the system.

---

## Layered Architecture

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
│  │ ElasticsearchService │  │   GraphService       │     │
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

---

## Component Responsibilities

### 1. Presentation Layer (`main.py`)

**Purpose:** Application entry point and global configuration

**Responsibilities:**
- Initialize FastAPI application
- Configure CORS middleware
- Register routers
- Handle application lifecycle (startup/shutdown)
- Provide root and health endpoints
- Generate OpenAPI documentation

### 2. Routing Layer (`routers/`)

**Purpose:** HTTP endpoint definitions and request handling

**Responsibilities:**
- Define endpoint paths and HTTP methods
- Validate request parameters with Pydantic
- Orchestrate service calls
- Build pagination URLs
- Handle HTTP errors
- Serialize responses

### 3. Service Layer (`services/`)

**Purpose:** Business logic and data access orchestration

**Components:**
- **ElasticsearchService:** Queries indexed model data
- **GraphService:** Queries graph relationships
- **FacetedSearchService:** Handles faceted search and aggregations

**Responsibilities:**
- Execute database queries
- Transform database results to domain models
- Implement search and pagination logic
- Handle service-level errors

### 4. Configuration Layer (`config.py`)

**Purpose:** Centralized configuration management

**Responsibilities:**
- Load configuration from environment variables
- Provide singleton instances of configs and clients
- Reuse ETL loader configurations
- Implement lazy initialization

### 5. Schema Layer (`schemas/`)

**Purpose:** Data validation and serialization

**Components:**
- **ModelListItem:** Lightweight model for list views
- **ModelDetail:** Full model (extends FAIR4ML MLModel)
- **RelatedEntities:** Graph relationship container
- **Entity models:** License, Dataset, Article, etc.
- **PaginatedResponse:** Generic pagination wrapper

**Responsibilities:**
- Validate response data
- Define JSON serialization format
- Provide OpenAPI schema documentation
- Extend FAIR4ML schemas

---

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

---

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

---

## Performance Considerations

### Query Optimization

1. **Elasticsearch (List Endpoint):**
   - Indexed search is fast (sub-100ms for most queries)
   - Pagination limits memory usage
   - Sorting by `name.raw` uses keyword field (faster than analyzed text)

2. **Neo4j (Detail Endpoint):**
   - Relationships fetched only when requested (`resolve_properties`)
   - Each entity type is a separate query (parallelization possible)
   - `LIMIT 1` on singular relationships (e.g., license)
   - `DISTINCT` prevents duplicate traversals

### Scalability

The API is stateless and can scale horizontally:
- No session state stored in API instances
- Database connections per request
- Independent service instances can run in parallel
- Load balancer can distribute requests

---

## Security Considerations

### Current State (MVP)
- No authentication (open access)
- No rate limiting
- CORS allows all origins (`allow_origins=["*"]`)

### Production Recommendations
1. **Authentication:** Add API key or OAuth2
2. **Rate Limiting:** Implement per-client throttling
3. **CORS:** Restrict to specific origins
4. **Input Validation:** Already handled by Pydantic
5. **Database Security:** Use read-only database credentials
6. **HTTPS:** Terminate SSL at load balancer or reverse proxy

---

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

---

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Elasticsearch DSL](https://elasticsearch-dsl.readthedocs.io/)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/)
- [FAIR4ML Specification](https://rda-fair4ml.github.io/FAIR4ML-schema/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

