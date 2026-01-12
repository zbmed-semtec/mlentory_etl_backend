# Data Flow

Detailed explanation of how data moves through the MLentory ETL pipeline from source platforms to storage systems.

---

## Overview

Data flows through the MLentory system in three main stages:

1. **Extraction** - Gather raw data from external sources
2. **Transformation** - Convert to standardized FAIR4ML format
3. **Loading** - Persist to storage systems (Neo4j, Elasticsearch)

Each stage produces intermediate artifacts that are preserved for debugging, reprocessing, and audit trails.

---

## Stage 1: Extraction

### Input Sources

Data is extracted from multiple external platforms:

- **HuggingFace Hub** - Via REST API
- **OpenML** - Via Python package (OpenML API wrapper)
- **AI4Life** - Via Hypha API

### Extraction Process

```
External Platform API
    ↓
Extractor Class (etl_extractors/<platform>/)
    ├─→ API Client (handles authentication, rate limiting)
    ├─→ Entity Identifier (discovers related entities)
    └─→ Enrichment (fetches related entity metadata)
    ↓
Raw JSON Files
    ↓
/data/1_raw/<platform>/<timestamp>_<uuid>/
```

### Extraction Methods

**1. API-Based Extraction (Primary)**

- Direct API calls to platform endpoints
- Handles pagination automatically
- Respects rate limits
- Fast and reliable

**2. File-Based Extraction (Targeted)**

- Reads model IDs from configuration file
- Extracts specific models of interest
- Useful for testing and targeted extraction

**3. Web Scraping (Optional)**

- Browser automation for data not available via API
- Slower and more fragile
- Used only when necessary

### Entity Discovery and Enrichment

After extracting primary entities (models), the system:

1. **Identifies Related Entities:**

   - Scans model metadata for references
   - Finds datasets, papers, base models, keywords, licenses
   - Creates mapping: `model_id → [entity_ids]`

2. **Enriches Entities:**

   - Fetches full metadata for identified entities
   - Resolves references to complete entities
   - Builds comprehensive knowledge graph foundation

### Output Structure

```
/data/1_raw/hf/2025-01-15_12-00-00_abc123/
├── hf_models.json                    # Primary models
├── hf_models_with_ancestors.json     # With base models
├── hf_datasets_specific.json         # Enriched datasets
├── arxiv_articles.json               # Enriched papers
├── keywords.json                     # Identified keywords
├── licenses.json                     # Identified licenses
└── ...
```

**File Format:**

- JSON arrays of objects
- Each object represents one entity
- Preserves original source structure
- Includes extraction metadata

### Data Characteristics

- **Format:** Source-specific (varies by platform)
- **Structure:** Nested JSON objects
- **Size:** Varies (models: ~1-10KB each, datasets: ~5-50KB each)
- **Volume:** Hundreds to thousands of entities per run

---

## Stage 2: Transformation

### Input

Transformation reads raw JSON files from the extraction stage:

```
/data/1_raw/<platform>/<timestamp>_<uuid>/<entity>.json
```

### Transformation Process

```
Raw JSON Files
    ↓
Property Extraction (Parallel)
    ├─→ Basic Properties (identifier, name, dates, URLs)
    ├─→ ML Task & Category
    ├─→ Keywords & Language
    ├─→ License
    ├─→ Lineage (base models, fine-tuning)
    ├─→ Datasets (training, evaluation)
    ├─→ Code & Usage
    └─→ Ethics & Risks
    ↓
Partial Schemas (one per property group)
    ↓
Schema Merging
    ↓
Pydantic Validation
    ↓
FAIR4ML JSON Files
    ↓
/data/2_normalized/<platform>/<timestamp>_<uuid>/
```

### Property Extraction

Each property group is extracted independently in parallel:

**Example: Basic Properties Extraction**
```python
# Input (raw HuggingFace)
{
  "modelId": "google-bert/bert-base-uncased",
  "author": "google-bert",
  "createdAt": "2020-01-01T00:00:00Z"
}

# Output (partial schema)
{
  "_model_id": "google-bert/bert-base-uncased",
  "_index": 0,
  "identifier": ["https://huggingface.co/google-bert/bert-base-uncased"],
  "name": "bert-base-uncased",
  "author": "google-bert",
  "dateCreated": "2020-01-01T00:00:00Z",
  "extraction_metadata": {...}
}
```

**Key Points:**
- Each property group creates a partial schema
- Partial schemas include `_model_id` for merging
- Extraction metadata tracks provenance

### Schema Merging

All partial schemas are merged by `_model_id`:

