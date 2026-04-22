# MLentory ETL Backend

A modular data pipeline that extracts ML model metadata from the web, normalizes it into the FAIR4ML schema, stores it in Neo4j, and indexes it in Elasticsearch for fast discovery.

## 🎯 Overview

MLentory ETL is a Dagster-based orchestration platform designed to:
- **Extract** ML model metadata from multiple sources (HuggingFace, PapersWithCode, OpenML, etc.)
- **Transform** raw data into the FAIR4ML schema for standardization
- **Load** normalized data into Neo4j (graph storage) and Elasticsearch (search indexing)
- **Track** provenance and lineage for reproducibility

## 🏗️ Architecture

```
┌─────────────┐
│  Extractors │ → Raw JSON in /data/raw/<source>/
└─────────────┘
       ↓
┌─────────────┐
│Transformers │ → FAIR4ML normalized data in /data/normalized/<source>/
└─────────────┘
       ↓
┌─────────────┐
│   Loaders   │ → Neo4j (graph) + Elasticsearch (search) + RDF /data/rdf/<source>/
└─────────────┘
```

## 🛠️ Tech Stack

- **Python 3.11+** - Core language
- **Dagster** - Orchestration and pipeline management
- **Docker & Docker Compose** - Service isolation and deployment
- **Neo4j** - Graph database for model relationships
- **Elasticsearch** - Full-text search and discovery
- **Pydantic** - Schema validation and data modeling
- **Poetry** - Dependency management

## 📁 Project Structure

```
mlentory_etl_backend/
├── etl/                    # Dagster pipelines and assets
│   ├── assets/            # Dagster asset definitions
│   ├── jobs/              # Dagster job definitions
│   ├── resources/         # Dagster resources (DB connections, etc.)
│   └── repository.py      # Main Dagster repository entrypoint
├── extractors/            # Source-specific scrapers/spiders
│   ├── huggingface/      # HuggingFace extractor
│   ├── paperswithcode/   # PapersWithCode extractor
│   └── openml/           # OpenML extractor
├── transformers/          # FAIR4ML normalization logic
│   ├── huggingface/      # HuggingFace transformer
│   ├── paperswithcode/   # PapersWithCode transformer
│   └── openml/           # OpenML transformer
├── loaders/               # Loaders for Neo4j + Elasticsearch
│   ├── neo4j_loader.py   # Neo4j graph loader
│   ├── elasticsearch_loader.py  # ES indexer
│   └── rdf_exporter.py   # RDF/Turtle exporter
├── schemas/               # Shared Pydantic schemas
│   ├── fair4ml.py        # FAIR4ML core schema
│   └── sources/          # Source-specific schemas
├── deploy/                # Deployment configurations
│   ├── docker/           # Dockerfiles
│   └── dagster/          # Dagster deployment configs
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── docs/                  # Documentation
│   ├── architecture.md   # System architecture
│   └── fair4ml.md        # FAIR4ML schema documentation
├── data/                  # Data storage (gitignored)
│   ├── raw/              # Raw extracted data
│   ├── normalized/       # FAIR4ML normalized data
│   └── rdf/              # RDF/Turtle exports
├── docker-compose.yml     # Local development stack
├── Makefile              # Common commands
├── pyproject.toml        # Python dependencies
├── .env.example          # Environment variables template
└── README.md             # This file
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose installed
- Python 3.11+ (for local development)
- At least 8GB RAM (for Neo4j + Elasticsearch)

### Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd mlentory_etl_backend
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start the services**
   ```bash
   sudo make up
   # or
   docker-compose up -d
   ```

4. **Access the services**
   - Dagster UI: http://localhost:3000
   - Neo4j Browser: http://localhost:7474
   - Elasticsearch: http://localhost:9200

### Development

```bash
# Start all services
sudo make up

# View logs
sudo make logs

# Stop services
sudo make down

# Run tests
sudo make test

# Format code
sudo make format

# Type check
sudo make typecheck

# Run a specific extractor
sudo make extract SOURCE=huggingface

# Full ETL pipeline
sudo make etl-run
```

## 🔧 Configuration

All configuration is managed through environment variables. See `.env.example` for all available options.

Key configurations:
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` - Neo4j connection
- `ELASTICSEARCH_URL` - Elasticsearch endpoint
- `DAGSTER_HOME` - Dagster workspace location
- `DATA_DIR` - Data storage directory

