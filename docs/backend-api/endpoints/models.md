# Model Endpoints

Complete reference for model-related API endpoints.

---

## List Models

### `GET /api/v1/models`

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

---

## Get Model Detail

### `GET /api/v1/models/{model_id}`

Get detailed model information with optional related entities.

**Path Parameters:**
- `model_id` (string) - Model URI/identifier (URL-encoded)

**Query Parameters:**
- `resolve_properties` (list[string], optional) - Related entities to include by relationship type
  - Examples: `HAS_LICENSE`, `dataset`, `author`

**Example Request:**
```bash
GET /api/v1/models/https%3A%2F%2Fw3id.org%2Fmlentory%2Fmodel%2Fabc123?resolve_properties=HAS_LICENSE&resolve_properties=dataset
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
}
```

---

## Faceted Search

### `GET /api/v1/models/search`

Advanced faceted search with dynamic facets and filters.

**Query Parameters:**
- `query` (string) - Text search query across model fields
- `filters` (JSON string) - Property filters (e.g., `{"license": ["MIT"], "mlTask": ["text-generation"]}`)
- `page` (int, default: 1) - Page number (1-based)
- `page_size` (int, default: 50, max: 1000) - Results per page
- `facets` (JSON array) - Facet fields to aggregate (e.g., `["mlTask", "license", "keywords"]`)
- `facet_size` (int, default: 20, max: 100) - Maximum values per facet
- `facet_query` (JSON object) - Search within specific facets (e.g., `{"keywords": "medical"}`)

**Example Requests:**
```bash
# Simple search
GET /api/v1/models/search?query=image+classification

# Search with filters
GET /api/v1/models/search?query=bert&filters={"license":["MIT"],"mlTask":["text-classification"]}

# Custom facets
GET /api/v1/models/search?facets=["license","sharedBy"]&facet_size=50

# Search within facets
GET /api/v1/models/search?facet_query={"keywords":"medical"}
```

**Response:**
```json
{
  "models": [
    {
      "db_identifier": "https://w3id.org/mlentory/model/abc123",
      "name": "bert-base-uncased",
      "description": "BERT base model",
      "sharedBy": "google",
      "license": "apache-2.0",
      "mlTask": ["fill-mask"],
      "keywords": ["bert", "transformer"],
      "platform": "Hugging Face"
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 50,
  "filters": {
    "license": ["MIT"],
    "mlTask": ["text-classification"]
  },
  "facets": {
    "mlTask": [
      {"value": "text-classification", "count": 75},
      {"value": "text-generation", "count": 45}
    ],
    "license": [
      {"value": "MIT", "count": 120},
      {"value": "Apache-2.0", "count": 30}
    ]
  },
  "facet_config": {
    "mlTask": {
      "field": "ml_tasks",
      "label": "ML Tasks",
      "type": "keyword",
      "icon": "mdi-brain",
      "is_high_cardinality": false,
      "supports_search": true
    }
  }
}
```

---

## Facet Configuration

### `GET /api/v1/models/facets/config`

Get configuration metadata for all available facets.

**Response:**
```json
{
  "facet_config": {
    "mlTask": {
      "field": "ml_tasks",
      "label": "ML Tasks",
      "type": "keyword",
      "icon": "mdi-brain",
      "is_high_cardinality": false,
      "default_size": 20,
      "supports_search": true,
      "pinned": true
    },
    "license": {
      "field": "license",
      "label": "Licenses",
      "type": "keyword",
      "icon": "mdi-license",
      "is_high_cardinality": false,
      "default_size": 10,
      "supports_search": true,
      "pinned": true
    },
    "keywords": {
      "field": "keywords",
      "label": "Keywords",
      "type": "keyword",
      "icon": "mdi-tag",
      "is_high_cardinality": true,
      "default_size": 20,
      "supports_search": true,
      "pinned": true
    }
  }
}
```

---

## Facet Values

### `GET /api/v1/models/facets/values`

Fetch values for a specific facet with search and pagination.

**Query Parameters:**
- `field` (string, required) - Facet field name (e.g., `keywords`, `mlTask`, `license`)
- `search_query` (string) - Optional search term to filter facet values
- `after_key` (string) - Pagination cursor for getting more values
- `limit` (int, default: 50, max: 200) - Maximum values to return
- `filters` (JSON string) - Current filters for context

**Example Requests:**
```bash
# Get keyword values
GET /api/v1/models/facets/values?field=keywords

# Search within keywords
GET /api/v1/models/facets/values?field=keywords&search_query=medical

# Paginate through values
GET /api/v1/models/facets/values?field=keywords&after_key=previous_value&limit=50

# With context filters
GET /api/v1/models/facets/values?field=keywords&filters={"license":["MIT"]}
```

**Response:**
```json
{
  "values": [
    {"value": "medical-imaging", "count": 15},
    {"value": "medical-diagnosis", "count": 12},
    {"value": "medical-research", "count": 8}
  ],
  "after_key": "medical-research",
  "has_more": true
}
```

---

## Error Responses

All endpoints may return the following error responses:

- `404 Not Found` - Model not found
- `422 Unprocessable Entity` - Invalid request parameters
- `500 Internal Server Error` - Server-side error

See [Error Handling](../reference/errors.md) for details.

