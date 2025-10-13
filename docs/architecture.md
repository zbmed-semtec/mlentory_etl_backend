# MLentory ETL Architecture

## Overview

MLentory ETL is a modular, scalable data pipeline for extracting, transforming, and loading ML model metadata from various sources into a unified knowledge graph and search index.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dagster Orchestration                     │
│                    (dagster-webserver & daemon)                  │
└─────────────────────────────────────────────────────────────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
        ┌───────▼───────┐ ┌─────▼──────┐ ┌──────▼───────┐
        │  Extractors   │ │Transformers│ │   Loaders    │
        │               │ │            │ │              │
        │  - HF         │ │ - HF       │ │ - Neo4j      │
        │  - PWC        │ │ - PWC      │ │ - ES         │
        │  - OpenML     │ │ - OpenML   │ │ - RDF Export │
        └───────┬───────┘ └─────┬──────┘ └──────┬───────┘
                │               │                │
                │               │                │
        ┌───────▼───────┐ ┌─────▼──────┐ ┌──────▼───────┐
        │  /data/raw/   │ │/data/norm/ │ │  Neo4j DB    │
        │               │ │            │ │  ES Index    │
        │  JSON files   │ │FAIR4ML JSON│ │  /data/rdf/  │
        └───────────────┘ └────────────┘ └──────────────┘
```

## Components

### 1. Extractors

Source-specific data extraction modules that fetch ML model metadata from various platforms.

**Responsibilities:**
- Connect to external APIs/websites
- Fetch raw model metadata
- Handle rate limiting and pagination
- Store raw data in `/data/raw/<source>/`

**Supported Sources:**
- HuggingFace Hub
- PapersWithCode
- OpenML

### 2. Transformers

Data normalization modules that convert source-specific formats into the FAIR4ML schema.

**Responsibilities:**
- Parse raw JSON data
- Map to FAIR4ML Pydantic models
- Validate data completeness
- Store normalized data in `/data/normalized/<source>/`

**Key Features:**
- Schema validation using Pydantic
- Data enrichment
- Deduplication logic

### 3. Loaders

Data persistence modules that load FAIR4ML data into target systems.

**Responsibilities:**
- Load data into Neo4j graph database
- Index data in Elasticsearch
- Export RDF/Turtle files
- Handle upserts and conflict resolution

**Target Systems:**
- **Neo4j**: Graph database for relationships
- **Elasticsearch**: Full-text search and discovery
- **RDF**: Semantic web compatibility

### 4. Dagster Orchestration

**Components:**
- **Assets**: Represent data artifacts (extracted, transformed, loaded data)
- **Jobs**: Define execution sequences
- **Schedules**: Automated periodic runs
- **Resources**: Shared connections (DB, API clients)

**Features:**
- Dependency tracking
- Incremental materialization
- Retry logic
- Run tracking and lineage

## Data Flow

### Stage 1: Extraction

```
External Source → Extractor → /data/raw/<source>/<timestamp>.json
```

### Stage 2: Transformation

```
/data/raw/<source>/*.json → Transformer → /data/normalized/<source>/<id>.json
                                       → FAIR4ML Pydantic Model
```

### Stage 3: Loading

```
/data/normalized/<source>/*.json → Loader → Neo4j (graph)
                                         → Elasticsearch (index)
                                         → /data/rdf/<source>/<id>.ttl
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Orchestration | Dagster | Workflow management |
| Graph DB | Neo4j | Model relationships |
| Search | Elasticsearch | Full-text search |
| Schema | Pydantic | Data validation |
| Semantic Web | RDFLib | RDF export |
| Container | Docker | Service isolation |
| Language | Python 3.11+ | Implementation |

## Deployment Architecture

### Local Development

```
Docker Compose
├── neo4j (7474, 7687)
├── elasticsearch (9200)
├── dagster-postgres (internal)
├── dagster-webserver (3000)
└── dagster-daemon
```

### Production (Future)

- Kubernetes deployment
- Managed Neo4j AuraDB
- Elastic Cloud
- Dagster Cloud or self-hosted

## Data Model

### FAIR4ML Schema

The FAIR4ML schema is the core data model representing:

- **Models**: ML model metadata
- **Datasets**: Training/evaluation datasets
- **Papers**: Research publications
- **Authors**: Model/paper authors
- **Organizations**: Institutions
- **Metrics**: Performance metrics
- **Tasks**: ML tasks (classification, etc.)
- **Frameworks**: ML frameworks (PyTorch, TF, etc.)

See `docs/fair4ml.md` for detailed schema documentation.

## Scalability Considerations

### Horizontal Scaling
- Extractors can run in parallel containers
- Dagster supports distributed execution
- Neo4j and Elasticsearch can be clustered

### Data Volume
- Incremental extraction (only fetch new/updated models)
- Batch processing for transformations
- Bulk loading into databases

### Performance
- Caching for API responses
- Connection pooling
- Async I/O where applicable

## Security

- Secrets management via environment variables
- API tokens stored in `.env` (gitignored)
- Network isolation via Docker networks
- Database authentication required

## Monitoring & Observability

- Dagster UI for pipeline monitoring
- Logs aggregated per service
- Future: Prometheus + Grafana integration

## Extensibility

### Adding a New Source

1. Create extractor in `extractors/<source>/`
2. Create transformer in `transformers/<source>/`
3. Define source schema in `schemas/sources/<source>.py`
4. Register Dagster assets in `etl/assets/`
5. Update documentation

### Adding a New Loader

1. Implement loader in `loaders/<name>_loader.py`
2. Add Dagster asset for loading
3. Configure connection in `.env`
4. Update `docker-compose.yml` if needed

## Future Enhancements

- [ ] API for querying MLentory
- [ ] Web UI for model discovery
- [ ] ML model recommendations
- [ ] Automated model card generation
- [ ] Integration with MLflow/Weights & Biases
- [ ] Real-time updates via webhooks

