# Code Flow

This guide explains how the loading system works, using HuggingFace as a concrete example. You'll learn how control flows through the system, how Dagster assets orchestrate loading to multiple storage systems, and where to make changes when adding support for a new platform.

---

## Overview: The Big Picture

Loading in MLentory follows a multi-target pattern:

1. **Dagster assets** orchestrate the loading process
2. **Loaders** convert FAIR4ML JSON to target formats (RDF, Elasticsearch documents)
3. **Multiple systems** are loaded in parallel (Neo4j, Elasticsearch, RDF export)
4. **Upsert logic** handles updates gracefully
5. **Error handling** maximizes success rate

Let's trace through this flow step by step using HuggingFace as our example.

---

## Step 1: How Dagster Assets Control the Flow

Loading assets are defined in `etl/assets/hf_loading.py`. They load data into three systems:

1. **Neo4j** - Graph database for relationships
2. **Elasticsearch** - Search engine for full-text search
3. **RDF Export** - Semantic web files for interoperability

### Asset Dependency Graph

```
hf_models_normalized (from transformation)
    ├─→ hf_rdf_store_ready (configures Neo4j)
    │       └─→ hf_load_models_to_neo4j (loads models to Neo4j)
    │       └─→ hf_load_articles_to_neo4j (loads articles to Neo4j)
    │       └─→ hf_load_datasets_to_neo4j (loads datasets to Neo4j)
    │       └─→ hf_load_tasks_to_neo4j (loads tasks to Neo4j)
    │
    ├─→ hf_index_models_elasticsearch (indexes models in Elasticsearch)
    │
    └─→ hf_export_metadata_json (exports metadata)
```

### Key Design: Parallel Loading

Loading to different systems happens **in parallel**:

- Neo4j loading doesn't wait for Elasticsearch
- Elasticsearch indexing doesn't wait for Neo4j
- RDF export doesn't wait for either

This maximizes efficiency and ensures that if one system fails, others continue.

---

## Step 2: How Neo4j Store Is Configured

Before loading to Neo4j, the system ensures the store is ready:

```49:115:etl/assets/hf_loading.py
@asset(
    group_name="hf_loading",
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_rdf_store_ready() -> Dict[str, Any]:
    """
    Verify Neo4j RDF store is configured and ready.
    
    Loads configuration from environment variables and validates connectivity.
    Returns a config marker that downstream assets can depend on.
    
    Returns:
        Dict with store readiness status and config info
        
    Raises:
        ValueError: If required env vars are missing
        ConnectionError: If Neo4j is not reachable
    """
    logger.info("Checking Neo4j RDF store readiness...")
    
    try:
        # Read env for reporting
        env_cfg = Neo4jConfig.from_env()
        # Build store config (may not expose uri/database attributes)
        _ = get_neo4j_store_config_from_env(
            batching=True,
            batch_size=200,
            multithreading=True,
            max_workers=4,
        )
        # Initialize/ensure n10s according to environment flag
        reset_flag = os.getenv("N10S_RESET_ON_CONFIG_CHANGE", "false").lower() == "true"
        desired_cfg = {"keepCustomDataTypes": True, "handleVocabUris": "SHORTEN"}

        # reset_database(drop_config=False)
        
        
        if reset_flag:
            logger.warning("N10S_RESET_ON_CONFIG_CHANGE=true → resetting database and re-initializing n10s")
            reset_database(drop_config=True)
            init_neosemantics(desired_cfg)
        else:
            current_cfg = get_neosemantics_config()
            if not current_cfg:
                init_neosemantics(desired_cfg)
            else:
                logger.info("n10s has existing configuration; skipping re-init on non-empty graph")
        ensure_default_prefixes()
        
        logger.info(f"Neo4j RDF store configured: uri={env_cfg.uri}, database={env_cfg.database}")
        
        return {
            "status": "ready",
            "uri": env_cfg.uri,
            "database": env_cfg.database,
            "batching": True,
            "batch_size": 5000,
            "multithreading": True,
            "max_workers": 4,
        }
        
    except ValueError as e:
        logger.error(f"Neo4j configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error checking Neo4j store: {e}", exc_info=True)
        raise
```

**What this does:**

- Validates Neo4j connection
- Initializes neosemantics (n10s) plugin for RDF support
- Sets up namespace prefixes
- Returns configuration for downstream assets

