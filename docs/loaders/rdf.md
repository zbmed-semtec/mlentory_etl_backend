# RDF Exporter

This comprehensive guide explains how MLentory exports FAIR4ML data as RDF (Resource Description Framework), enabling integration with the semantic web and other FAIR data systems. Understanding RDF export is crucial for researchers who need to integrate MLentory data with other research tools, for systems that consume semantic web data, and for anyone interested in FAIR data principles.

---

## Understanding RDF: The Foundation of the Semantic Web

**RDF** (Resource Description Framework) is a fundamental standard for representing information on the web in a way that machines can understand and link together. Think of it as a universal language for describing things and their relationships—not just for humans to read, but for computers to process, query, and connect.

### Why RDF Matters

The traditional web is built for humans. HTML pages are designed to be read by people, with formatting and layout that make information visually appealing but semantically opaque to machines. RDF flips this: it's designed for machines first, enabling automated processing, linking, and querying of data across different systems.

**Semantic Web Integration** means that MLentory data can be understood by any system that speaks RDF. This includes research platforms like Zenodo, academic databases, knowledge graphs like Wikidata, and specialized ML research tools. Instead of building custom integrations for each system, RDF provides a universal format.

**FAIR Compliance** is built into RDF. The FAIR principles (Findable, Accessible, Interoperable, Reusable) are naturally supported by RDF's design:

- **Findable**: RDF uses unique identifiers (URIs) for everything
- **Accessible**: RDF can be retrieved using standard web protocols
- **Interoperable**: RDF works with any system that understands semantic web standards
- **Reusable**: RDF provides rich metadata that enables informed reuse

**Queryability** is a key advantage. RDF data can be queried using SPARQL, a powerful query language similar to SQL but designed for graph data. This enables complex queries like "Find all models that use datasets also used by model X" or "Show me the lineage of all models based on BERT."

RDF uses a simple triple structure: subject-predicate-object. Each triple represents one fact about the data, enabling flexible and extensible data representation.
*Figure 1: RDF represents information as triples (subject-predicate-object), creating a graph structure that enables powerful queries and linking across systems.*

### Understanding RDF Triples

RDF represents information as **triples**, which are statements with three parts:

**Subject** is what you're describing (the thing). In our case, this is typically a model, identified by its URL.

**Predicate** is the property or relationship (the verb). This might be "has name" or "performs task" or "uses dataset."

**Object** is the value or target (the object of the statement). This could be a string value, a number, a date, or another resource.

The structure is: **Subject → Predicate → Object**

For example:
```
<https://huggingface.co/bert-base-uncased>
  → schema:name
  → "bert-base-uncased"
```

This reads as: "The model at https://huggingface.co/bert-base-uncased has the name 'bert-base-uncased'."

Triples can be linked together to create rich graphs. For example:
```
<https://huggingface.co/bert-base-uncased>
  → schema:name
  → "bert-base-uncased" ;
  → fair4ml:mlTask
  → "fill-mask" ;
  → fair4ml:trainedOn
  → <https://huggingface.co/datasets/wikipedia> .
```

This creates a small graph showing that BERT has a name, performs a task, and was trained on Wikipedia. These relationships can be followed, queried, and extended, creating a rich knowledge graph of ML models and their connections.

---

## RDF Format: Turtle

**Turtle** (Terse RDF Triple Language) is a human-readable RDF format. It's the format we use for RDF export.

### Basic Syntax

**Prefixes:**
```turtle
@prefix schema: <https://schema.org/> .
@prefix fair4ml: <https://w3id.org/fair4ml#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
```

**Triples:**
```turtle
<https://huggingface.co/bert-base-uncased>
  a fair4ml:MLModel ;
  schema:name "bert-base-uncased" ;
  schema:url "https://huggingface.co/bert-base-uncased" ;
  fair4ml:mlTask "fill-mask" .
```

**Key Syntax:**

- `a` = `rdf:type` (shorthand)
- `;` = Continue with same subject
- `.` = End of subject's triples
- `,` = Multiple objects for same predicate

---

## Export Process

### Step 1: Read Normalized Data

**Input:**
- `/data/normalized/<source>/<timestamp>_<uuid>/mlmodels.json`

**What happens:**

- Load FAIR4ML JSON files
- Parse model structure
- Extract all properties

### Step 2: Convert to RDF Triples

**What happens:**

- Create subject IRI for each model
- Map FAIR4ML properties to RDF predicates
- Create triples for each property
- Handle different data types (strings, dates, lists, URIs)

**Example:**
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
  schema:identifier "https://huggingface.co/bert-base-uncased" ;
  schema:name "bert-base-uncased" ;
  fair4ml:mlTask "fill-mask" .
