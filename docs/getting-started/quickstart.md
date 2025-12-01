# Quick Start

Get MLentory up and running! 

This guide walks you through setting up both components in the correct order:

1. **Infrastructure Setup** - Start core services (Neo4j, Elasticsearch, Dagster)
2. **ETL Pipeline** - Extract, transform and load data (must run first to populate the database)
3. **Backend API** - Start the REST API to query the loaded data

> **Important:** The Backend API requires data from the ETL pipeline. You must run the ETL pipeline at least once before the API can serve data.

---

## Prerequisites

Before starting, ensure you have:

✅ **Docker** (version 20.10+) installed and running

✅ **Docker Compose** (version 2.0+) installed (usually comes with Docker Desktop)

✅ At least **8GB RAM** available (Neo4j and Elasticsearch need memory)

✅ **Git** installed (to clone the repository)

### 📦 Installing Docker (If Needed)

If you don't have Docker installed:

**Linux:**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER  # Optional: run without sudo
```

**macOS/Windows:**
- Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop)

### ✅ Verify Docker Installation

```bash
docker --version
docker compose version
```

If these commands work, you're ready to proceed!

---

## Step 1: Clone and Configure

### 📥 Clone the Repository

```bash
git clone https://github.com/zbmed-semtec/mlentory_etl_backend.git
cd mlentory_etl_backend
```

### ⚙️ Configure Environment Variables

Create your environment file from the template:

```bash
cp .env.example .env
```

For a quick start, the default values in `.env.example` should work. You can customize them later if needed.

> **Note:** For detailed configuration options, see [Configuration Guide](configuration.md).

---

## Step 2: Start Infrastructure Services

Start all required infrastructure services (Neo4j, Elasticsearch, Dagster) with one command:

```bash
make up
```

Or using Docker Compose directly:

```bash
docker compose up -d
```

This will:
- Pull required Docker images (if not already present)
- Start Neo4j database
- Start Elasticsearch indexer
- Start Dagster webserver and daemon
- Set up the network and volumes

**Expected output:**
```
Starting MLentory ETL services...
Services started!
Dagster UI: http://localhost:3000
Neo4j Browser: http://localhost:7474
Elasticsearch: http://localhost:9201
```

### ✅ Verify Services Are Running

Check that all services are up:

```bash
docker compose ps
```

You should see all services with status "Up" or "running".

### 🌐 Access the Services

Once started, you can access:

**Dagster UI**: [http://localhost:3000](http://localhost:3000)
    - This is where you'll run and monitor your ETL pipelines
    
**Neo4j Browser**: [http://localhost:7474](http://localhost:7474)
    - Explore the knowledge graph of ML models

**Elasticsearch**: [http://localhost:9201](http://localhost:9201)
    - Check the search index status

> **💡 New to these tools?** If you're unfamiliar with Dagster, Neo4j, or Elasticsearch, check out the [Key Concepts Tutorial](../concepts-tutorial.md) for quick beginner-friendly explanations.

---

## Step 3: Run ETL Pipeline (Required First)

> **⚠️ Important:** The Backend API depends on data from the ETL pipeline. You must complete this step before starting the API.

The ETL pipeline extracts, transforms, and loads ML model metadata into Neo4j and Elasticsearch.

### 🖥️ Quick Option: Run via Dagster UI

The ETL pipeline is split into separate assets for each stage. To run the **complete ETL pipeline** (extract → transform → load), materialize the loading assets with dependencies (`+`), which will automatically run all upstream assets:

1. Open the Dagster UI at [http://localhost:3000](http://localhost:3000)
2. Navigate to the **Assets** tab
3. Find and materialize the loading assets with dependencies:
    - `hf_load_models_to_neo4j+` - Loads normalized data into Neo4j (automatically runs extract → transform → load)
    - `hf_index_models_elasticsearch+` - Indexes normalized data in Elasticsearch (automatically runs extract → transform → index)
   
   **Note:** Each asset handles one ETL step:
   
   - **Extract**: `hf_raw_models` - Extracts raw models from HuggingFace platform
   - **Transform**: `hf_models_normalized` - Transforms raw data into FAIR4ML format
   - **Load**: `hf_load_models_to_neo4j` - Loads normalized data into Neo4j (for graph queries)
   - **Index**: `hf_index_models_elasticsearch` - Indexes normalized data in Elasticsearch (for search)
   
   Materializing with `+` automatically runs all upstream dependencies, executing the full pipeline: extraction → transformation → loading/indexing

> **Note:** The API needs data in **both** Neo4j and Elasticsearch, so you need to materialize both loading assets. Materializing with dependencies (`+`) will run the complete pipeline.

### 💻 Alternative: Run via Command Line (Recommended)

The easiest way is to use the Makefile command which runs the complete pipeline:

```bash
# Run the full ETL pipeline (extract → transform → load)
# This runs everything needed for the API to work
make etl-run
```

Or manually materialize both loading assets:

```bash
# Materialize both loading assets with all dependencies
docker compose exec dagster-webserver dagster asset materialize \
  -a hf_load_models_to_neo4j+ \
  -a hf_index_models_elasticsearch+