---

## Step 3: How Models Are Loaded to Neo4j

The main loading asset converts FAIR4ML models to RDF and loads them to Neo4j:

```118:201:etl/assets/hf_loading.py
@asset(
    group_name="hf_loading",
    ins={
        "normalized_models": AssetIn("hf_models_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_models_to_neo4j(
    normalized_models: Tuple[str, str],
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized HF models as RDF triples into Neo4j.
    
    Builds RDF triples from FAIR4ML models and persists them to Neo4j
    using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        normalized_models: Tuple of (mlmodels_json_path, normalized_folder)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder)
        
    Raises:
        FileNotFoundError: If normalized models file not found
        Exception: If loading fails
    """
    mlmodels_json_path, normalized_folder = normalized_models
    
    logger.info(f"Loading RDF from normalized models: {mlmodels_json_path}")
    logger.info(f"Neo4j store status: {store_ready['status']}")
    
    # Get Neo4j store config
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    
    # Create RDF output directory parallel to normalized
    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent  / "3_rdf" / "hf"  # /data/3_rdf/hf
    rdf_run_folder = rdf_base / normalized_path.name  # Same run ID as normalized
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"RDF outputs will be saved to: {rdf_run_folder}")
    
    # Output Turtle file path
    ttl_path = rdf_run_folder / "mlmodels.ttl"
    
    # Build and persist RDF
    logger.info("Building and persisting RDF triples...")
    load_stats = build_and_persist_models_rdf(
        json_path=mlmodels_json_path,
        config=config,
        output_ttl_path=str(ttl_path),
        batch_size=50,
    )
    
    logger.info(
        f"RDF loading complete: {load_stats['models_processed']} models, "
        f"{load_stats['triples_added']} triples, {load_stats['errors']} errors"
    )
    
    # Write load report to both normalized and RDF folders
    report = {
        "input_file": mlmodels_json_path,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    
    # Save report to RDF folder as well
    rdf_report_path = rdf_run_folder / "mlmodels_load_report.json"
    with open(rdf_report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"Models load report also saved to: {rdf_report_path}")
    
    return (str(rdf_report_path), normalized_folder)
```

**Flow:**

1. Asset receives normalized models JSON path and store config
2. Gets Neo4j configuration from environment
3. Creates RDF output folder (parallel to normalized folder)
4. Calls `build_and_persist_models_rdf()` to:
   - Convert FAIR4ML JSON to RDF triples
   - Load triples to Neo4j
   - Save Turtle file for reference
5. Saves load report with statistics

---

## Step 4: How RDF Triples Are Built

The loader converts FAIR4ML JSON to RDF triples. Here's how it works:

### RDF Triple Structure

RDF uses subject-predicate-object triples:

```
<subject> <predicate> <object> .
```

**Example:**
```turtle
<https://huggingface.co/bert-base-uncased>
  a fair4ml:MLModel ;
  schema:name "bert-base-uncased" ;
  schema:url "https://huggingface.co/bert-base-uncased" ;
  fair4ml:mlTask "fill-mask" .
```

### Building Triples from FAIR4ML

The loader function `build_model_triples()` in `etl_loaders/hf_rdf_loader.py` does the conversion:

```python
def build_model_triples(graph: Graph, model: Dict[str, Any]) -> int:
    """
    Build RDF triples for a single FAIR4ML model.
    
    Creates triples for core identification, provenance, temporal, description,
    and documentation URL properties.
    
    Args:
        graph: RDFLib Graph to add triples to
        model: Model dictionary with FAIR4ML properties (using IRI aliases)
        
    Returns:
        Number of triples added
    """
    # Mint subject IRI (unique identifier for this model)
    subject_iri = LoadHelpers.mint_subject(model)
    subject = URIRef(subject_iri)
    
    # Add rdf:type (this is a MLModel)
    graph.add((subject, namespaces["rdf"].type, namespaces["fair4ml"].MLModel))
    
    # Add string properties
    string_properties = [
        "https://schema.org/identifier",
        "https://schema.org/name",
        "https://schema.org/url",
        "https://schema.org/author",
        # ... more properties ...
    ]
    
    for property_iri in string_properties:
        value = model.get(property_iri)
        if value:
            # Handle lists (multiple values)
            if isinstance(value, list):
                for v in value:
                    graph.add((subject, URIRef(property_iri), Literal(v, datatype=XSD.string)))
            else:
                graph.add((subject, URIRef(property_iri), Literal(value, datatype=XSD.string)))
    
    # Add date properties with proper data types
    date_properties = [
        "https://schema.org/dateCreated",
        "https://schema.org/dateModified",
        # ... more dates ...
    ]
    
    for property_iri in date_properties:
        value = model.get(property_iri)
        if value:
            # Parse and add as xsd:dateTime
            date_value = parse_datetime(value)
            graph.add((subject, URIRef(property_iri), Literal(date_value, datatype=XSD.dateTime)))
    
    # Add relationships (links to other entities)
    # trainedOn → links to Dataset entities
    # citesPaper → links to Paper entities
    # ... more relationships ...
    
    return len(graph) - triples_before
```

