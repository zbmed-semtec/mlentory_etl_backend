# Running ETL Pipelines by Tag

This document describes how to run the MLentory ETL pipelines using Dagster tags, specifically the `pipeline` tag.

## Overview

All assets in the MLentory ETL are tagged with pipeline identifiers:
- `pipeline: hf_etl` - HuggingFace extraction, transformation, and loading pipeline
- `pipeline: openml_etl` - OpenML extraction pipeline
- `pipeline: ai4life_etl` - AI4Life extraction pipeline

## Quick Start

### Run HuggingFace ETL Pipeline

The simplest way to run the complete HuggingFace ETL pipeline:

```bash
# Using Makefile (recommended)
make hf-etl

# Or using Docker Compose directly
docker compose exec dagster-webserver dagster asset materialize -t pipeline:hf_etl
```

## Command Reference

### Using Makefile (Recommended)

#### Run HuggingFace ETL Pipeline
```bash
make hf-etl
```

This command runs all assets tagged with `pipeline: hf_etl`, which includes:
- Extraction assets (hf_run_folder, hf_raw_models, etc.)
- Transformation assets (hf_models_normalized, etc.)
- Loading assets (Neo4j and Elasticsearch loaders)

#### Run Any Pipeline by Tag
```bash
# Run OpenML pipeline
make run-by-tag TAG="pipeline:openml_etl"

# Run AI4Life pipeline
make run-by-tag TAG="pipeline:ai4life_etl"

# Run HuggingFace pipeline (alternative to make hf-etl)
make run-by-tag TAG="pipeline:hf_etl"
```

### Using Docker Compose Directly

#### Run by Tag Filter
```bash
# Run all assets with pipeline:hf_etl tag
docker compose exec dagster-webserver dagster asset materialize -t pipeline:hf_etl

# Run all assets with pipeline:openml_etl tag
docker compose exec dagster-webserver dagster asset materialize -t pipeline:openml_etl

# Run all assets with pipeline:ai4life_etl tag
docker compose exec dagster-webserver dagster asset materialize -t pipeline:ai4life_etl
```

#### Run with Multiple Tags
```bash
# Run assets that match both tags (AND condition)
docker compose exec dagster-webserver dagster asset materialize -t pipeline:hf_etl -t stage:load

# This will run only loading assets from the HF pipeline
```

#### Run with JSON Tag Format
```bash
# Alternative format using JSON tags
docker compose exec dagster-webserver dagster asset materialize --tags '{"pipeline": "hf_etl"}'
```

### Using Dagster UI

1. Navigate to http://localhost:3000
2. Go to **Assets** tab
3. Use the filter/search bar to filter by tag: `pipeline:hf_etl`
4. Select the assets you want to materialize
5. Click **Materialize** button

### Using Dagster CLI (Inside Container)

If you're already inside the Dagster container:

```bash
# Enter the container
docker compose exec dagster-webserver /bin/bash

# Then run commands directly
dagster asset materialize -t pipeline:hf_etl
```

## Pipeline Stages

The HuggingFace ETL pipeline (`pipeline: hf_etl`) consists of three main stages:

### 1. Extraction Stage
Assets tagged with `pipeline: hf_etl` (extraction):
- `hf_run_folder` - Creates run-specific output directory
- `hf_raw_models_latest` - Extracts latest models
- `hf_raw_models_from_file` - Extracts models from file
- `hf_raw_models` - Merges model data
- Various enrichment assets (datasets, articles, keywords, etc.)

### 2. Transformation Stage
Assets tagged with `pipeline: hf_etl` (transformation):
- `hf_models_normalized` - Normalizes models to FAIR4ML schema
- Various property extraction assets

### 3. Loading Stage
Assets tagged with `pipeline: hf_etl` and `stage: load`:
- Neo4j loading assets
- Elasticsearch indexing assets
- RDF export assets

## Running Specific Stages

### Run Only Extraction
```bash
# Using asset group
docker compose exec dagster-webserver dagster asset materialize --select "hf/*" -t pipeline:hf_etl

# Or using Makefile (if you have a specific command)
make extract SOURCE=huggingface
```

### Run Only Transformation
```bash
# Using Makefile
make transform SOURCE=huggingface

# Or using asset selection
docker compose exec dagster-webserver dagster asset materialize --select "hf_models_normalized+"
```

### Run Only Loading
```bash
# Using multiple tags
docker compose exec dagster-webserver dagster asset materialize -t pipeline:hf_etl -t stage:load

# Or using Makefile
make load SOURCE=huggingface
```

## Advanced Usage

### Run with Dependencies
```bash
# Run an asset and all its upstream dependencies
docker compose exec dagster-webserver dagster asset materialize --select "hf_models_normalized+"
```

### Run Specific Assets
```bash
# Run specific assets by name
docker compose exec dagster-webserver dagster asset materialize --select "hf_run_folder hf_raw_models"
```

### Dry Run (Preview)
```bash
# See what would be executed without actually running
docker compose exec dagster-webserver dagster asset materialize -t pipeline:hf_etl --dry-run
```

### Run with Partitions (if configured)
```bash
# Run specific partition
docker compose exec dagster-webserver dagster asset materialize -t pipeline:hf_etl --partition "2025-01-01"
```

## Monitoring Runs

### View Run Status
```bash
# View logs
docker compose logs -f dagster-webserver

# Or use Dagster UI at http://localhost:3000
```

### Check Run History
```bash
# List recent runs
docker compose exec dagster-webserver dagster run list --limit 10
```

## Troubleshooting

### Assets Not Found
If you get "No assets found" error:
1. Verify the tag exists: `docker compose exec dagster-webserver dagster asset list`
2. Check tag format: Use `pipeline:hf_etl` not `pipeline=hf_etl`
3. Ensure Dagster has loaded the repository correctly

### Container Not Running
```bash
# Check service status
docker compose ps

# Start services if needed
make up
```

### Permission Issues
```bash
# Fix permissions (if needed)
sudo chown -R 1000:1000 ./config
sudo chmod -R 775 ./config
```

## Examples

### Complete HF ETL Run
```bash
# Run the entire pipeline
make hf-etl

# Monitor progress
docker compose logs -f dagster-webserver
```

### Run Only New Models
```bash
# Extract only latest models (without file-based extraction)
docker compose exec dagster-webserver dagster asset materialize --select "hf_run_folder hf_raw_models_latest"
```

### Run Only Indexing
```bash
# Run only Elasticsearch indexing
docker compose exec dagster-webserver dagster asset materialize -t pipeline:hf_etl -t stage:index
```

## See Also

- [Dagster Asset Tagging Documentation](https://docs.dagster.io/concepts/assets/software-defined-assets#tagging-assets)
- [Dagster CLI Reference](https://docs.dagster.io/_apidocs/cli)
- [Project README](../README.md)
- [Architecture Overview](architecture.md)

