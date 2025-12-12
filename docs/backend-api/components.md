# API Components

Detailed description of API components and their responsibilities.

---

## Component Overview

The API is organized into several key components:

```
api/
├── main.py                    # FastAPI application entrypoint
├── config.py                  # Configuration management
├── routers/
│   ├── models.py             # Model-related endpoints
│   ├── graph.py              # Graph exploration endpoints
│   └── stats.py              # Statistics endpoints
├── schemas/
│   └── responses.py          # Pydantic response models
└── services/
    ├── elasticsearch_service.py  # Elasticsearch queries
    ├── graph_service.py         # Neo4j graph queries
    └── faceted_search.py         # Faceted search logic
```

---

## Configuration (`config.py`)

Centralizes access to Elasticsearch and Neo4j configurations by reusing the existing ETL loader configs.

**Key Features:**
- Singleton pattern for config instances
- Lazy initialization of database clients
- Environment-based configuration
- Reuses ETL loader configurations

**Example:**
```python
from etl_loaders.elasticsearch_store import ElasticsearchConfig, create_elasticsearch_client
from etl_loaders.rdf_store import Neo4jConfig

# Same environment variables as ETL
es_config = ElasticsearchConfig.from_env()  # Uses ELASTIC_* vars
neo4j_config = Neo4jConfig.from_env()       # Uses NEO4J_* vars
```

---

## Services

### ElasticsearchService

Handles all Elasticsearch queries for model search and retrieval.

**Responsibilities:**
- Paginated model search with text queries
- Single model retrieval by identifier
- Result transformation to API response models

**Key Methods:**
- `search_models(search_query, page, page_size)` - Paginated search
- `get_model_by_id(model_id)` - Single model retrieval

### GraphService

Handles all Neo4j graph traversals and relationship queries.

**Responsibilities:**
- Fetch subgraphs starting from any entity with configurable depth
- Retrieve properties for batches of entities
- Support efficient graph exploration

**Key Methods:**
- `get_entity_graph(entity_id, depth, relationships...)` - Explore graph neighborhood
- `get_entities_properties_batch(entity_ids, properties)` - Batch property retrieval

### FacetedSearchService

Handles faceted search and aggregations.

**Responsibilities:**
- Build faceted search queries
- Calculate facet counts and aggregations
- Support facet value search and pagination

**Key Methods:**
- `search_with_facets(query, filters, facets, ...)` - Faceted search
- `get_facet_config()` - Get facet configuration
- `get_facet_values(field, search_query, ...)` - Get facet values

---

## Schemas (`schemas/responses.py`)

Pydantic models for API responses that extend FAIR4ML schemas.

**Key Models:**
- `PaginatedResponse[T]` - Generic pagination wrapper
- `ModelListItem` - Lightweight model info for list views
- `ModelDetail` - Full model info (extends `MLModel` from `schemas.fair4ml.mlmodel`)
- `RelatedEntities` - Container for related entities from Neo4j
- Entity models: `LicenseEntity`, `DatasetEntity`, `ArticleEntity`, etc.

---

## Routers

### Models Router (`routers/models.py`)

Defines the API endpoints for model operations.

**Endpoints:**
- `GET /api/v1/models` - List models
- `GET /api/v1/models/{model_id}` - Get model details
- `GET /api/v1/models/search` - Faceted search
- `GET /api/v1/models/facets/config` - Get facet configuration
- `GET /api/v1/models/facets/values` - Get facet values

### Graph Router (`routers/graph.py`)

Defines endpoints for graph exploration.

**Endpoints:**
- `GET /api/v1/graph/{entity_id}` - Explore graph
- `POST /api/v1/graph/entities_by_ids_batch` - Batch entity properties

### Stats Router (`routers/stats.py`)

Defines endpoints for statistics.

**Endpoints:**
- `GET /api/v1/stats/platform` - Platform statistics

---

## Main Application (`main.py`)

FastAPI application entry point and global configuration.

**Responsibilities:**
- Initialize FastAPI application
- Configure CORS middleware
- Register routers
- Handle application lifecycle (startup/shutdown)
- Provide root and health endpoints
- Generate OpenAPI documentation

---

## Component Interactions

```
Client Request
    │
    ▼
FastAPI Router
    │
    ├──> Validate request (Pydantic)
    │
    ├──> Call Service Layer
    │       │
    │       ├──> ElasticsearchService
    │       │       └──> Elasticsearch
    │       │
    │       └──> GraphService
    │               └──> Neo4j
    │
    ├──> Transform to Response Schema
    │
    └──> Return JSON Response
```

---

## Next Steps

- **[API Architecture](architecture.md)** → Understand system design
- **[Data Flow](data-flow.md)** → See request flow
- **[API Endpoints](endpoints/models.md)** → Explore endpoints

