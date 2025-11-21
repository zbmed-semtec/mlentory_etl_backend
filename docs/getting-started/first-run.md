# First Run

This guide walks you through executing your first successful ETL pipeline run. By the end, you'll have extracted, transformed, and loaded ML model metadata into Neo4j and Elasticsearch.

## Prerequisites

Before running your first pipeline, ensure:

- ✅ All services are running (see [Quick Start](quickstart.md))
- ✅ Configuration is set up (see [Configuration](configuration.md))
- ✅ You can access the Dagster UI at http://localhost:3000

## Step 1: Verify Services Are Running

Check that all required services are up:

```bash
docker compose ps
```

You should see:
- `mlentory-neo4j` - Status: Up
- `mlentory-elasticsearch` - Status: Up  
- `mlentory-dagster-webserver` - Status: Up
- `mlentory-dagster-postgres` - Status: Up

If any service is not running, start them:

```bash
make up
# or
docker compose up -d
```

## Step 2: Access Dagster UI

Open your browser and navigate to:

**http://localhost:3000**

You should see the Dagster UI with:
- **Assets** tab - Shows all available ETL assets
- **Jobs** tab - Shows pipeline jobs
- **Runs** tab - Shows execution history
- **Schedules** tab - Shows scheduled pipelines

## Step 3: Explore Available Assets

In the Dagster UI, click on the **Assets** tab. You'll see assets organized by source:

### Extraction Assets

- `extract_huggingface_models` - Extract models from HuggingFace
- `extract_openml_models` - Extract models from OpenML
- `extract_ai4life_models` - Extract models from AI4Life

### Transformation Assets

- `transform_huggingface_models` - Transform HF data to FAIR4ML
- `transform_openml_models` - Transform OpenML data to FAIR4ML

### Loading Assets

- `load_neo4j_huggingface` - Load HF models into Neo4j
- `load_elasticsearch_huggingface` - Index HF models in Elasticsearch
- `export_rdf_huggingface` - Export HF models as RDF

## Step 4: Run Your First Extraction

### Option A: Using Dagster UI (Recommended for Beginners)

1. **Navigate to Assets** tab
2. **Find an extractor asset** (e.g., `extract_huggingface_models`)
3. **Click on the asset** to see details
4. **Click "Materialize"** button
5. **Select materialization options**:
   - Choose which partitions to run (if applicable)
   - Review configuration
6. **Click "Materialize"** to start

You'll see the run progress in real-time with logs and status updates.

### Option B: Using Command Line

For HuggingFace extraction:

```bash
make extract SOURCE=huggingface
```

For OpenML extraction:

```bash
make extract SOURCE=openml
```

### Option C: Run Full ETL Pipeline

To run the complete pipeline (extract → transform → load):

```bash
make etl-run
```

This executes all stages in sequence for all configured sources.

## Step 5: Monitor the Run

### In Dagster UI

1. **Go to Runs tab** to see execution history
2. **Click on your run** to see detailed progress
3. **View logs** for each asset execution
4. **Check for errors** or warnings

### Via Command Line

```bash
# View all logs
make logs

# View only Dagster logs
make logs-dagster

# Follow logs in real-time
docker compose logs -f dagster-webserver
```

## Step 6: Verify Results

### Check Extracted Data

Raw extracted data is stored in `/data/raw/<source>/`:

```bash
# List extracted files
ls -lh data/raw/huggingface/

# View a sample file
cat data/raw/huggingface/*.json | head -50
```

### Check Normalized Data

FAIR4ML normalized data is in `/data/normalized/<source>/`:

```bash
# List normalized files
ls -lh data/normalized/huggingface/

# View a sample normalized model
cat data/normalized/huggingface/*.json | jq '.[0]' | head -100
```

### Check Neo4j Database

**Option 1: Using Neo4j Browser**

1. Open http://localhost:7474
2. Log in with your Neo4j credentials
3. Run a query to see loaded models:

