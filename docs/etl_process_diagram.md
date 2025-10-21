# MLentory ETL Process Diagram

```mermaid
flowchart TD
    %% Infrastructure Services
    subgraph "Infrastructure Services"
        NEO4J[NEO4J<br/>Graph Database<br/>Port: 7687/7474]
        ES[Elasticsearch<br/>Search Engine<br/>Port: 9200]
        DAGSTER[Dagster<br/>Orchestration<br/>Port: 3000]
        POSTGRES[PostgreSQL<br/>Dagster Metadata]
    end

    %% External Data Sources
    subgraph "External Data Sources"
        HF[HuggingFace Hub<br/>API]
        PWC[PapersWithCode<br/>Planned]
        OPENML[OpenML<br/>Planned]
    end

    %% ETL Pipeline Stages
    subgraph "ETL Pipeline"
        subgraph "1. Extraction Stage"
            HF_EXTRACTOR[HF Extractor<br/>hf_raw_models asset]
            HF_ENRICHMENT[HF Enrichment<br/>hf_enriched_entities asset]
        end

        subgraph "2. Transformation Stage"
            HF_TRANSFORMER[HF Transformer<br/>FAIR4ML Normalization<br/>Planned]
            PWC_TRANSFORMER[PWC Transformer<br/>Planned]
            OPENML_TRANSFORMER[OpenML Transformer<br/>Planned]
        end

        subgraph "3. Loading Stage"
            NEO4J_LOADER[Neo4j Loader<br/>Graph Storage<br/>Planned]
            ES_LOADER[Elasticsearch Loader<br/>Indexing<br/>Planned]
            RDF_EXPORTER[RDF Exporter<br/>Semantic Web Export<br/>Planned]
        end
    end

    %% Data Storage Paths
    subgraph "Data Storage (/data)"
        RAW_DIR[Raw Data<br/>/data/raw/<source>/]
        NORMALIZED_DIR[Normalized Data<br/>/data/normalized/<source>/]
        RDF_DIR[RDF Export<br/>/data/rdf/<source>/]
        CACHE_DIR[Cache<br/>/data/cache/]
        REFS_DIR[References<br/>/data/refs/]
    end

    %% Data Flow Connections
    HF --> HF_EXTRACTOR
    PWC -.-> PWC_EXTRACTOR
    OPENML -.-> OPENML_EXTRACTOR

    HF_EXTRACTOR --> HF_ENRICHMENT
    HF_ENRICHMENT --> HF_TRANSFORMER

    HF_TRANSFORMER --> NEO4J_LOADER
    HF_TRANSFORMER --> ES_LOADER
    HF_TRANSFORMER --> RDF_EXPORTER

    PWC_TRANSFORMER -.-> NEO4J_LOADER
    OPENML_TRANSFORMER -.-> NEO4J_LOADER

    PWC_TRANSFORMER -.-> ES_LOADER
    OPENML_TRANSFORMER -.-> ES_LOADER

    PWC_TRANSFORMER -.-> RDF_EXPORTER
    OPENML_TRANSFORMER -.-> RDF_EXPORTER

    %% Storage Connections
    HF_EXTRACTOR --> RAW_DIR
    HF_ENRICHMENT --> RAW_DIR

    HF_TRANSFORMER --> NORMALIZED_DIR
    PWC_TRANSFORMER -.-> NORMALIZED_DIR
    OPENML_TRANSFORMER -.-> NORMALIZED_DIR

    NEO4J_LOADER --> NEO4J
    ES_LOADER --> ES
    RDF_EXPORTER --> RDF_DIR

    %% Dagster Orchestration
    DAGSTER --> HF_EXTRACTOR
    DAGSTER --> HF_ENRICHMENT
    DAGSTER -.-> HF_TRANSFORMER
    DAGSTER -.-> NEO4J_LOADER
    DAGSTER -.-> ES_LOADER
    DAGSTER -.-> RDF_EXPORTER

    %% Metadata Storage
    DAGSTER --> POSTGRES

    %% Styling
    classDef current fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef planned fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,stroke-dasharray: 5 5
    classDef infrastructure fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    classDef storage fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    classDef external fill:#ffebee,stroke:#c62828,stroke-width:2px

    class HF,HUGGINGFACE_API current
    class HF_EXTRACTOR,HF_ENRICHMENT current
    class NEO4J,ES,DAGSTER,POSTGRES infrastructure
    class RAW_DIR,NORMALIZED_DIR,RDF_DIR,CACHE_DIR,REFS_DIR storage
    class HF,PWC,OPENML external
    class HF_TRANSFORMER,PWC_TRANSFORMER,OPENML_TRANSFORMER,NEO4J_LOADER,ES_LOADER,RDF_EXPORTER,PWC_EXTRACTOR,OPENML_EXTRACTOR planned
```

## ETL Pipeline Overview

### Current Implementation ✅
- **HF Raw Models Extraction**: Extracts raw model metadata from HuggingFace Hub API
- **HF Entity Enrichment**: Identifies and extracts related entities (datasets, papers, keywords, licenses)
- **Data Storage**: Raw JSON files stored in `/data/raw/hf/`
- **Dagster Orchestration**: Pipeline managed through Dagster assets

### Planned Implementation 📋
- **FAIR4ML Transformation**: Normalize raw data into FAIR4ML schema
- **Neo4j Loading**: Store normalized data as graph nodes/relationships
- **Elasticsearch Indexing**: Create searchable indices for discovery
- **RDF Export**: Generate semantic web compatible RDF/Turtle files
- **Additional Sources**: PapersWithCode and OpenML extractors

## Data Flow Details

### Stage 1: Extraction
```
HuggingFace API → HF Extractor → /data/raw/hf/models.json
                      ↓
              HF Enrichment → /data/raw/hf/{datasets,articles,keywords,licenses}.json
```

### Stage 2: Transformation (Planned)
```
/data/raw/hf/*.json → FAIR4ML Transformer → /data/normalized/hf/*.json
```

### Stage 3: Loading (Planned)
```
/data/normalized/hf/*.json → Neo4j Loader → Graph Database
                            → ES Loader → Search Indices
                            → RDF Exporter → /data/rdf/hf/*.ttl
```

## Service Dependencies

- **Dagster** orchestrates the entire pipeline
- **PostgreSQL** stores Dagster metadata and run history
- **Neo4j** provides graph storage for ML model relationships
- **Elasticsearch** enables full-text search and discovery

## Key Components

### Extractors
- **HFExtractor**: Downloads model metadata from HuggingFace Hub
- **HFEnrichment**: Extracts related entities and relationships

### Transformers (Planned)
- **FAIR4ML Normalization**: Converts source-specific data to standardized schema
- **Schema Validation**: Ensures data conforms to FAIR4ML Pydantic models

### Loaders (Planned)
- **Neo4jLoader**: Creates graph nodes and relationships
- **ElasticsearchLoader**: Indexes documents for search
- **RDFExporter**: Exports semantic web compatible data

## Configuration

Environment variables control:
- Model extraction limits (`HF_NUM_MODELS`)
- Threading (`HF_THREADS`, `HF_ENRICHMENT_THREADS`)
- Database connections (`NEO4J_URI`, `ELASTICSEARCH_URL`)
- Data directories (`DATA_DIR`)

## Extensibility

The modular design allows easy addition of new data sources:
1. Create source-specific extractor
2. Implement FAIR4ML transformer
3. Add Dagster assets to repository
4. Update docker-compose if needed
