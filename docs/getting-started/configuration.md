# Configuration

Learn how to configure the MLentory ETL pipeline for your environment. All configuration is managed through environment variables.

## Configuration File

The pipeline uses a `.env` file for configuration. Start by copying the example file:

```bash
cp .env.example .env
```

Then edit `.env` with your preferred settings.

## Environment Variables

### Required Variables

These variables must be set for the pipeline to function:

#### Neo4j Configuration

```bash
NEO4J_URI=bolt://mlentory-neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_secure_password_here
NEO4J_DATABASE=neo4j
```

- **NEO4J_URI**: Connection URI for Neo4j
  - Docker: `bolt://mlentory-neo4j:7687` (uses service name)
  - Local: `bolt://localhost:7687`
- **NEO4J_USER**: Username for Neo4j authentication
- **NEO4J_PASSWORD**: Password for Neo4j (use a strong password in production!)
- **NEO4J_DATABASE**: Database name (default: `neo4j`)

#### Elasticsearch Configuration

```bash
ELASTIC_HOST=mlentory-elasticsearch
ELASTIC_PORT=9201
ELASTIC_SCHEME=http
ELASTIC_USER=elastic
ELASTIC_PASSWORD=changeme
ELASTIC_HF_MODELS_INDEX=hf_models
```

- **ELASTIC_HOST**: Elasticsearch hostname
  - Docker: `mlentory-elasticsearch` (service name)
  - Local: `localhost`
- **ELASTIC_PORT**: Elasticsearch port (default: `9201` in Docker, `9200` locally)
- **ELASTIC_SCHEME**: Connection scheme (`http` or `https`)
- **ELASTIC_USER**: Username (optional, for secured Elasticsearch)
- **ELASTIC_PASSWORD**: Password (optional, for secured Elasticsearch)
- **ELASTIC_HF_MODELS_INDEX**: Index name for HuggingFace models (default: `hf_models`)

#### Dagster Configuration

```bash
DAGSTER_HOME=/opt/dagster/dagster_home
DAGSTER_POSTGRES_USER=dagster
DAGSTER_POSTGRES_PASSWORD=dagster_password_change_me
DAGSTER_POSTGRES_DB=dagster
DAGSTER_POSTGRES_HOST=dagster-postgres
```

- **DAGSTER_HOME**: Path to Dagster workspace directory
- **DAGSTER_POSTGRES_***: PostgreSQL connection details for Dagster metadata storage

### Optional Variables

These have sensible defaults but can be customized:

#### Data Storage

```bash
DATA_DIR=/data
```

- **DATA_DIR**: Base directory for storing extracted, normalized, and RDF data
  - Default: `/data` (in Docker containers)
  - Creates subdirectories: `raw/`, `normalized/`, `rdf/`

#### API Keys and Authentication

```bash
# HuggingFace API Token (optional but recommended)
HF_TOKEN=your_huggingface_token_here
# Alternative: HUGGINGFACE_HUB_TOKEN=your_huggingface_token_here
```

- **HF_TOKEN** or **HUGGINGFACE_HUB_TOKEN**: HuggingFace API token (optional)
  - **Why use it?**: Higher rate limits, access to private models, better reliability
  - **How to get**: Create a token at https://huggingface.co/settings/tokens
  - **Note**: The `huggingface_hub` library automatically reads this from environment variables
  - **Without token**: Works for public models but with lower rate limits

#### Extraction Configuration

```bash
# HuggingFace extraction
HF_NUM_MODELS=50
HF_UPDATE_RECENT=true
HF_THREADS=4
HF_MODELS_FILE_PATH=/data/refs/hf_model_ids.txt
HF_BASE_MODEL_ITERATIONS=1
HF_ENRICHMENT_THREADS=4

# OpenML extraction
OPENML_NUM_INSTANCES=50
OPENML_OFFSET=0
OPENML_THREADS=4
OPENML_ENRICHMENT_THREADS=4
OPENML_ENABLE_SCRAPING=false

# AI4Life extraction
AI4LIFE_NUM_MODELS=50
AI4LIFE_BASE_URL=https://hypha.aicell.io
AI4LIFE_PARENT_ID=bioimage-io/bioimage.io
```

- **HF_NUM_MODELS**: Number of latest models to extract (default: `50`)
- **HF_UPDATE_RECENT**: Prioritize recently updated models (default: `true`)
- **HF_THREADS**: Number of parallel threads for HuggingFace extraction (default: `4`)
- **HF_MODELS_FILE_PATH**: Path to file containing specific model IDs to extract (default: `/data/refs/hf_model_ids.txt`)
- **HF_BASE_MODEL_ITERATIONS**: Number of iterations for recursive base model enrichment (default: `1`)
- **HF_ENRICHMENT_THREADS**: Threads for enrichment tasks (default: `4`)
- **OPENML_NUM_INSTANCES**: Number of instances to extract from OpenML (default: `50`)
- **OPENML_OFFSET**: Offset for pagination (default: `0`)
- **OPENML_THREADS**: Number of parallel threads for OpenML extraction (default: `4`)
- **OPENML_ENRICHMENT_THREADS**: Threads for OpenML enrichment (default: `4`)
- **OPENML_ENABLE_SCRAPING**: Enable web scraping for additional stats (default: `false`, ⚠️ slow)
- **AI4LIFE_NUM_MODELS**: Number of models to extract from AI4Life (default: `50`)
- **AI4LIFE_BASE_URL**: Base URL for AI4Life API (default: `https://hypha.aicell.io`)
- **AI4LIFE_PARENT_ID**: Parent ID for AI4Life extraction (default: `bioimage-io/bioimage.io`)