**Key Points:**

- Each model gets a unique subject IRI (e.g., `https://huggingface.co/bert-base-uncased`)
- Properties become predicates (e.g., `schema:name`, `fair4ml:mlTask`)
- Values become objects (strings, dates, or links to other entities)
- Relationships create links between entities

---

## Step 5: How Models Are Indexed in Elasticsearch

Elasticsearch indexing happens in parallel with Neo4j loading:

```204:242:etl/assets/hf_loading.py
@asset(
    group_name="hf_loading",
    ins={
        "normalized_models": AssetIn("hf_models_normalized"),
    },
    tags={"pipeline": "hf_etl", "stage": "index"},
)
def hf_index_models_elasticsearch(
    normalized_models: Tuple[str, str],
) -> Dict[str, Any]:
    """Index normalized HF models into Elasticsearch for search.

    This asset reads the normalized HF FAIR4ML models JSON (`mlmodels.json`)
    and indexes a subset of properties into an Elasticsearch index using
    the `index_hf_models` function from `etl_loaders.hf_index_loader`.

    Args:
        normalized_models: Tuple of (mlmodels_json_path, normalized_folder)

    Returns:
        Dict with indexing statistics (models_indexed, errors, etc.)
    """
    mlmodels_json_path, normalized_folder = normalized_models
    
    logger.info(f"Indexing models to Elasticsearch: {mlmodels_json_path}")
    
    # Index models
    index_stats = index_hf_models(
        json_path=mlmodels_json_path,
        index_name="hf_models",
        batch_size=100,
    )
    
    logger.info(
        f"Elasticsearch indexing complete: {index_stats['models_indexed']} models, "
        f"{index_stats['errors']} errors"
    )
    
    return index_stats
```

**Flow:**

1. Asset receives normalized models JSON path
2. Calls `index_hf_models()` function
3. Function:
   - Reads FAIR4ML JSON
   - Converts to Elasticsearch document format
   - Indexes documents in batches
   - Handles upserts (updates existing documents)
4. Returns indexing statistics

### Elasticsearch Document Structure

FAIR4ML models are converted to searchable documents:

```json
{
  "id": "mlentory:model:xyz789",
  "name": "bert-base-uncased",
  "description": "BERT model for masked language modeling",
  "mlTask": ["fill-mask"],
  "keywords": ["bert", "nlp", "transformer"],
  "license": "apache-2.0",
  "author": "google",
  "url": "https://huggingface.co/bert-base-uncased",
  "dateCreated": "2020-01-01T00:00:00Z",
  "downloads": 5000000
}
```

**Key Points:**

- Text fields are analyzed for full-text search
- Keyword fields are stored for exact matching
- Dates are stored in ISO format
- Relationships are stored as arrays of IDs

---

## Step 6: How RDF Files Are Exported

RDF export creates Turtle files for semantic web integration:

```python
# During Neo4j loading, RDF triples are also saved to Turtle files
ttl_path = rdf_run_folder / "mlmodels.ttl"

# RDFLib can serialize graphs to Turtle format
graph.serialize(destination=str(ttl_path), format='turtle')
```

**Output Structure:**
```
/data/3_rdf/hf/2025-01-15_12-00-00_abc123/
├── mlmodels.ttl          (models in Turtle format)
├── datasets.ttl          (datasets in Turtle format)
├── articles.ttl          (articles in Turtle format)
└── mlmodels_load_report.json  (loading statistics)
```

