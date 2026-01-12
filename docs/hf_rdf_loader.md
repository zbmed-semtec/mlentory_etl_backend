# HuggingFace → RDF (Neo4j) Loader v1

## Overview

The HF RDF Loader implements a complete pipeline for persisting normalized HuggingFace model metadata as RDF triples in Neo4j using the `rdflib-neo4j` integration. This v1 implementation focuses on core FAIR4ML properties for model identification, provenance, temporal metadata, and documentation.

## Architecture

```
┌─────────────────────┐
│ hf_models_normalized│
│   (FAIR4ML JSON)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  rdf_loader.py   │
│  - Mint subject IRIs│
│  - Build triples    │
│  - Serialize Turtle │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐     ┌────────────────┐
│   Neo4j (RDF)       │◄────│ rdflib-neo4j   │
│   - Graph storage   │     │ - Batching     │
│   - SPARQL queries  │     │ - Multithreading│
└─────────────────────┘     └────────────────┘
```

## Components

### 1. `etl_loaders/rdf_store.py`

Configuration and utilities for Neo4j RDF store.

**Key functions:**
- `get_neo4j_store_config_from_env()`: Load Neo4j config from env vars
- `open_graph()`: Create RDFLib Graph backed by Neo4jStore
- `create_graph_context()`: Context manager for safe graph operations

**Environment variables:**
```bash
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
NEO4J_DATABASE=neo4j
```

### 2. `etl_loaders/rdf_loader.py`

HF-specific RDF building logic.

**Key functions:**
- `is_iri(value)`: Validate if string is a valid IRI
- `to_xsd_datetime(value)`: Convert datetime to xsd:dateTime
- `mint_subject(model)`: Create stable subject IRI
- `add_literal_or_iri()`: Add triple with literal or IRI object
- `build_model_triples()`: Build all triples for a model
- `build_and_persist_models_rdf()`: Main entry point

### 3. `etl/assets/hf_loading.py`

Dagster assets for orchestration.

**Assets:**
- `hf_rdf_store_ready`: Verify Neo4j connectivity
- `hf_load_models_rdf`: Load normalized models as RDF

## RDF Schema (v1)

### Subject IRI Minting Strategy

1. **First priority:** Use first `identifier` if it's a valid IRI
   ```
   https://huggingface.co/bert-base-uncased
   ```

2. **Fallback:** Mint from URL hash
   ```
   https://w3id.org/mlentory/model/{sha256(url)}
   ```

### Triples Created Per Model

| Predicate | Range | Example |
|-----------|-------|---------|
| `rdf:type` | `fair4ml:MLModel` | - |
| `schema:identifier` | IRI or Literal | `"https://huggingface.co/model"` |
| `schema:name` | Literal | `"bert-base-uncased"` |
| `schema:url` | IRI | `https://huggingface.co/model` |
| `schema:author` | Literal | `"google"` |
| `fair4ml:sharedBy` | Literal | `"Google Research"` |
| `schema:dateCreated` | xsd:dateTime | `"2020-01-01T00:00:00"` |
| `schema:dateModified` | xsd:dateTime | `"2020-06-01T00:00:00"` |
| `schema:datePublished` | xsd:dateTime | `"2020-01-15T00:00:00"` |
| `schema:description` | Literal | `"BERT base model"` |
| `schema:discussionUrl` | IRI | `https://example.com/discuss` |
| `schema:archivedAt` | IRI | `https://archive.org/...` |
| `codemeta:readme` | IRI | `https://example.com/README.md` |
| `codemeta:issueTracker` | IRI | `https://github.com/...` |

### Namespace Prefixes

```turtle
@prefix schema: <https://schema.org/> .
@prefix fair4ml: <https://w3id.org/fair4ml/> .
@prefix codemeta: <https://w3id.org/codemeta/> .
@prefix mlentory: <https://w3id.org/mlentory/> .
```

## Usage

### Via Dagster

```python
# Materialize the loading asset
from dagster import materialize

from etl.assets.hf_loading import hf_load_models_rdf, hf_rdf_store_ready
from etl.assets.hf_transformation import hf_models_normalized

result = materialize([hf_rdf_store_ready, hf_models_normalized, hf_load_models_rdf])
```

### Standalone Python

```python
from etl_loaders.rdf_store import get_neo4j_store_config_from_env
from etl_loaders.rdf_loader import build_and_persist_models_rdf

# Load config from env
config = get_neo4j_store_config_from_env(
    batching=True,
    batch_size=5000,
    multithreading=True,
    max_workers=4,
)

# Build and persist RDF
stats = build_and_persist_models_rdf(
    json_path="/data/normalized/hf/2025-11-06_12-00-00_abc123/mlmodels.json",
    config=config,
    output_ttl_path="/data/rdf/hf/2025-11-06_12-00-00_abc123/mlmodels.ttl",
)

print(f"Processed {stats['models_processed']} models")
print(f"Added {stats['triples_added']} triples")
print(f"Errors: {stats['errors']}")
```

### Command Line (via scripts)

```bash
# Set environment variables
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
export NEO4J_DATABASE=neo4j

# Run loading via Dagster CLI
dagster asset materialize -a mlentory_etl_repository \
  --select hf_load_models_rdf
```

## Output Files

### Directory Structure