```python
# Partial 1: Basic Properties
{"_model_id": "model1", "identifier": ["url1"], "name": "Model1"}

# Partial 2: ML Task
{"_model_id": "model1", "mlTask": ["classification"]}

# Merged Result
{
  "identifier": ["url1"],
  "name": "Model1",
  "mlTask": ["classification"]
}
```

### Validation

Merged schemas are validated against FAIR4ML Pydantic models:

```python
from schemas.fair4ml import MLModel

# Validate
model = MLModel(**merged_data)

# If valid, serialize to JSON
validated_json = model.model_dump(mode='json', by_alias=True)
```

**Validation Checks:**

- Required fields present
- Correct data types
- Value constraints (dates, URLs, etc.)
- Relationship references valid

### Entity Linking

After property extraction, models are linked to related entities:

- **Datasets:** `trainedOn`, `evaluatedOn` properties
- **Papers:** `citesPaper` property
- **Base Models:** `fineTunedFrom` property
- **Keywords:** `keywords` property
- **Licenses:** `license` property

### Output Structure

```
/data/2_normalized/hf/2025-01-15_12-00-00_abc123/
├── partial_basic_properties.json
├── partial_ml_task.json
├── partial_keywords_language.json
├── ...
├── mlmodels.json                    # Final validated models
├── datasets.json                    # Normalized datasets
├── articles.json                    # Normalized papers
└── mlmodels_transformation_errors.json  # Validation errors
```

**File Format:**

- FAIR4ML-compliant JSON
- Standardized structure across all sources
- Includes extraction metadata
- Validated and type-checked

### Data Characteristics

- **Format:** FAIR4ML JSON (standardized)
- **Structure:** Consistent across all sources
- **Size:** Similar to raw (some enrichment)
- **Volume:** Same as extraction (one-to-one mapping)

---

## Stage 3: Loading

### Input

Loading reads normalized FAIR4ML JSON files:

```
/data/2_normalized/<platform>/<timestamp>_<uuid>/<entity>.json
```

### Loading Process

```
FAIR4ML JSON Files
    ↓
    ├─→ Neo4j Loader
    │   ├─→ Convert to RDF Triples
    │   ├─→ Persist to Neo4j (via rdflib-neo4j)
    │   └─→ Export to Turtle (.ttl)
    │
    ├─→ Elasticsearch Loader
    │   ├─→ Build Searchable Documents
    │   └─→ Bulk Index
    │
    └─→ RDF Exporter
        └─→ Generate Turtle Files
    ↓
Storage Systems
```

### Neo4j Loading

**Step 1: RDF Conversion**

FAIR4ML JSON is converted to RDF triples:

```python
# FAIR4ML JSON
{
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "mlTask": ["fill-mask"]
}

# ↓ Converted to RDF ↓

<https://huggingface.co/bert-base-uncased>
  a fair4ml:MLModel ;
  schema:name "bert-base-uncased" ;
  fair4ml:mlTask "fill-mask" .
```

**Step 2: Graph Construction**

RDF triples create graph nodes and relationships:

- **Nodes:** Models, Datasets, Papers, Authors, Organizations
- **Relationships:** USES_DATASET, CITES_PAPER, BASED_ON, CREATED_BY

**Step 3: Persistence**

Triples are persisted to Neo4j using rdflib-neo4j:

- Batch insertion for efficiency
- Upsert logic (update if exists, insert if new)
- Transaction-based for consistency

**Step 4: RDF Export**

Triples are also exported to Turtle files for:

- Semantic web integration
- Archival and backup
- Interoperability with other systems

### Elasticsearch Loading

**Step 1: Document Building**

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
  "url": "https://huggingface.co/bert-base-uncased"
}
```

**Step 2: Field Mapping**

Fields are configured for appropriate search behavior:

- **Text fields:** Analyzed for full-text search
- **Keyword fields:** Stored for exact matching
- **Date fields:** Stored as ISO format
- **Nested fields:** Arrays for multi-value fields

**Step 3: Bulk Indexing**

Documents are indexed in batches:
- Bulk API for efficiency
- Upsert by document ID
- Refresh strategy for immediate searchability

### Output Structure

**Neo4j:**

- Graph nodes and relationships
- Queryable via Cypher
- RDF/Turtle export in `/data/3_rdf/<platform>/`

**Elasticsearch:**

- Searchable documents in indices
- Queryable via REST API
- Optimized for full-text search

**RDF Files:**

```
/data/3_rdf/hf/2025-01-15_12-00-00_abc123/
├── mlmodels.ttl
├── datasets.ttl
├── articles.ttl
└── mlmodels_load_report.json
```

### Data Characteristics

- **Neo4j:** Graph structure (nodes + relationships)
- **Elasticsearch:** Document structure (searchable fields)
- **RDF:** Semantic web format (triples)
- **Volume:** Same as normalized (one-to-one loading)

---

## Complete Flow Example

Let's trace a single model through the entire pipeline:

### Example: BERT Model from HuggingFace

**Step 1: Extraction**
```
HuggingFace Hub API
    ↓ (API call)