```

### ✅ Verify Data Was Loaded

After the ETL pipeline completes, verify data is in Neo4j:

```bash
# Check Neo4j via browser at http://localhost:7474
# Run this query:
MATCH (m:MLModel)
RETURN count(m) as total_models
LIMIT 10
```

Or check Elasticsearch:

```bash
curl http://localhost:9201/hf_models/_count
```

---

## Step 4: Start Backend API

Once you have data loaded from the ETL pipeline, start the Backend API:

### 🚀 Start API Service

#### Option 1: Docker Compose (Recommended)

```bash
# Start the API service (and its dependencies: neo4j, elasticsearch)
docker compose up -d api

# Alternative: Start all services with the "api" profile (same result)
docker compose --profile api up -d
```

#### Option 2: Local Development

If you prefer to run the API locally (without Docker):

```bash
# Install dependencies
poetry install

# Set environment variables (or use .env file)
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

> **Note:** When running locally, the API will be on port 8000 (not 8008).

### ✅ Verify API is Running

Check the API health endpoint:

```bash
curl http://localhost:8008/health
```

> **Note:** The API is mapped to port 8008 in docker-compose (8008:8000). If running locally, it may be on port 8000.

**Expected Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "elasticsearch": true,
  "neo4j": true
}
```

### 📚 Access API Documentation

The API provides interactive documentation:

- **Swagger UI**: [http://localhost:8008/docs](http://localhost:8008/docs)
- **ReDoc**: [http://localhost:8008/redoc](http://localhost:8008/redoc)

### 🧪 Test the API

Try listing models:

```bash
curl http://localhost:8008/api/v1/models?page=1&page_size=10
```

> **For more API usage examples**, see the [API Usage Guide](../backend-api/usage/quickstart.md).

---

## Step 5: Verify Everything Works

### ✅ Check ETL Pipeline

- ✅ Dagster UI accessible at http://localhost:3000
- ✅ Can see assets and run extractions
- ✅ Data visible in Neo4j Browser
- ✅ Data indexed in Elasticsearch

### ✅ Check Backend API

- ✅ API health check returns `"status": "healthy"`
- ✅ Can list models via API
- ✅ Interactive docs accessible at http://localhost:8008/docs

---

## What's Next?

### 📚 New to These Concepts?

If you're unfamiliar with schemas, Dagster, Neo4j, or Elasticsearch:

- **[Key Concepts Tutorial](../concepts-tutorial.md)** → Quick beginner-friendly tutorials

### 🔄 For ETL Pipeline

- **[Configuration Guide](configuration.md)** → Customize settings for your needs
- **[ETL Architecture](../architecture/overview.md)** → Understand how everything works

### 🌐 For Backend API

- **[API Overview](../backend-api/overview.md)** → Understand the API structure
- **[API Usage Guide](../backend-api/usage/quickstart.md)** → Start using the API
- **[API Endpoints](../backend-api/endpoints/models.md)** → Explore available endpoints
- **[API Examples](../backend-api/usage/examples.md)** → See code examples

---

## Troubleshooting

### ⚠️ Services won't start

- **Check Docker is running**: `docker ps`
- **Check port availability**: Ensure ports 3000, 7474, 7687, 9200, 9201, 8008 are not in use
- **View logs**: `docker compose logs` to see what's happening

### 💾 Out of memory errors

- Neo4j and Elasticsearch need significant RAM
- Try reducing memory allocation in `docker-compose.yml` or close other applications
- Minimum recommended: 8GB total system RAM

### ⚠️ API returns empty results

- **Ensure ETL pipeline has run**: The API needs data from the ETL pipeline
- **Check Neo4j has data**: Query Neo4j Browser to verify models exist
- **Check Elasticsearch index**: Verify index exists and has documents

### ❌ Can't access services

- Wait a minute for services to fully start
- Check logs: `docker compose logs <service-name>`
- Verify the service is running: `docker compose ps <service-name>`

For more detailed troubleshooting, see the [Operations section](../operations/troubleshooting.md).

---

## Summary

You've successfully set up MLentory! Here's what you accomplished:

1. ✅ Started infrastructure services (Neo4j, Elasticsearch, Dagster)
2. ✅ Ran ETL pipeline to extract and load data
3. ✅ Started Backend API to query the data
4. ✅ Verified everything is working

**Next Steps:**
- Check out the [API documentation](../backend-api/overview.md)
- Learn about the [architecture](../architecture/overview.md)