## 🧪 STELLA Evaluation (Optional)

This repository can be run with the **STELLA evaluation framework** to support interleaved A/B ranking and
feedback collection for search experiments.

### Start STELLA services

The `docker-compose.yml` includes a `stella` profile that starts:
- `stella-app` (proxy + interleaving + session/feedback handling)
- `stella-server` (experiment tracking backend)
- system containers (baseline/experimental rankers)

Using the Makefile:

```bash
# Start STELLA services
sudo make stella-up

# Initialize STELLA databases (run once)
sudo make stella-init

# Stop STELLA services
sudo make stella-down
```

Using Docker Compose directly:

```bash
# Start the full stack (ETL + API + STELLA)
docker compose --profile=complete --profile=stella up -d

# Or start only STELLA services
docker compose --profile=stella up -d
```

Default ports (see `docker-compose.yml`):
- STELLA App: `http://localhost:${STELLA_APP_PORT:-8080}`
- STELLA Server: `http://localhost:${STELLA_SERVER_PORT:-8004}`

### API endpoints used by STELLA

This API exposes STELLA-specific endpoints under `/api/v1/stella`:
- `GET /api/v1/stella/search_with_stella`: forwards search to STELLA proxy (ranking/interleaving)
- `POST /api/v1/stella/stella_feedback`: forwards click feedback payloads to STELLA

### Environment variables

Common configuration knobs:
- `USE_STELLA=true`: enable STELLA endpoints
- `STELLA_PROXY_API` (default `http://stella-app:8005/proxy`): proxy base used by `search_with_stella`
- `BACKEND_BASE_URL` (default `mlentory-api:8000/api/v1/models`): base URL forwarded to ranker containers
- `STELLA_APP_API` (default `http://stella-app:8005/stella/api/v1`): base URL used for feedback forwarding

## 🧪 Testing

```bash
# Run all tests
sudo make test

# Run unit tests only
pytest tests/unit/

# Run integration tests (requires Docker services)
pytest tests/integration/

# Run with coverage
pytest --cov=. --cov-report=html
```

Target coverage: ≥ 80%

## 📊 Data Flow

1. **Extraction**: Source-specific extractors fetch raw metadata
   - Output: `/data/raw/<source>/*.json`

2. **Transformation**: Convert to FAIR4ML schema
   - Input: `/data/raw/<source>/*.json`
   - Output: `/data/normalized/<source>/*.json`

3. **Loading**: Persist to Neo4j and Elasticsearch
   - Input: `/data/normalized/<source>/*.json`
   - Output: Neo4j nodes/relationships + ES indices + `/data/rdf/<source>/*.ttl`

## 🎨 Coding Standards

- **Formatter**: Black
- **Type Checker**: mypy
- **Docstrings**: Google style
- **Naming**:
  - Python modules: `snake_case`
  - Classes: `PascalCase`
  - Environment variables: `UPPER_SNAKE_CASE`
  - Docker services: `kebab-case`

## 🔐 Security

- Never commit secrets to version control
- Use `.env` for local development
- Use secrets management for production (e.g., Docker secrets, Kubernetes secrets)

## 📝 License

[Add your license here]

## 🤝 Contributing

1. Create a feature branch
2. Make your changes
3. Run tests and linting
4. Submit a pull request

## 📚 Additional Documentation

- [Architecture Overview](docs/architecture.md)
- [FAIR4ML Schema](docs/fair4ml.md)
- [Adding a New Source](docs/adding_sources.md)

## 🐛 Troubleshooting

### Services won't start
- Check Docker is running: `docker ps`
- Check logs: `docker-compose logs`
- Ensure ports 3000, 7474, 7687, 9200 are available

### Neo4j connection fails
- Verify Neo4j is running: `docker-compose ps neo4j`
- Check credentials in `.env` match `docker-compose.yml`

### Dagster UI not accessible
- Ensure dagster service is running: `docker-compose ps dagster`
- Check logs: `docker-compose logs dagster`

## 📞 Support

For issues and questions, please open an issue on GitHub.

