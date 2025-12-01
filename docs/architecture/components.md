# Component Details

Deep dive into each system component, their responsibilities, interfaces, and implementation details.

---

## Component Architecture

The MLentory ETL pipeline consists of several key components organized in a modular architecture:

```
┌──────────────────────────────────────────────────────────────┐
│                   Dagster Orchestration                 │
│  (Asset Management, Dependency Resolution, Scheduling)  │
└──────────────┬───────────────────────────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌──────────┐ ┌────────┐
│Extract │ │Transform │ │ Load   │
│        │ │          │ │        │
└────────┘ └──────────┘ └────────┘
    │          │          │
    ▼          ▼          ▼
┌──────────────────────────────────────────┐
│      Storage Systems                  │
│  (Neo4j, Elasticsearch, PostgreSQL)   │
└──────────────────────────────────────────┘
```

---

## Extractors

### Purpose

Extractors gather raw, unprocessed data from external ML model repositories and save it in a consistent format for transformation.

### Responsibilities

1. **API Interaction:** Connect to external APIs, handle authentication, manage rate limits
2. **Data Fetching:** Retrieve model metadata and related entities
3. **Entity Discovery:** Identify references to related entities (datasets, papers, etc.)
4. **Entity Enrichment:** Fetch full metadata for discovered entities
5. **Data Persistence:** Save raw data to organized file structures

### Component Structure

```
etl_extractors/<platform>/
├── <platform>_extractor.py      # High-level extractor class
├── <platform>_enrichment.py     # Entity enrichment orchestrator
├── clients/                     # API client classes
│   ├── models_client.py
│   ├── datasets_client.py
│   └── ...
└── entity_identifiers/          # Entity discovery
    ├── base.py                  # Abstract base class
    ├── dataset_identifier.py
    └── ...
```

### Key Classes

**Extractor Class:**

- Main interface for extraction
- Coordinates clients and enrichment
- Handles pagination and error recovery
- Saves data to organized folders

**Client Classes:**

- Low-level API interactions
- Handle authentication and rate limiting
- Parse API responses
- Convert to consistent data structures

**Entity Identifiers:**

- Scan model metadata for entity references
- Use pattern matching and heuristics
- Return mappings: `model_id → [entity_ids]`

**Enrichment Class:**

- Orchestrates entity identification
- Fetches full metadata for entities
- Handles batch processing and parallelization

### Interfaces

**Extractor Interface:**
```python
class Extractor:
    def extract_models(
        self,
        num_models: int,
        threads: int = 4,
        output_root: Path | None = None,
    ) -> tuple[pd.DataFrame, Path]:
        """Extract models and return DataFrame + file path."""
        pass
```

**Entity Identifier Interface:**
```python
class EntityIdentifier(ABC):
    @property
    def entity_type(self) -> str:
        """Return entity type (e.g., 'datasets')."""
        pass
    
    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """Extract unique entity IDs."""
        pass
    
    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """Extract entity IDs per model."""
        pass
```

### Implementation Details

**Error Handling:**

- Continue processing on individual failures
- Log errors with context
- Return partial results

**Rate Limiting:**

- Respect API rate limits
- Implement exponential backoff
- Use thread pools for parallel requests

**Data Organization:**

- Run folders with timestamps and UUIDs
- Consistent file naming
- Preserve source structure

### Supported Platforms

- **HuggingFace:** Most comprehensive, extensive entity enrichment
- **OpenML:** ML experiments focus, different data model
- **AI4Life:** Biomedical specialization, domain-specific metadata

See [Extractors Overview](../extractors/overview.md) for platform-specific details.

---

## Transformers

### Purpose

Transformers convert source-specific raw data into standardized FAIR4ML format, ensuring consistency and enabling cross-platform comparison.

### Responsibilities

1. **Field Mapping:** Convert source fields to FAIR4ML properties
2. **Data Validation:** Ensure data conforms to FAIR4ML schema
3. **Data Enrichment:** Add computed fields and resolve references
4. **Entity Linking:** Link models to related entities
5. **Error Handling:** Collect and report validation errors