```cypher
MATCH (m:MLModel)
RETURN m.name, m.platform, m.mlTask
LIMIT 10
```

**Option 2: Using Cypher Shell**

```bash
docker compose exec neo4j cypher-shell -u neo4j -p your_password
```

Then run:
```cypher
MATCH (m:MLModel)
RETURN count(m) as total_models;
```

### Check Elasticsearch Index

**Check if index exists:**

```bash
curl http://localhost:9201/hf_models
```

**Search for models:**

```bash
curl -X GET "http://localhost:9201/hf_models/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match_all": {}
    },
    "size": 5
  }'
```

**Count indexed documents:**

```bash
curl http://localhost:9201/hf_models/_count
```

### Check RDF Export

RDF files are exported to `/data/rdf/<source>/`:

```bash
# List RDF files
ls -lh data/rdf/huggingface/

# View a sample RDF file
head -50 data/rdf/huggingface/*.ttl
```

## Understanding the Output

### What Happened?

1. **Extraction**: Fetched raw metadata from the source (e.g., HuggingFace Hub)
2. **Transformation**: Converted raw data to FAIR4ML schema format
3. **Loading**: 
   - Created nodes and relationships in Neo4j
   - Indexed documents in Elasticsearch
   - Exported RDF/Turtle files

### Expected Results

After a successful run, you should have:

- ✅ Raw JSON files in `data/raw/<source>/`
- ✅ Normalized JSON files in `data/normalized/<source>/`
- ✅ Models visible in Neo4j Browser
- ✅ Documents indexed in Elasticsearch
- ✅ RDF files in `data/rdf/<source>/`

## Common Issues and Solutions

### Extraction Fails

**Issue**: Extractor times out or fails

**Solutions**:
- Check network connectivity
- Verify source API is accessible
- Reduce extraction limit: Set `HF_EXTRACTION_LIMIT=10` in `.env`
- Check logs: `docker compose logs dagster-webserver`

### Transformation Errors

**Issue**: Validation errors during transformation

**Solutions**:
- Check raw data format matches expected schema
- Review transformation logs for specific field errors
- Some models may be skipped if they don't meet FAIR4ML requirements (this is normal)

### Neo4j Connection Fails

**Issue**: Cannot connect to Neo4j

**Solutions**:
- Verify Neo4j is running: `docker compose ps neo4j`
- Check credentials in `.env` match Neo4j configuration
- Test connection: `curl http://localhost:7474`
- Check Neo4j logs: `docker compose logs neo4j`

### Elasticsearch Indexing Fails

**Issue**: Documents not appearing in Elasticsearch

**Solutions**:
- Verify Elasticsearch is running: `docker compose ps elasticsearch`
- Check Elasticsearch logs: `docker compose logs elasticsearch`
- Verify index exists: `curl http://localhost:9201/_cat/indices`
- Check for mapping errors in logs

## Next Steps

Now that you've successfully run your first pipeline:

1. **[Explore the architecture](../architecture/overview.md)** - Understand how everything works
2. **[Learn about extractors](../extractors/overview.md)** - Understand extraction process
3. **[Query the knowledge graph](../examples/neo4j-queries.md)** - Explore relationships in Neo4j
4. **[Search in Elasticsearch](../examples/elasticsearch-queries.md)** - Learn search capabilities
5. **[Run operations](../operations/running-pipelines.md)** - Learn about monitoring and scheduling

## Tips for Success

- **Start small**: Extract a few models first (`HF_EXTRACTION_LIMIT=10`)
- **Monitor logs**: Watch the Dagster UI logs to understand what's happening
- **Check data quality**: Review normalized files to ensure data looks correct
- **Explore incrementally**: Run extract → transform → load separately to understand each stage
- **Use the UI**: Dagster UI provides excellent visualization of dependencies and execution

Congratulations on running your first MLentory ETL pipeline! 🎉
