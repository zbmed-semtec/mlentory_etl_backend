# API Schemas

Complete reference for API request and response schemas.

---

## Response Models

### PaginatedResponse

Generic pagination wrapper for list endpoints.

```json
{
  "count": 150,
  "next": "/api/v1/models?page=2&page_size=20",
  "prev": "/api/v1/models?page=1&page_size=20",
  "results": [...]
}
```

**Fields:**
- `count` (int) - Total number of items
- `next` (string|null) - URL for next page
- `prev` (string|null) - URL for previous page
- `results` (array) - List of items

---

### ModelListItem

Lightweight model information for list views.

```json
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
```

**Fields:**
- `db_identifier` (string) - Unique model identifier (URI)
- `name` (string) - Model name
- `description` (string) - Model description
- `sharedBy` (string) - Organization/author sharing the model
- `license` (string) - License identifier
- `mlTask` (array[string]) - ML tasks the model supports
- `keywords` (array[string]) - Keywords/tags
- `platform` (string) - Source platform (e.g., "Hugging Face")

---

### ModelDetail

Full model information extending FAIR4ML MLModel schema.

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
    "HAS_LICENSE": [...],
    "dataset": [...]
  }
}
```

**Fields:**
- All fields from FAIR4ML MLModel schema
- `platform` (string, optional) - Source platform
- `related_entities` (RelatedEntities) - Graph relationships

---

### RelatedEntities

Container for related entities from Neo4j graph.

```json
{
  "HAS_LICENSE": [
    {
      "uri": "https://spdx.org/licenses/Apache-2.0",
      "name": "Apache License 2.0",
      "url": "https://www.apache.org/licenses/LICENSE-2.0"
    }
  ],
  "dataset": [
    {
      "uri": "https://w3id.org/mlentory/dataset/xyz789",
      "name": "Wikipedia + BookCorpus",
      "description": "Training data for BERT"
    }
  ]
}
```

**Structure:**
- Keys are relationship types (e.g., "HAS_LICENSE", "dataset")
- Values are arrays of entity objects

---

### Entity Models

#### LicenseEntity

```json
{
  "uri": "https://spdx.org/licenses/Apache-2.0",
  "name": "Apache License 2.0",
  "url": "https://www.apache.org/licenses/LICENSE-2.0"
}
```

#### DatasetEntity

```json
{
  "uri": "https://w3id.org/mlentory/dataset/xyz789",
  "name": "Wikipedia + BookCorpus",
  "description": "Training data for BERT",
  "url": "https://example.com/dataset"
}
```

#### ArticleEntity

```json
{
  "uri": "https://arxiv.org/abs/1810.04805",
  "name": "BERT: Pre-training of Deep Bidirectional Transformers",
  "url": "https://arxiv.org/abs/1810.04805"
}
```

---

### GraphResponse

Graph exploration response.

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

### HealthResponse

Health check response.

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "elasticsearch": true,
  "neo4j": true
}
```

**Fields:**
- `status` (string) - "healthy" or "degraded"
- `version` (string) - API version
- `elasticsearch` (boolean) - Elasticsearch connection status
- `neo4j` (boolean) - Neo4j connection status

---

## FAIR4ML Schema

All model responses extend the FAIR4ML MLModel schema. See the [FAIR4ML Schema Documentation](../../schemas/fair4ml.md) for complete field definitions.

---

## Schema Validation

All request and response data is validated using Pydantic:

- **Request Validation:** Invalid parameters return `422 Unprocessable Entity`
- **Response Validation:** All responses conform to defined schemas
- **Type Safety:** Full type annotations for all models

---

## OpenAPI Schema

Complete OpenAPI schema is available at:

- **Swagger UI:** http://localhost:8000/docs
- **OpenAPI JSON:** http://localhost:8000/openapi.json

---

## Next Steps

- **[Error Handling](errors.md)** → Understand error responses
- **[API Endpoints](../endpoints/models.md)** → See schemas in context
- **[FAIR4ML Schema](../../schemas/fair4ml.md)** → Learn about FAIR4ML