#### Port Configuration

```bash
DAGSTER_PORT=3000
NEO4J_BROWSER_PORT=7474
NEO4J_BOLT_PORT=7687
```

- **DAGSTER_PORT**: Port for Dagster UI (default: `3000`)
- **NEO4J_BROWSER_PORT**: Port for Neo4j Browser UI (default: `7474`)
- **NEO4J_BOLT_PORT**: Port for Neo4j Bolt protocol (default: `7687`)

## Configuration Examples

### Development Setup

For local development with Docker:

```bash
# .env for development
NEO4J_URI=bolt://mlentory-neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=dev_password_123
NEO4J_DATABASE=neo4j

ELASTIC_HOST=mlentory-elasticsearch
ELASTIC_PORT=9201
ELASTIC_SCHEME=http
ELASTIC_USER=elastic
ELASTIC_PASSWORD=changeme

# Optional: HuggingFace API token for higher rate limits
# HF_TOKEN=your_huggingface_token_here

DATA_DIR=/data
DAGSTER_HOME=/opt/dagster/dagster_home
```

### Production Setup

For production, use secure passwords and consider enabling authentication:

```bash
# .env for production
NEO4J_URI=bolt://neo4j.example.com:7687
NEO4J_USER=mlentory_user
NEO4J_PASSWORD=<strong_random_password>
NEO4J_DATABASE=mlentory_prod

ELASTIC_HOST=elasticsearch.example.com
ELASTIC_PORT=9200
ELASTIC_SCHEME=https
ELASTIC_USER=elastic
ELASTIC_PASSWORD=<strong_random_password>

# Recommended: HuggingFace API token for production
HF_TOKEN=<your_huggingface_token>

# Enable security features
# Set secure passwords for all services
# Use secrets management (Docker secrets, Kubernetes secrets, etc.)
# Store API tokens securely (never commit to git)
```

## Security Best Practices

### Never Commit Secrets

- ✅ Add `.env` to `.gitignore`
- ✅ Use `.env.example` as a template (without real passwords or API tokens)
- ✅ Use different passwords for development and production
- ✅ Rotate passwords and API tokens regularly
- ✅ Never commit API tokens or passwords to version control

### API Token Security

- **HuggingFace Token**: Store securely, use read-only tokens when possible
- **Token Scope**: Only grant necessary permissions (read access is sufficient for extraction)
- **Token Rotation**: Rotate tokens periodically for security
- **Environment Variables**: Prefer environment variables over hardcoding in code

### Production Security

- Use strong, randomly generated passwords
- Enable Elasticsearch security features
- Use HTTPS for Elasticsearch connections
- Consider using secrets management systems:
  - Docker secrets
  - Kubernetes secrets
  - AWS Secrets Manager
  - HashiCorp Vault

### Password Generation

Generate strong passwords:

```bash
# Using openssl
openssl rand -base64 32

# Using Python
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Verifying Configuration

After setting up your `.env` file, verify the configuration:

### Check Environment Variables

```bash
# In Docker container
docker compose exec dagster-webserver env | grep NEO4J
docker compose exec dagster-webserver env | grep ELASTIC
```

### Test Connections

**Test Neo4j:**
```bash
# From host
curl http://localhost:7474

# From container
docker compose exec dagster-webserver python -c "
from etl_loaders.rdf_store import Neo4jConfig
config = Neo4jConfig.from_env()
print(f'Neo4j URI: {config.uri}')
"
```

**Test Elasticsearch:**
```bash
# From host
curl http://localhost:9201

# From container
docker compose exec dagster-webserver python -c "
from etl_loaders.elasticsearch_store import ElasticsearchConfig
config = ElasticsearchConfig.from_env()
print(f'Elasticsearch: {config.scheme}://{config.host}:{config.port}')
"
```

## Troubleshooting Configuration

### Variables Not Loading

- Ensure `.env` file is in the project root
- Check for typos in variable names
- Restart services after changing `.env`: `docker compose restart`

### Connection Failures

- Verify service names match (for Docker networking)
- Check ports are not conflicting
- Ensure services are running: `docker compose ps`

### Permission Issues

- Check file permissions: `chmod 600 .env` (restrictive permissions)
- Verify Docker volumes have correct permissions

## Next Steps

Once configured:

- **[Run your first pipeline](first-run.md)** - Execute your first extraction
- **[Explore operations](../operations/running-pipelines.md)** - Learn about running and monitoring pipelines
