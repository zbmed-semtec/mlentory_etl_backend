# Neo4j Loader: Building the Knowledge Graph

The Neo4j loader is responsible for converting normalized FAIR4ML models into RDF triples and storing them in Neo4j as a knowledge graph. This process enables relationship queries, model lineage tracking, and graph-based recommendations. Understanding how the Neo4j loader works helps you appreciate how MLentory builds and maintains its knowledge graph.

---

## Overview: Why Neo4j for ML Model Metadata?

Graph databases excel at relationship queries, path finding, and pattern matching—exactly what you need for ML model metadata. When you want to find "all models that use this dataset" or "trace a model's lineage through fine-tuning," graph databases make these queries fast and intuitive.

**The Neo4j loader's job** is to take FAIR4ML data (which is already standardized and validated) and convert it into a graph structure that Neo4j can store and query efficiently. This involves converting JSON to RDF triples, creating graph nodes and relationships, and ensuring data consistency.

![Neo4j Loading Process](images/neo4j-loading-process.png)
*Figure 1: The Neo4j loader converts FAIR4ML JSON to RDF triples, then loads them into Neo4j as a knowledge graph.*

### Why Neo4j?

**Graph databases excel at:**
- **Relationship queries:** Finding connected entities is fast because relationships are stored directly, not computed through JOINs
- **Path finding:** Discovering connections between entities (like model lineage) is a natural graph operation
- **Pattern matching:** Finding subgraphs that match patterns (like "models using datasets also used by other models") is efficient
- **Traversals:** Following relationships from one node to explore the graph is intuitive and fast

**Perfect for ML metadata:**
- Models use datasets (for training and evaluation)
- Models cite papers (research publications)
- Models are based on other models (fine-tuning, transfer learning)
- Models are created by authors and published by organizations

These relationships are crucial for discovery and recommendation, and graph databases make querying them efficient.

---

## Loading Process: From FAIR4ML to Knowledge Graph

The loading process transforms FAIR4ML JSON into a Neo4j knowledge graph through several stages:

### Step 1: Reading Normalized Data

**Input:** The loader reads FAIR4ML JSON files from the transformation stage. These files are located in `/data/normalized/<source>/<timestamp>_<uuid>/mlmodels.json` and contain validated, standardized model metadata.

**What happens:** The loader reads these JSON files and parses the FAIR4ML structure. Each model is a JSON object with properties like `identifier`, `name`, `mlTask`, `trainedOn`, `evaluatedOn`, etc. The loader validates that the data conforms to the FAIR4ML schema before proceeding.

**Why this matters:** Starting with validated FAIR4ML data ensures that the graph will be consistent and complete. If data doesn't conform to the schema, it's caught here before it reaches Neo4j.

### Step 2: Converting to RDF Triples

**What happens:** Each FAIR4ML model is converted to RDF (Resource Description Framework) triples. RDF is a standard format for representing knowledge graphs, using subject-predicate-object triples.

**Example conversion:**
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

**Why RDF?** RDF is a standard format that enables semantic web integration. By converting to RDF, we can:
- Use standard vocabularies (FAIR4ML, schema.org)
- Enable SPARQL queries (in addition to Cypher)
- Export to RDF/Turtle format for interoperability
- Integrate with other FAIR data systems

**Subject IRI generation:** Each model gets a unique identifier (IRI) based on its source URL. For HuggingFace models, this is `https://huggingface.co/{modelId}`. This creates resolvable URLs that work in semantic web contexts.

### Step 3: Creating Graph Nodes

**What happens:** RDF triples are converted into Neo4j nodes. Each entity (Model, Dataset, Paper, Author, etc.) becomes a node with properties extracted from the RDF triples.

**Example:**
```cypher
CREATE (m:Model {
  id: "mlentory:model:xyz789",
  name: "bert-base-uncased",
  url: "https://huggingface.co/bert-base-uncased"
})
```

