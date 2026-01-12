# API Data Flow

How requests flow through the API system.

---

## List Models Flow

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

---

## Get Model Detail Flow

```
Client
  │
  │ GET /api/v1/models/{id}?resolve_properties=HAS_LICENSE&resolve_properties=dataset
  │
  ▼
FastAPI Router (routers/models.py)
  │
  │ 1. Validate model_id and resolve_properties
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
  │ 5. If resolve_properties specified:
  │
  ▼
GraphService (services/graph_service.py)
  │
  │ 6. For each requested entity type:
  │    • _get_license() if "HAS_LICENSE" requested
  │    • _get_datasets() if "dataset" requested
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
GraphService
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

---

## Faceted Search Flow

```
Client
  │
  │ GET /api/v1/models/search?query=bert&filters={"license":["MIT"]}&facets=["mlTask","license"]
  │
  ▼
FastAPI Router (routers/models.py)
  │
  │ 1. Parse and validate query parameters
  │ 2. Parse JSON filters and facets
  │ 3. Call faceted_search_service.search_with_facets()
  │
  ▼
FacetedSearchService (services/faceted_search.py)
  │
  │ 4. Build Elasticsearch query with:
  │    • Text search query
  │    • Filter clauses
  │    • Facet aggregations
  │
  ▼
Elasticsearch
  │
  │ 5. Execute search query
  │ 6. Return results + facet aggregations
  │
  ▼
FacetedSearchService
  │
  │ 7. Transform results to ModelListItem objects
  │ 8. Extract facet counts from aggregations
  │ 9. Return (models, facets, total_count)
  │
  ▼
FastAPI Router
  │
  │ 10. Build FacetedSearchResponse
  │
  ▼
Client (receives models + facets JSON)
```

---

## Graph Exploration Flow

```
Client
  │
  │ GET /api/v1/graph/bert-base-uncased?depth=2&direction=outgoing
  │
  ▼
FastAPI Router (routers/graph.py)
  │
  │ 1. Validate entity_id and query parameters
  │ 2. Call graph_service.get_entity_graph()
  │
  ▼
GraphService (services/graph_service.py)
  │
  │ 3. Find starting entity by ID fragment
  │ 4. Build Cypher query for graph traversal
  │    • Configure depth
  │    • Set direction (outgoing/incoming/both)
  │    • Filter by relationship types if specified
  │
  ▼
Neo4j
  │
  │ 5. Execute Cypher query
  │    MATCH path = (start)-[*1..2]->(connected)
  │    RETURN nodes(path), relationships(path)
  │
  ▼
GraphService
  │
  │ 6. Transform Neo4j records to nodes and edges
  │ 7. Build GraphResponse with metadata
  │
  ▼
FastAPI Router
  │
  │ 8. Return GraphResponse JSON
  │
  ▼
Client (receives graph structure JSON)
```

---

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

---

## Error Flow

```
Client Request
  │
  ▼
FastAPI Router
  │
  ├──> Validation Error?
  │     └──> Return 422 Unprocessable Entity
  │
  ├──> Service Error?
  │     ├──> Resource Not Found
  │     │     └──> Return 404 Not Found
  │     │
  │     └──> Server Error
  │           └──> Return 500 Internal Server Error
  │
  └──> Success
        └──> Return 200 OK with data
```

---

## Next Steps

- **[API Architecture](architecture.md)** → Understand component design
- **[API Components](components.md)** → See component details
- **[API Endpoints](endpoints/models.md)** → Explore endpoints

