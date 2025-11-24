# MLentory API Quick Start Guide

Get the MLentory API up and running in 5 minutes.

## Prerequisites

- Docker and docker-compose installed
- Neo4j and Elasticsearch services running with data
- `.env` file configured (see `.env.example`)

## Start the API

### Option 1: Docker Compose (Recommended)

```bash
# From project root
docker-compose up -d api

# Check logs
docker-compose logs -f api

# Check health
curl http://localhost:8000/health
```

### Option 2: Local Development

```bash
# Install dependencies
poetry install

# Set environment variables
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your-password
export ELASTIC_HOST=localhost
export ELASTIC_PORT=9201
export ELASTIC_USER=elastic
export ELASTIC_PASSWORD=changeme
export ELASTIC_HF_MODELS_INDEX=hf_models

# Run the API
poetry run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## First API Calls

### 1. Check API Health

```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "elasticsearch": true,
  "neo4j": true
}
```

### 2. List Models (First Page)

```bash
curl http://localhost:8000/api/v1/models
```

**Expected Response:**
```json
{
  "count": 150,
  "next": "/api/v1/models?page=2",
  "prev": null,
  "results": [
    {
      "db_identifier": "https://w3id.org/mlentory/model/abc123",
      "name": "bert-base-uncased",
      "description": "BERT base model, uncased",
      "sharedBy": "google",
      "license": "apache-2.0",
      "mlTask": ["fill-mask"],
      "keywords": ["bert", "transformer"],
      "platform": "Hugging Face"
    }
    // ... more models
  ]
}
```

### 3. Search for Models

```bash
curl "http://localhost:8000/api/v1/models?search=bert&page_size=5"
```

### 4. Get Model Details

```bash
# Get basic model info
MODEL_ID="https://w3id.org/mlentory/model/abc123"
curl "http://localhost:8000/api/v1/models/${MODEL_ID}"

# Get model with related entities
curl "http://localhost:8000/api/v1/models/${MODEL_ID}?include_entities=license&include_entities=datasets"
```

## Interactive Documentation

Open your browser and visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

You can test all endpoints directly from the Swagger UI!

## Common Use Cases

### Search and Filter

```bash
# Search for "transformer" models
curl "http://localhost:8000/api/v1/models?search=transformer"

# Get page 3 with 50 results per page
curl "http://localhost:8000/api/v1/models?page=3&page_size=50"
```

### Get Full Model Information

```bash
# Get model with all relationships
MODEL_ID="https://w3id.org/mlentory/model/abc123"
curl "http://localhost:8000/api/v1/models/${MODEL_ID}?include_entities=license&include_entities=datasets&include_entities=articles&include_entities=keywords&include_entities=tasks&include_entities=languages"
```

### Python Client Example

```python
import requests

# Search for models
response = requests.get(
    "http://localhost:8000/api/v1/models",
    params={"search": "bert", "page_size": 10}
)
data = response.json()

print(f"Found {data['count']} models")
for model in data['results']:
    print(f"- {model['name']}")

# Get detailed model info
model_id = data['results'][0]['db_identifier']
detail_response = requests.get(
    f"http://localhost:8000/api/v1/models/{model_id}",
    params={"include_entities": ["license", "datasets"]}
)
model = detail_response.json()

print(f"\nModel: {model['name']}")
print(f"Description: {model.get('description', 'N/A')}")
if model['related_entities']['license']:
    print(f"License: {model['related_entities']['license']['name']}")
```

## Troubleshooting

### API Won't Start

**Check logs:**
```bash
docker-compose logs api
```

**Common issues:**
- Missing environment variables (check `.env` file)
- Elasticsearch not running
- Neo4j not running
- Port 8000 already in use

### Empty Results

**Verify data exists:**
```bash
# Check Elasticsearch
curl http://localhost:9201/_cat/indices

# Check Neo4j (open browser)
# http://localhost:7474
# Run: MATCH (m:MLModel) RETURN count(m)
```

**Solution:** Run the ETL pipeline to load data first.

### Connection Errors

**Elasticsearch connection failed:**
```bash
# Check Elasticsearch is running
docker-compose ps elasticsearch

# Test connection
curl http://localhost:9201/_cluster/health
```

**Neo4j connection failed:**
```bash
# Check Neo4j is running
docker-compose ps neo4j

# Test connection (requires username/password)
curl -u neo4j:your-password http://localhost:7474/db/data/
```

## Next Steps

- Read the full [README.md](./README.md) for detailed API documentation
- Explore [ARCHITECTURE.md](./ARCHITECTURE.md) to understand how it works
- Check out the [main project README](../README.md) for ETL pipeline info
- View interactive API docs at http://localhost:8000/docs

## Getting Help

- Check the logs: `docker-compose logs -f api`
- Open an issue on GitHub
- Review the [troubleshooting section](./README.md#troubleshooting) in the main README

## Development Tips

### Hot Reload

When running with `--reload`, the API automatically restarts when you change code:

```bash
# Start with hot reload
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Now edit any .py file in api/ and it will auto-reload!
```

### Testing Changes

```bash
# Make a change to api/routers/models.py
# Test immediately without restart
curl http://localhost:8000/api/v1/models
```

### Adding a New Endpoint

1. Add endpoint function to appropriate router (e.g., `routers/models.py`)
2. Add response schema to `schemas/responses.py` if needed
3. Test at http://localhost:8000/docs (automatic documentation!)
4. Update [README.md](./README.md) with new endpoint details

### Code Style

Format code before committing:
```bash
# Format with black
poetry run black api/

# Check with ruff
poetry run ruff check api/

# Type check with mypy
poetry run mypy api/
```

## Quick Reference Card

| Action | Command |
|--------|---------|
| Start API | `docker-compose up -d api` |
| View logs | `docker-compose logs -f api` |
| Stop API | `docker-compose stop api` |
| Restart API | `docker-compose restart api` |
| List models | `curl http://localhost:8000/api/v1/models` |
| Search | `curl "http://localhost:8000/api/v1/models?search=bert"` |
| Get model | `curl "http://localhost:8000/api/v1/models/MODEL_ID"` |
| Health check | `curl http://localhost:8000/health` |
| API docs | Open http://localhost:8000/docs |