```

### Step 3: Generate Turtle File

**What happens:**

- Write RDF triples in Turtle format
- Include namespace prefixes
- Format for readability
- Save to file

**Output:**
- `/data/rdf/<source>/<timestamp>_<uuid>/models.ttl`

---

## FAIR4ML to RDF Mapping

### Namespaces

**Standard Namespaces:**

- `schema:` → `https://schema.org/`
- `fair4ml:` → `https://w3id.org/fair4ml#`
- `rdf:` → `http://www.w3.org/1999/02/22-rdf-syntax-ns#`
- `rdfs:` → `http://www.w3.org/2000/01/rdf-schema#`
- `xsd:` → `http://www.w3.org/2001/XMLSchema#`
- `codemeta:` → `https://w3id.org/codemeta/`

### Property Mapping

**Core Identification:**

- `identifier` → `schema:identifier`
- `name` → `schema:name`
- `url` → `schema:url`

**Authorship:**

- `author` → `schema:author`
- `sharedBy` → `fair4ml:sharedBy`

**Temporal:**

- `dateCreated` → `schema:dateCreated` (xsd:dateTime)
- `dateModified` → `schema:dateModified` (xsd:dateTime)
- `datePublished` → `schema:datePublished` (xsd:dateTime)

**ML-Specific:**

- `mlTask` → `fair4ml:mlTask`
- `modelCategory` → `fair4ml:modelCategory`
- `fineTunedFrom` → `fair4ml:fineTunedFrom`
- `trainedOn` → `fair4ml:trainedOn`
- `evaluatedOn` → `fair4ml:evaluatedOn`

**Description:**

- `description` → `schema:description`
- `keywords` → `schema:keywords`
- `license` → `schema:license`

### Subject IRI Generation

**Format:**
```
https://huggingface.co/{modelId}
```

**Example:**
```python
model_id = "bert-base-uncased"
subject_iri = "https://huggingface.co/bert-base-uncased"
```

**Benefits:**
- Unique identifiers
- Resolvable URLs
- Semantic web compatible

---

## Complete Example

### Input (FAIR4ML JSON)

```json
{
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "dateCreated": "2020-01-01T00:00:00Z",
  "mlTask": ["fill-mask"],
  "modelCategory": ["transformer"],
  "keywords": ["bert", "nlp"],
  "license": "apache-2.0"
}
```

### Output (RDF/Turtle)

```turtle
@prefix schema: <https://schema.org/> .
@prefix fair4ml: <https://w3id.org/fair4ml#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

<https://huggingface.co/bert-base-uncased>
  a fair4ml:MLModel ;
  schema:identifier "https://huggingface.co/bert-base-uncased" ;
  schema:name "bert-base-uncased" ;
  schema:url "https://huggingface.co/bert-base-uncased" ;
  schema:author "google" ;
  schema:dateCreated "2020-01-01T00:00:00Z"^^xsd:dateTime ;
  fair4ml:mlTask "fill-mask" ;
  fair4ml:modelCategory "transformer" ;
  schema:keywords "bert", "nlp" ;
  schema:license "apache-2.0" .
```

---

## Data Type Handling

### Strings

**Simple strings:**
```turtle
schema:name "bert-base-uncased" .
```

### Dates

**ISO 8601 with datatype:**
```turtle
schema:dateCreated "2020-01-01T00:00:00Z"^^xsd:dateTime .
```

### Lists

**Multiple values:**
```turtle
schema:keywords "bert", "nlp", "transformer" .
```

**Or separate triples:**
```turtle
schema:keywords "bert" ;
schema:keywords "nlp" ;
schema:keywords "transformer" .
```

### URIs

**As objects (relationships):**
```turtle
fair4ml:fineTunedFrom <https://huggingface.co/bert-base> .
```

**As literals:**
```turtle
schema:identifier "https://huggingface.co/bert-base-uncased" .
```

---

## Relationships

### Model → Dataset

```turtle
<https://huggingface.co/bert-base-uncased>
  fair4ml:trainedOn <https://huggingface.co/datasets/wikipedia> ;
  fair4ml:evaluatedOn <https://huggingface.co/datasets/glue> .
```

### Model → Paper

```turtle
<https://huggingface.co/bert-base-uncased>
  schema:citation <https://arxiv.org/abs/1810.04805> .
```

### Model → Model

```turtle
<https://huggingface.co/bert-finetuned>
  fair4ml:fineTunedFrom <https://huggingface.co/bert-base-uncased> .
```

---

## Usage Examples

### Via Dagster UI