### Component Structure

```
etl_transformers/<platform>/
├── transform_mlmodel.py         # Mapping functions
│   ├── map_basic_properties()
│   ├── map_ml_task()
│   ├── map_license()
│   └── ...
└── __init__.py                  # Module exports
```

### Key Functions

**Mapping Functions:**

- Pure functions (no side effects)
- Take raw model dict, return FAIR4ML dict
- Include extraction metadata
- Handle missing fields gracefully

**Property Extractors:**

- Extract specific property groups
- Run in parallel for efficiency
- Save partial schemas
- Include merge keys (`_model_id`)

**Schema Merger:**

- Load all partial schemas
- Merge by `_model_id`
- Validate with Pydantic
- Save validated models

### Interfaces

**Mapping Function Interface:**
```python
def map_basic_properties(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map basic properties from source to FAIR4ML.
    
    Returns:
        Dictionary with mapped fields and extraction_metadata
    """
    pass
```

**Property Extractor Asset:**
```python
@asset(...)
def extract_basic_properties(models_data: Tuple[str, str]) -> str:
    """
    Extract basic properties for all models.
    
    Returns:
        Path to partial schema JSON file
    """
    pass
```

### Implementation Details

**Modular Architecture:**

- Property groups extracted independently
- Parallel processing for efficiency
- Error isolation (one failure doesn't stop others)

**Validation:**

- Pydantic schema validation
- Type checking and constraints
- Error collection and reporting

**Extraction Metadata:**

- Tracks how each field was obtained
- Includes confidence scores
- Records source field names

### Transformation Patterns

**Direct Mapping:**

```python
result["name"] = raw_model.get("name", "")
```

**Value Transformation:**

```python
result["mlTask"] = [raw_model.get("task")]  # Convert to list
```

**URL Generation:**

```python
result["url"] = f"https://platform.com/models/{model_id}"
```

**Date Parsing:**

```python
result["dateCreated"] = _parse_datetime(raw_model.get("created_at"))
```

See [Transformers Overview](../transformers/overview.md) for more patterns.

---

## Loaders

### Purpose

Loaders persist normalized FAIR4ML data into storage systems optimized for different query patterns (graph queries, full-text search, semantic web).

### Responsibilities

1. **Format Conversion:** Convert FAIR4ML JSON to target formats (RDF, Elasticsearch documents)
2. **Data Persistence:** Load data into storage systems
3. **Upsert Logic:** Handle updates gracefully (update if exists, insert if new)
4. **Error Handling:** Continue loading even when individual items fail
5. **Export:** Generate RDF/Turtle files for interoperability

### Component Structure

```
etl_loaders/
├── <platform>_rdf_loader.py      # Neo4j RDF loading
│   ├── build_and_persist_models_rdf()
│   ├── build_model_triples()
│   └── ...
├── <platform>_index_loader.py    # Elasticsearch indexing
│   ├── index_models()
│   └── build_document()
└── rdf_store.py                  # Neo4j store configuration
```

### Key Functions

**RDF Builders:**

- Convert FAIR4ML JSON to RDF triples
- Create subject-predicate-object triples
- Handle different data types (strings, dates, URIs)
- Build relationships between entities

**Neo4j Persisters:**

- Persist RDF triples to Neo4j
- Use rdflib-neo4j for integration
- Batch operations for efficiency
- Export to Turtle files

**Elasticsearch Indexers:**

- Build searchable documents
- Configure field mappings
- Bulk index for efficiency
- Handle upserts

### Interfaces

**RDF Builder Interface:**
```python
def build_model_triples(
    graph: Graph,
    model: Dict[str, Any]
) -> int:
    """
    Build RDF triples for a model.
    
    Returns:
        Number of triples added
    """
    pass
```

**Neo4j Loader Interface:**
```python
def build_and_persist_models_rdf(
    json_path: str,
    config: Neo4jConfig,
    output_ttl_path: str,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """
    Load models to Neo4j and export RDF.
    
    Returns:
        Loading statistics
    """
    pass
```

**Elasticsearch Indexer Interface:**
```python
def index_models(
    json_path: str,
    index_name: str = "models",
    batch_size: int = 100,
) -> Dict[str, Any]:
    """
    Index models in Elasticsearch.
    
    Returns:
        Indexing statistics
    """
    pass
```

### Implementation Details

**RDF Conversion:**

- Use standard vocabularies (schema.org, FAIR4ML)
- Generate unique subject IRIs
- Handle lists and nested structures
- Preserve relationships

**Neo4j Integration:**

- Use neosemantics (n10s) plugin
- Batch triple insertion
- Transaction-based for consistency
- Export to Turtle format

**Elasticsearch Integration:**

- Configure field mappings
- Use bulk API for efficiency
- Handle document updates
- Optimize for search performance

### Target Systems

**Neo4j:**

- Graph database for relationships
- Optimized for graph traversals
- Supports Cypher queries
- RDF/Turtle export

**Elasticsearch:**

- Search engine for full-text search
- Optimized for text analysis
- Supports complex queries and filters
- Fast search performance

**RDF Export:**

- Semantic web format
- Human-readable Turtle syntax
- Machine-processable
- FAIR data compliance

See [Loaders Overview](../loaders/overview.md) for system-specific details.

---

## Dagster Assets

### Purpose

Dagster assets orchestrate the ETL pipeline, managing dependencies, execution order, and observability.

### Responsibilities

1. **Dependency Management:** Define and resolve asset dependencies
2. **Execution Orchestration:** Determine execution order
3. **Observability:** Track execution status and metrics
4. **Error Handling:** Retry logic and error reporting
5. **Scheduling:** Support scheduled and on-demand execution

### Asset Structure

```
etl/assets/
├── <platform>_extraction.py      # Extraction assets
│   ├── <platform>_run_folder
│   ├── <platform>_raw_models
│   └── ...
├── <platform>_transformation.py  # Transformation assets
│   ├── <platform>_normalized_run_folder
│   ├── <platform>_extract_basic_properties
│   ├── <platform>_models_normalized
│   └── ...
└── <platform>_loading.py         # Loading assets
    ├── <platform>_rdf_store_ready
    ├── <platform>_load_models_to_neo4j
    └── ...
```

### Asset Types

**Extraction Assets:**

- Create run folders
- Extract models and entities
- Identify and enrich entities
- Save raw data

**Transformation Assets:**

- Create normalized run folders
- Extract property groups (parallel)
- Merge partial schemas
- Validate and save FAIR4ML data

**Loading Assets:**

- Configure storage systems
- Load to Neo4j, Elasticsearch
- Export RDF files
- Generate load reports

### Asset Dependencies

Assets form a dependency graph:

```
hf_run_folder
    ├── hf_raw_models_latest
    └── hf_raw_models_from_file
            └── hf_raw_models
                    └── hf_models_normalized
                            ├── hf_load_models_to_neo4j
                            └── hf_index_models_elasticsearch
```

**Dependency Resolution:**

- Dagster automatically resolves dependencies
- Ensures correct execution order
- Parallelizes independent assets
- Handles failures gracefully

### Asset Interface

```python
@asset(
    group_name="platform",
    ins={"input_data": AssetIn("upstream_asset")},
    tags={"pipeline": "platform_etl"}
)
def my_asset(input_data: str) -> str:
    """
    Process input data and return output.
    
    Args:
        input_data: Output from upstream asset
        
    Returns:
        Output for downstream assets
    """
    pass

---

## Storage Systems

### Neo4j

**Purpose:** Graph database for relationship queries and knowledge graph exploration.

**Data Model:**

- **Nodes:** Models, Datasets, Papers, Authors, Organizations
- **Relationships:** USES_DATASET, CITES_PAPER, BASED_ON, CREATED_BY
- **Properties:** Stored on nodes and relationships

**Query Language:** Cypher

**Features:**

- Native graph storage
- Fast relationship traversals
- RDF support via neosemantics
- Graph algorithms and analytics

**Configuration:**

- Connection via Bolt protocol
- Authentication via credentials
- Database selection per connection
- Plugin support (n10s, APOC)

### Elasticsearch

**Purpose:** Search engine for full-text search and filtering.

**Data Model:**

- **Indices:** Collections of documents (e.g., `hf_models`)
- **Documents:** JSON objects representing models
- **Fields:** Searchable properties (name, description, etc.)

**Query Language:** Elasticsearch Query DSL (JSON)

**Features:**

- Full-text search with relevance scoring
- Filtering and aggregation
- Faceted search
- Autocomplete and suggestions

**Configuration:**

- Index mappings define field types
- Analyzers for text processing
- Sharding and replication
- Bulk API for efficient indexing

### PostgreSQL

**Purpose:** Metadata storage for Dagster pipeline execution.

**Data Model:**

- **Runs:** Pipeline execution records
- **Assets:** Data artifact definitions
- **Materializations:** Asset execution records
- **Lineage:** Dependency relationships

**Usage:**

- Dagster metadata storage
- Pipeline execution history
- Asset lineage tracking
- Run scheduling and monitoring

**Configuration:**

- Standard PostgreSQL setup
- Dagster-managed schema
- Connection pooling
- Backup and recovery

---

## Configuration System

### Purpose

Centralized configuration management for all pipeline components.

### Configuration Sources

1. **Environment Variables:** Primary source for secrets and settings
2. **YAML Files:** Structured configuration for extraction parameters
3. **Default Values:** Sensible defaults for all settings

### Configuration Structure

```
etl/config.py
├── GeneralConfig          # Shared settings
├── HuggingFaceConfig     # HF-specific settings
├── OpenMLConfig          # OpenML-specific settings
└── AI4LifeConfig         # AI4Life-specific settings
```

### Configuration Access

```python
from etl.config import get_hf_config

config = get_hf_config()
extractor.extract_models(num_models=config.num_models)
```

### Environment Variables

**Neo4j:**

- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

**Elasticsearch:**

- `ELASTICSEARCH_HOST`
- `ELASTICSEARCH_PORT`
- `ELASTICSEARCH_USER`
- `ELASTICSEARCH_PASSWORD`

**Extraction:**

- `HF_NUM_MODELS`
- `HF_THREADS`
- `OPENML_NUM_INSTANCES`
- etc.

See [Configuration Guide](../getting-started/configuration.md) for complete list.

---

## Error Handling and Logging

### Logging Strategy

**Logging Levels:**

- **DEBUG:** Detailed diagnostic information
- **INFO:** General informational messages
- **WARNING:** Warning messages for potential issues
- **ERROR:** Error messages for failures
- **CRITICAL:** Critical errors requiring immediate attention

**Logging Format:**

- Structured logging with context
- Include timestamps, module names, log levels
- Error stack traces for debugging

### Error Handling Patterns

**Extraction:**

- Continue on individual model failures
- Log errors with model ID and context
- Save error files for analysis

**Transformation:**

- Continue on individual model failures
- Collect validation errors
- Save error files separately

**Loading:**

- Retry on transient failures
- Log errors with entity ID
- Generate error reports

### Error Recovery

**Automatic:**

- Dagster retry logic
- Exponential backoff
- Transient failure handling

**Manual:**

- Re-run failed assets
- Investigate error files
- Fix data issues and re-run

---

## Related Documentation

- **[Architecture Overview](overview.md)** - High-level system overview
- **[System Design](system-design.md)** - Design decisions and rationale
- **[Data Flow](data-flow.md)** - Detailed data journey
- **[Deployment](deployment.md)** - Production deployment guide
- **[Extractors Code Flow](../extractors/code-flow.md)** - Extraction implementation
- **[Transformers Code Flow](../transformers/code-flow.md)** - Transformation implementation
- **[Loaders Code Flow](../loaders/code-flow.md)** - Loading implementation