**Node properties:** Properties are extracted from RDF triples and stored on nodes. For example, `schema:name` becomes the `name` property, `fair4ml:mlTask` becomes the `mlTask` property, etc.

**Node labels:** Nodes are labeled with their types (Model, Dataset, Paper, etc.). These labels enable efficient queries (e.g., "find all Model nodes") and organize the graph.

### Step 4: Creating Relationships

**What happens:** Relationships between entities are created based on FAIR4ML properties. For example, if a model has `trainedOn: [dataset]`, a `TRAINED_ON` relationship is created from the model to the dataset.

**Example:**
```cypher
MATCH (m:Model {id: "mlentory:model:xyz789"})
MATCH (d:Dataset {id: "mlentory:dataset:abc123"})
CREATE (m)-[:USES_DATASET]->(d)
```

**Relationship types:** Different FAIR4ML properties map to different relationship types:
- `trainedOn` → `TRAINED_ON`
- `evaluatedOn` → `EVALUATED_ON`
- `citesPaper` → `CITES_PAPER`
- `basedOn` → `BASED_ON`
- `author` → `CREATED_BY`

**Relationship properties:** Relationships can have properties too. For example, a `USES_DATASET` relationship might have a `purpose` property indicating whether it's for training or evaluation.

### Step 5: Exporting to Turtle (Optional)

**What happens:** The loader can optionally export RDF data to Turtle format (a human-readable RDF syntax). This creates files like `/data/rdf/<source>/models.ttl` that can be used for semantic web integration.

**Why export?** RDF/Turtle files enable:
- Integration with other semantic web systems
- FAIR data compliance
- Sharing knowledge graphs with other researchers
- Backup and archival of graph data

**Format:** Turtle files use a compact, human-readable syntax that's easier to read than raw RDF/XML but contains the same information.

---

## RDF Conversion: Mapping FAIR4ML to RDF

Understanding how FAIR4ML properties map to RDF helps you understand the graph structure:

### FAIR4ML to RDF Mapping