**Turtle Format Example:**
```turtle
@prefix schema: <https://schema.org/> .
@prefix fair4ml: <https://w3id.org/fair4ml#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

<https://huggingface.co/bert-base-uncased>
  a fair4ml:MLModel ;
  schema:name "bert-base-uncased" ;
  schema:url "https://huggingface.co/bert-base-uncased" ;
  fair4ml:mlTask "fill-mask" ;
  schema:author "google" .
```

---

## Step 7: How Related Entities Are Loaded

After models, related entities (datasets, articles, tasks) are loaded:

```316:410:etl/assets/hf_loading.py
@asset(
    group_name="hf_loading",
    ins={
        "articles_normalized": AssetIn("hf_articles_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_articles_to_neo4j(
    articles_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized articles as RDF triples into Neo4j.
    
    Builds RDF triples from Schema.org ScholarlyArticle entities and persists them
    to Neo4j using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        articles_normalized: Path to normalized articles JSON (articles.json)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder) or ("", "") if no articles
        
    Raises:
        FileNotFoundError: If normalized articles file not found
        Exception: If loading fails
    """
    # Handle empty articles case
    if not articles_normalized or articles_normalized == "":
        logger.info("No articles to load (empty input)")
        return ("", "")
    
    articles_path = Path(articles_normalized)
    if not articles_path.exists():
        logger.warning(f"Articles JSON not found: {articles_normalized}")
        return ("", "")
    
    normalized_folder = str(articles_path.parent)
    
    logger.info(f"Loading RDF from normalized articles: {articles_normalized}")
    logger.info(f"Neo4j store status: {store_ready['status']}")
    
    # Get Neo4j store config
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    
    # Create RDF output directory parallel to normalized
    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "hf"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Article RDF outputs will be saved to: {rdf_run_folder}")
    
    ttl_path = rdf_run_folder / "articles.ttl"
    
    logger.info("Building and persisting RDF triples for articles...")
    load_stats = build_and_persist_articles_rdf(
        json_path=articles_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
        batch_size=50,
    )
    
    logger.info(
        f"Article RDF loading complete: {load_stats['articles_processed']} articles, "
        f"{load_stats['triples_added']} triples, {load_stats['errors']} errors"
    )
    
    # Write load report
    report = {
        "input_file": articles_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    
    rdf_report_path = rdf_run_folder / "articles_load_report.json"
    with open(rdf_report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    return (str(rdf_report_path), normalized_folder)
```

**Flow:**

- Similar to model loading, but for different entity types
- Each entity type (articles, datasets, tasks) has its own loader function
- All load to the same Neo4j database, creating relationships between entities

---

## Complete Flow Example: Loading HuggingFace Models

Let's trace through a complete loading run:

### 1. User Triggers Loading

User clicks "Materialize" in Dagster UI for `hf_load_models_to_neo4j` asset.

### 2. Dagster Resolves Dependencies

Dagster sees that `hf_load_models_to_neo4j` depends on:

- `hf_models_normalized` (from transformation)
- `hf_rdf_store_ready` (Neo4j configuration)

### 3. Store Configuration

`hf_rdf_store_ready` asset:
- Validates Neo4j connection
- Initializes neosemantics plugin
- Sets up namespace prefixes
- Returns configuration

### 4. Parallel Loading

Dagster executes loading assets **in parallel**:

- `hf_load_models_to_neo4j` → loads models to Neo4j, saves Turtle file
- `hf_index_models_elasticsearch` → indexes models in Elasticsearch
- `hf_load_articles_to_neo4j` → loads articles to Neo4j (if available)
- `hf_load_datasets_to_neo4j` → loads datasets to Neo4j (if available)

### 5. RDF Conversion

For each model:

- FAIR4ML JSON is converted to RDF triples
- Triples are added to RDFLib graph
- Graph is persisted to Neo4j using rdflib-neo4j
- Graph is serialized to Turtle file

### 6. Final Output

All data is loaded and exported:

- **Neo4j**: Models, datasets, articles as graph nodes with relationships
- **Elasticsearch**: Models as searchable documents
- **RDF Files**: Models, datasets, articles in Turtle format

---

## How to Add a New Loader

