# API Examples

Practical examples for using the MLentory API.

---

## Python Examples

### Search with Filters

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# Faceted search with filters
response = requests.get(f"{BASE_URL}/api/v1/models/search", params={
    "query": "image classification",
    "filters": json.dumps({"license": ["MIT"], "mlTask": ["image-classification"]}),
    "facets": json.dumps(["mlTask", "license", "keywords"]),
    "page": 1,
    "page_size": 50
})

data = response.json()
print(f"Found {data['total']} models")
print(f"ML Task facets: {data['facets']['mlTask']}")
```

### Get Facet Configuration

```python
response = requests.get(f"{BASE_URL}/api/v1/models/facets/config")
config = response.json()
print(f"Available facets: {list(config['facet_config'].keys())}")
```

### Search Within Facets

```python
response = requests.get(f"{BASE_URL}/api/v1/models/facets/values", params={
    "field": "keywords",
    "search_query": "medical",
    "limit": 20,
    "filters": json.dumps({"license": ["MIT"]})
})
values = response.json()
print(f"Medical keywords: {[v['value'] for v in values['values']]}")
```

### Graph Exploration

```python
# Explore graph from a model
response = requests.get(f"{BASE_URL}/api/v1/graph/bert-base-uncased", params={
    "entity_type": "MLModel",
    "depth": 2,
    "direction": "outgoing",
    "relationships": ["HAS_LICENSE", "dataset"]
})

graph = response.json()
print(f"Found {graph['metadata']['node_count']} nodes")
print(f"Found {graph['metadata']['edge_count']} edges")
```

### Batch Entity Properties

```python
response = requests.post(
    f"{BASE_URL}/api/v1/graph/entities_by_ids_batch",
    json={
        "entity_ids": [
            "https://w3id.org/mlentory/model/abc123",
            "https://w3id.org/mlentory/dataset/xyz789"
        ],
        "properties": ["name", "description"]
    }
)

data = response.json()
for uri, props in data['entities'].items():
    print(f"{uri}: {props}")
```

---

## JavaScript Examples

### Search with Filters

```javascript
const BASE_URL = 'http://localhost:8000';

// Faceted search
const response = await fetch(`${BASE_URL}/api/v1/models/search?` + new URLSearchParams({
  query: 'image classification',
  filters: JSON.stringify({ license: ['MIT'], mlTask: ['image-classification'] }),
  facets: JSON.stringify(['mlTask', 'license', 'keywords']),
  page: 1,
  page_size: 50
}));

const data = await response.json();
console.log(`Found ${data.total} models`);
console.log('ML Task facets:', data.facets.mlTask);
```

### Graph Exploration

```javascript
const response = await fetch(`${BASE_URL}/api/v1/graph/bert-base-uncased?` + new URLSearchParams({
  entity_type: 'MLModel',
  depth: '2',
  direction: 'outgoing',
  relationships: ['HAS_LICENSE', 'dataset']
}));

const graph = await response.json();
console.log(`Found ${graph.metadata.node_count} nodes`);
console.log(`Found ${graph.metadata.edge_count} edges`);
```

---

## cURL Examples

### List Models

```bash
curl http://localhost:8000/api/v1/models
```

### Search Models

```bash
curl "http://localhost:8000/api/v1/models?search=transformer&page=1&page_size=10"
```

### Get Model Details

```bash
curl "http://localhost:8000/api/v1/models/https%3A%2F%2Fw3id.org%2Fmlentory%2Fmodel%2Fabc123?resolve_properties=HAS_LICENSE&resolve_properties=dataset"
```

### Faceted Search

```bash
curl "http://localhost:8000/api/v1/models/search?query=image+classification&filters=%7B%22license%22%3A%5B%22MIT%22%5D%7D"
```

### Get Facet Configuration

```bash
curl http://localhost:8000/api/v1/models/facets/config
```

### Get Facet Values

```bash
curl "http://localhost:8000/api/v1/models/facets/values?field=keywords&search_query=medical&limit=20"
```

### Graph Exploration

```bash
curl "http://localhost:8000/api/v1/graph/bert-base-uncased?entity_type=MLModel&depth=2&direction=outgoing"
```

### Platform Statistics

```bash
curl http://localhost:8000/api/v1/stats/platform
```

---

## Advanced Examples

### Pagination

```python
def get_all_models(base_url, search_query=None):
    """Fetch all models with pagination."""
    page = 1
    all_models = []
    
    while True:
        params = {"page": page, "page_size": 100}
        if search_query:
            params["search"] = search_query
        
        response = requests.get(f"{base_url}/api/v1/models", params=params)
        data = response.json()
        
        all_models.extend(data['results'])
        
        if not data.get('next'):
            break
        
        page += 1
    
    return all_models

# Usage
models = get_all_models("http://localhost:8000", search_query="bert")
print(f"Total models: {len(models)}")
```

### Error Handling

```python
import requests
from requests.exceptions import RequestException

def safe_api_call(url, params=None):
    """Make API call with error handling."""
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except RequestException as e:
        print(f"Request failed: {e}")
        return None
    except ValueError as e:
        print(f"Invalid JSON response: {e}")
        return None

# Usage
data = safe_api_call("http://localhost:8000/api/v1/models", {"page": 1})
if data:
    print(f"Found {data['count']} models")
```

---

## Next Steps

- **[Quick Start Guide](../../getting-started/quickstart.md)** → Set up the API
- **[API Usage Guide](quickstart.md)** → Basic usage guide
- **[API Endpoints](../endpoints/models.md)** → Complete endpoint reference
- **[API Reference](../reference/schemas.md)** → Response schemas