1. Open Dagster UI (http://localhost:3000)
2. Navigate to Assets tab
3. Find `hf_load_models_rdf` asset
4. Click "Materialize"
5. RDF export happens automatically during Neo4j loading

### Via Command Line

**Load models (includes RDF export):**
```bash
dagster asset materialize -m etl.repository -a hf_load_models_rdf
```

**Export only (without loading to Neo4j):**
```python
from etl_loaders.rdf_loader import build_and_persist_models_rdf

stats = build_and_persist_models_rdf(
    json_path="/data/normalized/hf/mlmodels.json",
    config=None,  # Don't load to Neo4j
    output_ttl_path="/data/rdf/hf/models.ttl"
)
```

### Programmatic Usage

**Standalone export:**
```python
from rdflib import Graph
from etl_loaders.rdf_store import namespaces, open_graph
from etl_loaders.rdf_loader import build_model_triples
import json

# Load FAIR4ML JSON
with open("/data/normalized/hf/mlmodels.json") as f:
    models = json.load(f)

# Create RDF graph
graph = open_graph()

# Convert each model to RDF
for model in models:
    build_model_triples(graph, model)

# Export to Turtle
graph.serialize(destination="/data/rdf/hf/models.ttl", format="turtle")
```

---

## Output Files

### File Structure

```
/data/rdf/<source>/
└── <timestamp>_<uuid>/
    ├── models.ttl          # Models in RDF/Turtle
    ├── datasets.ttl         # Datasets in RDF/Turtle
    └── papers.ttl           # Papers in RDF/Turtle
```

### File Format

**Turtle (.ttl):**

- Human-readable
- Standard RDF format
- Widely supported

**Alternative Formats:**

- JSON-LD (`.jsonld`)
- RDF/XML (`.rdf`)
- N-Triples (`.nt`)

---

## Using RDF Data

### SPARQL Queries

**Query RDF data:**
```sparql
PREFIX schema: <https://schema.org/>
PREFIX fair4ml: <https://w3id.org/fair4ml#>

SELECT ?model ?name ?task
WHERE {
  ?model a fair4ml:MLModel ;
         schema:name ?name ;
         fair4ml:mlTask ?task .
  FILTER(?task = "fill-mask")
}
```

### Integration with Other Systems

**FAIR Data Systems:**

- Link to other FAIR datasets
- Integrate with semantic web tools
- Enable cross-platform discovery

**Research Platforms:**

- Zenodo
- DataCite
- ORCID

**Knowledge Graphs:**

- Wikidata
- DBpedia
- Custom knowledge graphs

---

## Performance Considerations

### Large Files

**Streaming:**

- Process models in batches
- Write incrementally
- Avoid loading entire graph in memory

**Compression:**

- Use `.ttl.gz` for large files
- Reduces storage and transfer time

### Optimization Tips

1. **Batch Processing:** Process multiple models at once
2. **Incremental Export:** Only export new/changed models
3. **Compression:** Compress large Turtle files
4. **Validation:** Validate RDF before writing

---

## Troubleshooting

### Invalid RDF

**Problem:** RDF file is invalid

**Solutions:**

- Validate with RDF validator
- Check namespace prefixes
- Verify IRI format
- Review data types

### Large File Size

**Problem:** RDF file is too large

**Solutions:**

- Split into multiple files
- Use compression
- Filter unnecessary properties
- Use streaming export

### Missing Properties

**Problem:** Some properties not exported

**Solutions:**

- Check property mapping
- Verify data exists in source
- Review transformation logic
- Check RDF conversion code

---

## Key Takeaways

1. **RDF** enables semantic web integration
2. **Turtle** is human-readable RDF format
3. **Triples** represent relationships
4. **FAIR4ML** maps cleanly to RDF
5. **Export** happens during Neo4j loading
6. **SPARQL** can query RDF data

---

## Next Steps

- See [Neo4j Loader](neo4j.md) - RDF is exported during Neo4j loading
- Check [FAIR4ML Schema](../schemas/fair4ml.md) - Property reference
- Explore [Architecture Overview](../architecture/overview.md) - System architecture
- Review [FAIR Principles](../concepts/fair4ml-schema.md#fair-principles) - Why RDF matters

---

## Resources

- **RDF 1.1 Primer:** [https://www.w3.org/TR/rdf11-primer/](https://www.w3.org/TR/rdf11-primer/)
- **Turtle Syntax:** [https://www.w3.org/TR/turtle/](https://www.w3.org/TR/turtle/)
- **SPARQL Query Language:** [https://www.w3.org/TR/sparql11-query/](https://www.w3.org/TR/sparql11-query/)
- **RDFLib Documentation:** [https://rdflib.readthedocs.io/](https://rdflib.readthedocs.io/)