Now that you understand the flow, here's how to add support for a new platform:

### Step 1: Create RDF Loader Functions

Create `etl_loaders/<platform>_rdf_loader.py` with loader functions:

```python
# etl_loaders/newplatform_rdf_loader.py
from rdflib import Graph, URIRef, Literal, Namespace
from rdflib.namespace import RDF, XSD

def build_and_persist_models_rdf(
    json_path: str,
    config: Neo4jConfig,
    output_ttl_path: str,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """
    Build RDF triples from FAIR4ML models and persist to Neo4j.
    
    Args:
        json_path: Path to normalized models JSON
        config: Neo4j configuration
        output_ttl_path: Path to save Turtle file
        batch_size: Batch size for processing
        
    Returns:
        Dict with loading statistics
    """
    # Load models
    with open(json_path, 'r') as f:
        models = json.load(f)
    
    # Create RDF graph
    graph = Graph()
    
    # Build triples for each model
    for model in models:
        build_model_triples(graph, model)
    
    # Persist to Neo4j
    store = Neo4jStore(config)
    store.add_graph(graph)
    
    # Save Turtle file
    graph.serialize(destination=output_ttl_path, format='turtle')
    
    return {
        "models_processed": len(models),
        "triples_added": len(graph),
        "errors": 0,
    }

def build_model_triples(graph: Graph, model: Dict[str, Any]) -> int:
    """Build RDF triples for a single model"""
    # Similar to HuggingFace implementation
    pass
```

### Step 2: Create Elasticsearch Indexer

Create `etl_loaders/<platform>_index_loader.py`:

```python
# etl_loaders/newplatform_index_loader.py
from elasticsearch import Elasticsearch

def index_newplatform_models(
    json_path: str,
    index_name: str = "newplatform_models",
    batch_size: int = 100,
) -> Dict[str, Any]:
    """
    Index FAIR4ML models into Elasticsearch.
    
    Args:
        json_path: Path to normalized models JSON
        index_name: Elasticsearch index name
        batch_size: Batch size for bulk indexing
        
    Returns:
        Dict with indexing statistics
    """
    # Load models
    with open(json_path, 'r') as f:
        models = json.load(f)
    
    # Connect to Elasticsearch
    es = Elasticsearch()
    
    # Index models in batches
    indexed = 0
    errors = 0
    
    for i in range(0, len(models), batch_size):
        batch = models[i:i+batch_size]
        
        actions = []
        for model in batch:
            doc = convert_to_elasticsearch_doc(model)
            actions.append({
                "_index": index_name,
                "_id": doc["id"],
                "_source": doc,
            })
        
        # Bulk index
        result = es.bulk(body=actions)
        
        # Count successes and errors
        indexed += sum(1 for item in result['items'] if item['index']['status'] == 201)
        errors += sum(1 for item in result['items'] if 'error' in item['index'])
    
    return {
        "models_indexed": indexed,
        "errors": errors,
    }
```

### Step 3: Create Loading Assets

Create `etl/assets/<platform>_loading.py`:

```python
# etl/assets/newplatform_loading.py
from dagster import asset, AssetIn
from etl_loaders.newplatform_rdf_loader import build_and_persist_models_rdf
from etl_loaders.newplatform_index_loader import index_newplatform_models

@asset(
    group_name="newplatform_loading",
    tags={"pipeline": "newplatform_etl", "stage": "load"}
)
def newplatform_rdf_store_ready() -> Dict[str, Any]:
    """Configure Neo4j store"""
    # Similar to hf_rdf_store_ready
    pass

@asset(
    group_name="newplatform_loading",
    ins={
        "normalized_models": AssetIn("newplatform_models_normalized"),
        "store_ready": AssetIn("newplatform_rdf_store_ready"),
    },
    tags={"pipeline": "newplatform_etl", "stage": "load"}
)
def newplatform_load_models_to_neo4j(
    normalized_models: Tuple[str, str],
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load models to Neo4j"""
    mlmodels_json_path, normalized_folder = normalized_models
    
    config = get_neo4j_store_config_from_env(...)
    
    rdf_run_folder = create_rdf_folder(normalized_folder)
    ttl_path = rdf_run_folder / "mlmodels.ttl"
    
    load_stats = build_and_persist_models_rdf(
        json_path=mlmodels_json_path,
        config=config,
        output_ttl_path=str(ttl_path),
    )
    
    return (str(ttl_path), normalized_folder)

@asset(
    group_name="newplatform_loading",
    ins={
        "normalized_models": AssetIn("newplatform_models_normalized"),
    },
    tags={"pipeline": "newplatform_etl", "stage": "index"}
)
def newplatform_index_models_elasticsearch(
    normalized_models: Tuple[str, str],
) -> Dict[str, Any]:
    """Index models in Elasticsearch"""
    mlmodels_json_path, _ = normalized_models
    
    index_stats = index_newplatform_models(
        json_path=mlmodels_json_path,
        index_name="newplatform_models",
    )
    
    return index_stats
```