HF Extractor
    ↓
/data/1_raw/hf/2025-01-15_12-00-00_abc123/hf_models.json
{
  "modelId": "bert-base-uncased",
  "author": "google",
  "pipeline_tag": "fill-mask",
  "tags": ["pytorch", "transformers", "bert"],
  "createdAt": "2020-01-01T00:00:00Z"
}
```

**Step 2: Entity Discovery**
```
Extractor identifies:
- Datasets: ["squad", "glue"]
- Base models: []
- Keywords: ["pytorch", "transformers", "bert"]
```

**Step 3: Entity Enrichment**
```
Fetches full metadata for:
- SQuAD dataset
- GLUE dataset
Saves to hf_datasets_specific.json
```

**Step 4: Transformation**
```
Raw JSON
    ↓ (map_basic_properties)
Partial Schema 1: Basic Properties
    ↓ (map_ml_task)
Partial Schema 2: ML Task
    ↓ (merge)
Merged Schema
    ↓ (validate)
FAIR4ML Model
    ↓
/data/2_normalized/hf/.../mlmodels.json
{
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "mlTask": ["fill-mask"],
  "trainedOn": ["https://huggingface.co/datasets/squad"],
  ...
}
```

**Step 5: Loading to Neo4j**
```
FAIR4ML JSON
    ↓ (convert to RDF)
RDF Triples
    ↓ (persist)
Neo4j Graph:
  (Model:bert-base-uncased)-[:USES_DATASET]->(Dataset:squad)
  (Model:bert-base-uncased)-[:USES_DATASET]->(Dataset:glue)
```

**Step 6: Loading to Elasticsearch**
```
FAIR4ML JSON
    ↓ (build document)
Elasticsearch Document
    ↓ (index)
Searchable in Elasticsearch:
  Query: "BERT" → Returns bert-base-uncased
  Query: "fill-mask" → Returns bert-base-uncased
```

**Step 7: Serving to Users**
```
User searches "BERT" in frontend
    ↓
Backend API queries Elasticsearch
    ↓
Returns BERT model with metadata
    ↓
User clicks "Related Datasets"
    ↓
Backend API queries Neo4j
    ↓
Returns SQuAD and GLUE datasets
```

---

## Data Lineage

The system maintains complete data lineage:

1. **Extraction Metadata:** Tracks source, method, timestamp
2. **Transformation Metadata:** Tracks mapping functions, validation status
3. **Loading Metadata:** Tracks load statistics, errors
4. **Run Folders:** Group all artifacts from one run
5. **Dagster Lineage:** Tracks asset dependencies and execution

**Example Lineage:**
```
hf_raw_models (extraction)
    ↓
hf_models_normalized (transformation)
    ↓
hf_load_models_to_neo4j (loading)
```

---

## Error Handling and Recovery

### Error Handling Strategy

**Extraction:**

- Continue on individual model failures
- Log errors to error files
- Return partial results

**Transformation:**

- Continue on individual model failures
- Save validation errors separately
- Return validated models + error list

**Loading:**

- Retry on transient failures
- Log errors to load reports
- Continue with other entities

### Recovery

**Re-run Failed Assets:**

- Dagster allows re-materializing failed assets
- Idempotent operations ensure safe re-runs
- Can re-run from any stage

**Incremental Updates:**

- Only process new/changed data
- Upsert logic handles updates
- Maintains data consistency

---

## Performance Characteristics

### Extraction

- **Speed:** ~10-100 models/second (depends on API rate limits)
- **Bottlenecks:** API rate limits, network latency
- **Optimization:** Parallel threads, connection pooling

### Transformation

- **Speed:** ~100-1000 models/second (CPU-bound)
- **Bottlenecks:** CPU for validation, I/O for file operations
- **Optimization:** Parallel property extraction, batch processing

### Loading

- **Speed:** ~50-500 models/second (depends on target system)
- **Bottlenecks:** Database write speed, network latency
- **Optimization:** Batch operations, bulk APIs, connection pooling

---

## Related Documentation

- **[Architecture Overview](overview.md)** - High-level system overview
- **[System Design](system-design.md)** - Design decisions and rationale
- **[Component Details](components.md)** - Deep dive into each component
- **[Extractors Code Flow](../extractors/code-flow.md)** - Detailed extraction flow
- **[Transformers Code Flow](../transformers/code-flow.md)** - Detailed transformation flow
- **[Loaders Code Flow](../loaders/code-flow.md)** - Detailed loading flow
