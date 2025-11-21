# Quick Start

Get the MLentory ETL pipeline up and running in 5 minutes! This guide assumes you have Docker and Docker Compose installed.

## Prerequisites

Before starting, ensure you have:

- ✅ **Docker** (version 20.10+) installed and running
- ✅ **Docker Compose** (version 2.0+) installed (usually comes with Docker Desktop)
- ✅ At least **8GB RAM** available (Neo4j and Elasticsearch need memory)
- ✅ **Git** installed (to clone the repository)

### Installing Docker (If Needed)

If you don't have Docker installed:

**Linux:**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER  # Optional: run without sudo
```

**macOS/Windows:**
- Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop)

### Verify Docker Installation

```bash
docker --version
docker compose version
```

If these commands work, you're ready to proceed!

## Step 1: Clone the Repository

```bash
git clone https://github.com/zbmed-semtec/mlentory_etl_backend.git
cd mlentory_etl_backend
```

## Step 2: Configure Environment Variables

Create your environment file from the template:

```bash
cp .env.example .env
```

For a quick start, the default values in `.env.example` should work. You can customize them later if needed.

## Step 3: Start All Services

Start all required services (Neo4j, Elasticsearch, Dagster) with one command:

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
Elasticsearch: http://localhost:9200
```

## Step 4: Verify Services Are Running

Check that all services are up:

```bash
docker compose ps
```

You should see all services with status "Up" or "running".

### Access the Services

Once started, you can access:

- **Dagster UI**: [http://localhost:3000](http://localhost:3000)
  - This is where you'll run and monitor your ETL pipelines
- **Neo4j Browser**: [http://localhost:7474](http://localhost:7474)
  - Explore the knowledge graph of ML models
- **Elasticsearch**: [http://localhost:9201](http://localhost:9201)
  - Check the search index status

## Step 5: Run Your First Extraction

Open the Dagster UI at http://localhost:3000 and:

1. Navigate to the **Assets** tab
2. Find an extractor asset (e.g., `extract_huggingface_models`)
3. Click **Materialize** to run your first extraction

Or use the command line:

```bash
# Run a specific extractor
make extract SOURCE=huggingface

# Or run the full ETL pipeline
make etl-run
```

## What's Next?

Congratulations! You've successfully started the MLentory ETL pipeline. Now you can:

- **[Configure your environment](configuration.md)** - Customize settings for your needs
- **[Run your first pipeline](first-run.md)** - Detailed guide on executing extractions
- **[Explore the architecture](../architecture/overview.md)** - Understand how everything works

## Troubleshooting

### Services won't start

- **Check Docker is running**: `docker ps`
- **Check port availability**: Ensure ports 3000, 7474, 7687, 9200, 9201 are not in use
- **View logs**: `docker compose logs` to see what's happening

### Out of memory errors

- Neo4j and Elasticsearch need significant RAM
- Try reducing memory allocation in `docker-compose.yml` or close other applications
- Minimum recommended: 8GB total system RAM

### Can't access Dagster UI

- Wait a minute for services to fully start
- Check logs: `docker compose logs dagster-webserver`
- Verify the service is running: `docker compose ps dagster-webserver`

For more detailed troubleshooting, see the [Operations section](../operations/troubleshooting.md).