**Core Properties** use schema.org vocabulary:
- `identifier` → `schema:identifier` (the model's unique identifier)
- `name` → `schema:name` (human-readable name)
- `url` → `schema:url` (primary access URL)
- `author` → `schema:author` (model creator)
- `description` → `schema:description` (full description)
- `license` → `schema:license` (license information)

**ML-Specific Properties** use FAIR4ML vocabulary:
- `mlTask` → `fair4ml:mlTask` (ML tasks the model addresses)
- `modelCategory` → `fair4ml:modelCategory` (model architecture type)
- `fineTunedFrom` → `fair4ml:fineTunedFrom` (base model for fine-tuning)
- `trainedOn` → `fair4ml:trainedOn` (training datasets)
- `evaluatedOn` → `fair4ml:evaluatedOn` (evaluation datasets)

**Temporal Properties** use schema.org with proper data types:
- `dateCreated` → `schema:dateCreated` (xsd:dateTime)
- `dateModified` → `schema:dateModified` (xsd:dateTime)
- `datePublished` → `schema:datePublished` (xsd:dateTime)

### Subject IRI Generation

**Format:** Each model gets a unique identifier (IRI) based on its source:
```
https://huggingface.co/{modelId}
```

**Example:**
```python
model_id = "bert-base-uncased"
subject_iri = "https://huggingface.co/bert-base-uncased"
```

**Benefits:**
- **Unique identifiers:** Each model has a globally unique identifier
- **Resolvable URLs:** Identifiers are URLs that can be resolved (in some cases)
- **Semantic web compatible:** IRIs work in semantic web contexts
- **Source traceability:** The IRI shows where the model came from

---

## Graph Structure: Understanding the Knowledge Graph

The Neo4j knowledge graph has a specific structure that enables powerful queries:

### Nodes: Entities in the Graph

**Model Nodes** represent ML models:
```cypher
(:Model {
  id: "mlentory:model:xyz789",
  name: "bert-base-uncased",
  url: "https://huggingface.co/bert-base-uncased",
  mlTask: ["fill-mask"],
  modelCategory: ["transformer"]
})
```

Model nodes store all the properties from FAIR4ML, making them queryable and searchable.

**Dataset Nodes** represent training/evaluation datasets:
```cypher
(:Dataset {
  id: "mlentory:dataset:abc123",
  name: "SQuAD",
  url: "https://huggingface.co/datasets/squad"
})
```

Dataset nodes enable queries like "find all models using this dataset" or "find datasets used by transformer models."

**Paper Nodes** represent research publications:
```cypher
(:Paper {
  id: "mlentory:paper:def456",
  title: "BERT: Pre-training of Deep Bidirectional Transformers",
  arxiv_id: "1810.04805"
})
```

Paper nodes enable queries like "find all papers cited by transformer models" or "find models based on this paper."

**Other Node Types:**
- `Author` - Model/paper authors
- `Organization` - Publishing institutions/companies
- `Task` - ML tasks
- `License` - License information

### Relationships: Connections Between Entities

**Model → Dataset Relationships:**
```cypher
(Model)-[:USES_DATASET]->(Dataset)
(Model)-[:TRAINED_ON]->(Dataset)
(Model)-[:EVALUATED_ON]->(Dataset)
```

These relationships enable queries like "find all models using SQuAD" or "find datasets used by BERT."

**Model → Paper Relationships:**
```cypher
(Model)-[:CITES_PAPER]->(Paper)
(Model)-[:BASED_ON_PAPER]->(Paper)
```

These relationships enable queries like "find all papers cited by transformer models" or "find models based on the BERT paper."

**Model → Model Relationships:**
```cypher
(Model)-[:BASED_ON]->(Model)
(Model)-[:FINE_TUNED_FROM]->(Model)
```

These relationships create model family trees, enabling lineage queries like "find all models based on BERT" or "trace this model's lineage."

**Model → Author/Organization Relationships:**
```cypher
(Model)-[:CREATED_BY]->(Author)
(Model)-[:PUBLISHED_BY]->(Organization)
```

These relationships enable queries like "find all models by Google" or "find models created by this researcher."

---

## Neo4j Integration: Using n10s for RDF

Neo4j's **n10s plugin** provides RDF integration, enabling seamless conversion between RDF and Neo4j's native graph format.

### What is n10s?

**n10s** (Neosemantics) is a Neo4j plugin that provides:
- **RDF import/export:** Convert between RDF and Neo4j's native format
- **SPARQL queries:** Query Neo4j using SPARQL (in addition to Cypher)
- **Semantic web compatibility:** Maintain RDF semantics in Neo4j
- **Vocabulary management:** Handle RDF vocabularies (like FAIR4ML, schema.org)

**How it works:** n10s stores RDF triples in Neo4j while maintaining RDF semantics. This means you can:
- Load RDF data into Neo4j
- Query using Cypher (for graph operations)
- Query using SPARQL (for semantic web operations)
- Export back to RDF/Turtle format

### Connection Configuration

**Environment Variables:**
- `NEO4J_URI`: Neo4j connection URI (default: `bolt://localhost:7687`)
- `NEO4J_USER`: Username (default: `neo4j`)
- `NEO4J_PASSWORD`: Password (required)

**Example:**
```python
from rdflib_neo4j import Neo4jStoreConfig

config = Neo4jStoreConfig(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password"
)
```

This configuration is used to connect to Neo4j and load RDF data using n10s.

---

## Usage Examples: Running the Loader

The Neo4j loader can be used in several ways:

### Via Dagster UI

**Steps:**
1. Open Dagster UI (http://localhost:3000)
2. Navigate to Assets tab
3. Find `hf_load_models_to_neo4j` asset (or similar for other sources)
4. Click "Materialize"
5. Watch progress in real-time

**Benefits:** Visual interface, real-time progress, easy to see logs and errors.

### Via Command Line

**Load models:**
```bash
dagster asset materialize -m etl.repository -a hf_load_models_to_neo4j
```

**Load with dependencies:**
```bash
# This automatically runs transformation first
dagster asset materialize -m etl.repository -a hf_load_models_to_neo4j+
```

The `+` notation means "include dependencies," so this will automatically run the transformation stage first if needed.

### Programmatic Usage

**Standalone (without Dagster):**
```python
from etl_loaders.hf_rdf_loader import build_and_persist_models_rdf
from rdflib_neo4j import Neo4jStoreConfig

config = Neo4jStoreConfig(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password"
)

stats = build_and_persist_models_rdf(
    json_path="/data/normalized/hf/mlmodels.json",
    config=config,
    output_ttl_path="/data/rdf/hf/models.ttl"
)

print(f"Loaded {stats['models_loaded']} models")
print(f"Created {stats['relationships_created']} relationships")
```

This allows you to use the loader programmatically, useful for testing, automation, or integration with other systems.

---

## Query Examples: Exploring the Knowledge Graph

Once data is loaded into Neo4j, you can query it using Cypher. Here are practical examples:

### Find Models Using a Dataset

```cypher
MATCH (m:Model)-[:USES_DATASET]->(d:Dataset {name: "SQuAD"})
RETURN m.name, m.mlTask
```

This query finds all models that use the SQuAD dataset, returning their names and ML tasks. This is useful for understanding which models have been evaluated on SQuAD or understanding SQuAD's usage in the ML community.

### Find Related Models

```cypher
// Models that share datasets with BERT
MATCH (bert:Model {name: "BERT"})-[:USES_DATASET]->(d:Dataset)
      <-[:USES_DATASET]-(related:Model)
WHERE related.name <> "BERT"
RETURN DISTINCT related.name
```

This finds models that share datasets with BERT. Models using the same datasets are likely similar or related, making this useful for discovery and recommendation.

### Model Lineage

```cypher
// All models in BERT's lineage
MATCH path = (base:Model {name: "BERT"})<-[:BASED_ON*]-(derived:Model)
RETURN [node in nodes(path) | node.name] as lineage
```

This finds all models derived from BERT, regardless of how many fine-tuning steps removed they are. The `*` means "any number of relationships," and the path shows the complete lineage chain.

### Recommendation Query

```cypher
// Recommend models similar to user's favorite
MATCH (fav:Model {id: $favorite_model_id})
      -[:USES_DATASET|CITES_PAPER|BASED_ON]->(entity)
      <-[:USES_DATASET|CITES_PAPER|BASED_ON]-(recommended:Model)
WHERE recommended.id <> $favorite_model_id
RETURN recommended.name, COUNT(entity) as similarity_score
ORDER BY similarity_score DESC
LIMIT 10
```

This finds models similar to a user's favorite by finding models that share relationships (datasets, papers, or base models). Models with more shared relationships are ranked higher. This is the foundation of graph-based recommendation systems.

---

## Output Files: RDF/Turtle Export

The loader can optionally export RDF data to Turtle format:

### RDF/Turtle Export

**Location:** `/data/rdf/<source>/<timestamp>_<uuid>/models.ttl`

**Format:**
```turtle
@prefix fair4ml: <https://w3id.org/fair4ml#> .
@prefix schema: <https://schema.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .

<https://huggingface.co/bert-base-uncased>
  a fair4ml:MLModel ;
  schema:name "bert-base-uncased" ;
  schema:url "https://huggingface.co/bert-base-uncased" ;
  fair4ml:mlTask "fill-mask" ;
  schema:author "google" .
```

**Benefits:**
- **Semantic web compatible:** Can be used with other RDF tools
- **FAIR data compliance:** Supports FAIR data principles
- **Integration:** Can be imported into other systems
- **Human-readable:** Turtle format is easier to read than RDF/XML
- **Backup:** Provides a backup of graph data in a standard format

---

## Performance Optimization: Making Loading Efficient

Loading large amounts of data into Neo4j requires optimization:

### Batch Processing

**Batch RDF triple insertion:** Process models in batches rather than one at a time. This reduces overhead and improves performance.

**Example:**
```python
# Process 100 models at a time
batch_size = 100
for i in range(0, len(models), batch_size):
    batch = models[i:i+batch_size]
    # Convert batch to RDF
    # Insert batch into Neo4j
    # Commit transaction
```

**Benefits:** Faster loading (less overhead per model), better transaction management (smaller transactions are faster), and easier error recovery (if one batch fails, others continue).

### Parallel Processing

**Multi-threaded loading:** Process multiple models simultaneously using multiple threads. This utilizes all available CPU cores.

**Considerations:** 
- Use connection pooling to avoid creating too many connections
- Balance load across threads (don't overload Neo4j)
- Handle errors gracefully (one thread failure shouldn't stop others)

### Indexing

**Create indexes for:** Model IDs, Dataset IDs, Paper IDs, and relationship types. Indexes make queries faster by enabling Neo4j to find nodes quickly.

**Example:**
```cypher
CREATE INDEX model_id_index FOR (m:Model) ON (m.id)
CREATE INDEX dataset_id_index FOR (d:Dataset) ON (d.id)
```

**Benefits:** Faster queries (indexes enable fast lookups), better performance (queries don't need to scan all nodes), and scalability (performance doesn't degrade as graph grows).

---

## Troubleshooting: Common Issues and Solutions

When loading data into Neo4j, you might encounter issues:

### Connection Errors

**Problem:** Cannot connect to Neo4j

**Solutions:**
- Check Neo4j is running (`docker ps` or `systemctl status neo4j`)
- Verify connection URI (should be `bolt://localhost:7687` for local)
- Check credentials (username and password)
- Review firewall settings (if Neo4j is remote)

### Memory Issues

**Problem:** Out of memory during loading

**Solutions:**
- Reduce batch size (process fewer models at a time)
- Process in smaller chunks (split large datasets)
- Increase Neo4j heap size (in `neo4j.conf`: `dbms.memory.heap.max_size=2G`)
- Use streaming for large datasets (don't load everything into memory)

### Performance Issues

**Problem:** Loading is slow

**Solutions:**
- Enable batch processing (process multiple models together)
- Create indexes (faster lookups)
- Use parallel processing (utilize all CPU cores)
- Optimize transaction size (smaller transactions are faster)
- Check Neo4j configuration (memory, page cache, etc.)

---

## Key Takeaways

The Neo4j loader converts FAIR4ML JSON into a knowledge graph stored in Neo4j. This process involves converting to RDF triples, creating graph nodes and relationships, and optionally exporting to Turtle format. The resulting knowledge graph enables powerful relationship queries, model lineage tracking, and graph-based recommendations.

Understanding how the Neo4j loader works helps you appreciate how MLentory builds and maintains its knowledge graph, and how to query it effectively for discovery and recommendation.

---

## Next Steps

- See [Elasticsearch Loader](elasticsearch.md) - How we index data for search
- Check [RDF Exporter](rdf.md) - Semantic web export details
- Explore [Graph Databases](../concepts/graph-databases.md) - Graph database concepts
- Review [Neo4j Queries Examples](../examples/neo4j-queries.md) - Practical query examples

---

## Resources

- **Neo4j Documentation:** [https://neo4j.com/docs/](https://neo4j.com/docs/) - Comprehensive Neo4j guide
- **n10s Plugin:** [https://neo4j.com/labs/neosemantics/](https://neo4j.com/labs/neosemantics/) - RDF integration for Neo4j
- **RDFLib:** [https://rdflib.readthedocs.io/](https://rdflib.readthedocs.io/) - Python RDF library
- **Cypher Manual:** [https://neo4j.com/docs/cypher-manual/](https://neo4j.com/docs/cypher-manual/) - Complete Cypher reference