```
/data/
├── normalized/hf/{run_id}/
│   ├── mlmodels.json           # Input: Normalized FAIR4ML models
│   └── load_report.json        # Output: Loading statistics
└── rdf/hf/{run_id}/
    ├── mlmodels.ttl            # Output: Turtle serialization
    └── load_report.json        # Output: Loading statistics (copy)
```

### Load Report Format

```json
{
  "input_file": "/data/normalized/hf/.../mlmodels.json",
  "rdf_folder": "/data/rdf/hf/.../",
  "ttl_file": "/data/rdf/hf/.../mlmodels.ttl",
  "neo4j_uri": "bolt://neo4j:7687",
  "neo4j_database": "neo4j",
  "models_processed": 500,
  "triples_added": 6500,
  "errors": 0,
  "timestamp": "2025-11-06T12:30:45.123456"
}
```

## Performance Tuning

### Neo4j Store Config

The loader uses batching and multithreading for optimal performance:

```python
config = get_neo4j_store_config_from_env(
    batching=True,          # Enable batch commits
    batch_size=5000,        # Triples per batch
    multithreading=True,    # Enable parallel imports
    max_workers=4,          # Worker threads
)
```

**Recommendations:**
- **Small datasets (<1K models):** Default settings work well
- **Medium datasets (1K-10K models):** Increase `batch_size=10000`, `max_workers=8`
- **Large datasets (>10K models):** Consider streaming or chunking input

### Memory Considerations

For large datasets, consider processing in chunks:

```python
import json

def load_models_chunked(json_path: str, chunk_size: int = 1000):
    """Load models in chunks to control memory."""
    with open(json_path, 'r') as f:
        models = json.load(f)
    
    for i in range(0, len(models), chunk_size):
        chunk = models[i:i + chunk_size]
        yield chunk
```

## Idempotency

The loader is **idempotent** - running it multiple times with the same input will:
1. Create the same subject IRIs (stable hashing)
2. Overwrite existing triples in Neo4j
3. Not create duplicates (Neo4j handles upserts)

## Error Handling

The loader continues on individual model errors and reports them:

```json
{
  "models_processed": 500,
  "triples_added": 6450,
  "errors": 2,
  "timestamp": "..."
}
```

Check logs for specific error details:
```bash
grep "ERROR" /var/log/dagster/hf_loading.log
```

## Querying the RDF Graph

### Via Neo4j Browser

```cypher
// Count models
MATCH (n:Resource)
WHERE n.uri CONTAINS "mlentory/model"
RETURN count(n)

// Find models by author
MATCH (n:Resource)-[r:ns0__author]->(author:Resource)
WHERE author.value = "google"
RETURN n.uri, r, author.value
LIMIT 10

// Models created in 2020
MATCH (n:Resource)-[r:ns0__dateCreated]->(date:Resource)
WHERE date.value STARTS WITH "2020"
RETURN n.uri, date.value
ORDER BY date.value DESC
```

### Via SPARQL (RDFLib)

```python
from etl_loaders.rdf_store import open_graph, get_neo4j_store_config_from_env

config = get_neo4j_store_config_from_env()
graph = open_graph(config)

# Query models by author
query = """
PREFIX schema: <https://schema.org/>
PREFIX fair4ml: <https://w3id.org/fair4ml/>

SELECT ?model ?name ?author
WHERE {
  ?model a fair4ml:MLModel ;
         schema:name ?name ;
         schema:author ?author .
  FILTER(?author = "google")
}
LIMIT 10
"""

results = graph.query(query)
for row in results:
    print(f"{row.model} - {row.name} by {row.author}")

graph.close(True)
```

## Testing

Run unit tests:
```bash
pytest tests/loaders/test_rdf_loader.py -v
```

Run integration tests (requires Neo4j):
```bash
pytest tests/loaders/test_rdf_loader.py -v -m integration
```

## Future Enhancements (v2+)

Planned for future versions:
- [ ] Add ML-specific properties (mlTask, modelCategory, etc.)
- [ ] Add dataset relationships (trainedOn, testedOn, etc.)
- [ ] Add lineage relationships (fineTunedFrom)
- [ ] Add license and keyword entities
- [ ] Support for incremental updates
- [ ] Graph validation and consistency checks
- [ ] Performance profiling and optimization
- [ ] Support for other sources (OpenML, PapersWithCode)

## Troubleshooting

### Common Issues

**1. Import error: `rdflib_neo4j` not found**
```bash
# Install dependencies
poetry install
# or
pip install rdflib rdflib-neo4j
```

**2. Connection refused to Neo4j**
```bash
# Check Neo4j is running
docker ps | grep neo4j

# Check connection
curl http://localhost:7474
```

**3. Authentication failed**
```bash
# Verify credentials
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your_password

# Test connection
cypher-shell -u neo4j -p your_password
```

**4. Slow loading performance**
- Increase `batch_size` and `max_workers`
- Ensure Neo4j has sufficient memory (ES_JAVA_OPTS)
- Use SSD storage for Neo4j data directory

## References

- [Neo4j RDFLib Integration Guide](https://neo4j.com/blog/developer/rdflib-neo4j-rdf-integration-neo4j/)
- [RDFLib Documentation](https://rdflib.readthedocs.io/)
- [FAIR4ML Schema 0.1.0](https://rda-fair4ml.github.io/FAIR4ML-schema/)
- [Schema.org Vocabulary](https://schema.org/)
- [CodeMeta Vocabulary](https://codemeta.github.io/)