### Step 4: Register Assets

Add to `etl/repository.py`:

```python
from etl.assets import newplatform_loading as newplatform_loading_module

@repository
def mlentory_etl_repository():
    # ... existing assets ...
    newplatform_loading_assets = load_assets_from_modules([newplatform_loading_module])
    return [..., *newplatform_loading_assets]
```

---

## Key Concepts for Beginners

### What is RDF?

RDF (Resource Description Framework) is a standard for representing knowledge graphs:

- Uses subject-predicate-object triples
- Enables semantic web integration
- Works with SPARQL queries
- Standard format for FAIR data

### What is Neo4j?

Neo4j is a graph database:

- Stores data as nodes and relationships
- Optimized for relationship queries
- Uses Cypher query language
- Perfect for knowledge graphs

### What is Elasticsearch?

Elasticsearch is a search engine:

- Indexes text for fast search
- Supports full-text search, filtering, faceting
- Uses JSON documents
- Perfect for discovery interfaces

### Why Three Systems?

- **Neo4j**: Fast relationship queries ("find models using this dataset")
- **Elasticsearch**: Fast text search ("find models for sentiment analysis")
- **RDF Export**: Semantic web integration and FAIR compliance

### How Does Upsert Work?

Upsert = Update if exists, Insert if new:

- Neo4j: Uses MERGE operation based on unique identifier
- Elasticsearch: Uses document ID to update or create
- Prevents duplicates when re-running loads

---

## Common Patterns

### Pattern 1: Parallel Loading

Load to multiple systems simultaneously:

- Neo4j loading doesn't block Elasticsearch
- Elasticsearch indexing doesn't block Neo4j
- Maximizes efficiency

### Pattern 2: Batch Processing

Process entities in batches:

- Reduces memory usage
- Improves performance
- Handles large datasets efficiently

### Pattern 3: Error Resilience

Continue loading even when individual entities fail:

- Maximize success rate
- Log errors for debugging
- Save error reports

### Pattern 4: RDF Export

Always export RDF/Turtle files:

- Enables semantic web integration
- Provides backup/archival format
- Supports FAIR data principles

---

## Debugging Tips

### Check Neo4j

Query Neo4j to see loaded data:
```cypher
MATCH (m:Model)
RETURN m.name, m.url
LIMIT 10
```

### Check Elasticsearch

Query Elasticsearch to see indexed documents:
```bash
curl -X GET "localhost:9200/hf_models/_search?q=bert"
```

### Check RDF Files

View Turtle files to see RDF structure:
```bash
cat /data/3_rdf/hf/2025-01-15_12-00-00_abc123/mlmodels.ttl
```

### Check Load Reports

View loading statistics:
```bash
cat /data/3_rdf/hf/2025-01-15_12-00-00_abc123/mlmodels_load_report.json
```

### Test Loaders Independently

Test loader functions without Dagster:
```python
from etl_loaders.hf_rdf_loader import build_and_persist_models_rdf

stats = build_and_persist_models_rdf(
    json_path="/path/to/models.json",
    config=config,
    output_ttl_path="/path/to/output.ttl",
)
print(stats)
```

---

## Next Steps

- See [Neo4j Loader](neo4j.md) for detailed Neo4j-specific documentation
- Check [Elasticsearch Loader](elasticsearch.md) for search indexing details
- Review [RDF Exporter](rdf.md) for semantic web integration
- Explore [Loaders Overview](overview.md) for high-level concepts
- Review [Architecture Overview](../architecture/overview.md) to see how loaders fit into the system

