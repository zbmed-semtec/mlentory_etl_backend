# Graph Endpoints

Complete reference for graph exploration API endpoints.

---

## Explore Graph

### `GET /api/v1/graph/{entity_id}`

Explore the knowledge graph starting from any entity with configurable depth traversal.

**Path Parameters:**
- `entity_id` (string) - Alphanumeric ID fragment of the starting entity (e.g., `bert-base-uncased`)

**Query Parameters:**
- `depth` (int, default: 1, max: 3) - Number of hops to traverse
- `direction` (string, default: "both") - Traversal direction ("outgoing", "incoming", "both")
- `entity_type` (string, default: "MLModel") - Entity label/type (e.g., `MLModel`, `License`, `DefinedTerm`)
- `relationships` (list[string], optional) - Specific relationship types to follow (e.g., "HAS_LICENSE", "CITED_IN")

**Example Requests:**
```bash
# Get immediate neighbors (depth 1) for an MLModel
GET /api/v1/graph/abc123?entity_type=MLModel

# Get neighbors up to depth 2, outgoing only
GET /api/v1/graph/abc123?entity_type=MLModel&depth=2&direction=outgoing

# Filter by specific relationships
GET /api/v1/graph/abc123?entity_type=MLModel&relationships=HAS_LICENSE&relationships=CITED_IN
```

**Response:**
```json
{
  "nodes": [
    {
      "id": "https://w3id.org/mlentory/model/abc123",
      "labels": ["MLModel"],
      "properties": {
        "name": "bert-base-uncased",
        "uri": "https://w3id.org/mlentory/model/abc123"
      }
    },
    {
      "id": "https://spdx.org/licenses/Apache-2.0",
      "labels": ["License"],
      "properties": {
        "name": "Apache License 2.0",
        "uri": "https://spdx.org/licenses/Apache-2.0"
      }
    }
  ],
  "edges": [
    {
      "id": "rel_123",
      "source": "https://w3id.org/mlentory/model/abc123",
      "target": "https://spdx.org/licenses/Apache-2.0",
      "type": "HAS_LICENSE",
      "properties": {}
    }
  ],
  "metadata": {
    "start_uri": "https://w3id.org/mlentory/model/abc123",
    "depth": 1,
    "direction": "both",
    "node_count": 2,
    "edge_count": 1
  }
}
```

---

## Batch Entity Properties

### `POST /api/v1/graph/entities_by_ids_batch`

Batch fetch properties for multiple entities by their URIs.

**Request Body:**
```json
{
  "entity_ids": [
    "https://w3id.org/mlentory/model/abc123",
    "<https://w3id.org/mlentory/dataset/xyz789>"
  ],
  "properties": ["name", "description"]
}
```

**Note:** The `properties` field is optional. If omitted, all properties are returned.

**Response:**
```json
{
  "count": 2,
  "entities": {
    "https://w3id.org/mlentory/model/abc123": {
      "name": ["bert-base-uncased"],
      "description": ["BERT base model"]
    },
    "https://w3id.org/mlentory/dataset/xyz789": {
      "name": ["Wikipedia + BookCorpus"],
      "description": ["Training data"]
    }
  },
  "cache_stats": {
    "hits": 0,
    "misses": 2,
    "hit_rate": 0.0
  }
}
```

---

## Use Cases

### Finding Related Models

Use graph traversal to find models that share common characteristics:

```bash
# Find models with the same license
GET /api/v1/graph/bert-base-uncased?entity_type=MLModel&depth=2&relationships=HAS_LICENSE
```

### Exploring Dataset Connections

Discover which models use the same training datasets:

```bash
# Find models using the same dataset
GET /api/v1/graph/wikipedia-bookcorpus?entity_type=Dataset&depth=2&direction=incoming
```

### Building Recommendation Systems

Use graph structure to find similar models based on relationships:

```bash
# Find models with similar characteristics
GET /api/v1/graph/model-123?entity_type=MLModel&depth=2&relationships=mlTask&relationships=keywords
```

---

## Error Responses

- `404 Not Found` - Entity not found
- `422 Unprocessable Entity` - Invalid request parameters
- `500 Internal Server Error` - Server-side error

See [Error Handling](../reference/errors.md) for details.

