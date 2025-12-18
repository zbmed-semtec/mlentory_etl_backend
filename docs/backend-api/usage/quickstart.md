# API Usage Quick Start

Get started using the MLentory API! This guide shows you how to use the API once it's running.

> **Setting up the API?** See the [Quick Start Guide](../../getting-started/quickstart.md) for installation and configuration instructions.

---

## Prerequisites

- MLentory API running (see [Getting Started](../../getting-started/quickstart.md))
- API accessible at `http://localhost:8000` (or your configured host/port)

---

## Interactive Documentation

The API provides interactive documentation:

- **Swagger UI:** http://localhost:8000/docs
  - Test endpoints directly in the browser
  - View request/response schemas
  - See example values

- **ReDoc:** http://localhost:8000/redoc
  - Alternative documentation view
  - Better for reading and understanding

---

## Basic Usage

### Check API Health

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "elasticsearch": true,
  "neo4j": true
}
```

### List Models

```bash
curl http://localhost:8000/api/v1/models?page=1&page_size=10
```

### Search Models

```bash
curl "http://localhost:8000/api/v1/models?search=bert&page=1&page_size=10"
```

### Get Model Details

```bash
# URL-encode the model ID
MODEL_ID="https://w3id.org/mlentory/model/abc123"
ENCODED_ID=$(echo -n "$MODEL_ID" | jq -sRr @uri)

curl "http://localhost:8000/api/v1/models/$ENCODED_ID"
```

---

## Using Python

### Install Dependencies

```bash
pip install requests
```

### Basic Example

```python
import requests

# Base URL
BASE_URL = "http://localhost:8000"

# List models
response = requests.get(f"{BASE_URL}/api/v1/models", params={
    "page": 1,
    "page_size": 20,
    "search": "bert"
})

data = response.json()
print(f"Found {data['count']} models")

# Get model details
model_id = "https://w3id.org/mlentory/model/abc123"
response = requests.get(
    f"{BASE_URL}/api/v1/models/{model_id}",
    params={"resolve_properties": ["HAS_LICENSE", "dataset"]}
)
model = response.json()
print(f"Model: {model['name']}")
```

---

## Using JavaScript/TypeScript

### Basic Example

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
  `http://localhost:8000/api/v1/models/${modelId}?resolve_properties=HAS_LICENSE&resolve_properties=dataset`
);
const model = await detailResponse.json();
console.log(`Model: ${model.name}`);
```

---

## Next Steps

- **[API Examples](examples.md)** → See more code examples
- **[API Endpoints](../endpoints/models.md)** → Explore all endpoints
- **[API Reference](../reference/schemas.md)** → Understand response schemas

