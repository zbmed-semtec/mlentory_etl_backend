# Elasticsearch Loader: Enabling Fast Full-Text Search

The Elasticsearch loader indexes normalized FAIR4ML models as searchable documents, enabling fast full-text search, filtering, and faceted search across all ML models. Understanding how the Elasticsearch loader works helps you appreciate how MLentory enables discovery through search.

---

## Overview: Why Elasticsearch for ML Model Discovery?

When users search for ML models, they don't always know exact model names or identifiers. They might search for "models for sentiment analysis" or "transformer models for text classification." These queries require full-text search—searching through descriptions, names, and other text fields.

**Elasticsearch** is a search engine built on Apache Lucene, designed specifically for full-text search. Unlike databases optimized for exact matches or relationship queries, Elasticsearch analyzes text, builds indexes, and provides relevance ranking that makes discovery intuitive.

![Elasticsearch Indexing Process](images/elasticsearch-indexing-process.png)
*Figure 1: The Elasticsearch loader converts FAIR4ML JSON into searchable documents, enabling fast full-text search and filtering.*

### Why Elasticsearch?

**Elasticsearch excels at:**
- **Full-text search:** Fast keyword search across descriptions, names, and other text fields
- **Filtering:** Filter by ML tasks, licenses, authors, and other structured fields
- **Faceted search:** Count results by category (e.g., "how many models for each task?")
- **Autocomplete:** Suggest search terms as users type
- **Aggregations:** Analyze data distributions (e.g., "most common ML tasks")

**Perfect for ML model discovery:**
- Search by description ("models for sentiment analysis")
- Filter by ML tasks ("text-classification")
- Find models by keywords ("bert", "transformer", "nlp")
- Discover similar models through text similarity

These capabilities make Elasticsearch essential for MLentory's search functionality.

---

## Indexing Process: From FAIR4ML to Searchable Documents

The indexing process transforms FAIR4ML JSON into Elasticsearch documents through several stages:

### Step 1: Reading Normalized Data

**Input:** The loader reads FAIR4ML JSON files from the transformation stage. These files are located in `/data/normalized/<source>/<timestamp>_<uuid>/mlmodels.json` and contain validated, standardized model metadata.

**What happens:** The loader reads these JSON files and parses the FAIR4ML structure. Each model is a JSON object with properties like `identifier`, `name`, `description`, `mlTask`, `keywords`, etc. The loader extracts searchable fields from this structure.

**Why this matters:** Starting with validated FAIR4ML data ensures that search results will be consistent and complete. If data doesn't conform to the schema, it's caught before indexing.

### Step 2: Building Searchable Documents

**What happens:** Each FAIR4ML model is converted into an Elasticsearch document. The document structure is optimized for search, with fields mapped to appropriate types (Text for full-text search, Keyword for exact matches).

**Document Structure:**
```json
{
  "db_identifier": "mlentory:model:xyz789",
  "name": "bert-base-uncased",
  "description": "BERT model for masked language modeling",
  "shared_by": "google",
  "license": "apache-2.0",
  "ml_tasks": ["fill-mask"],
  "keywords": ["bert", "transformer", "nlp"],
  "platform": "huggingface"
}
```

**Field mapping:** Different FAIR4ML properties map to different Elasticsearch field types:
- `name`, `description` → Text fields (full-text search)
- `db_identifier`, `license`, `platform` → Keyword fields (exact match)
- `ml_tasks`, `keywords` → Keyword arrays (multi-value, exact match)

**Why this structure?** Text fields are analyzed (tokenized, lowercased, stemmed) for full-text search. Keyword fields are stored exactly as-is for filtering and exact matches. This dual approach enables both search and filtering.

### Step 3: Indexing Documents

**What happens:** Documents are indexed into Elasticsearch in batches. The loader creates or updates the index, sets up field mappings, and indexes documents. After indexing, the index is refreshed to make documents immediately searchable.

**Batch processing:** Documents are indexed in batches (typically 100-1000 at a time) for efficiency. This reduces overhead and improves performance.

**Upsert logic:** If a document with the same `db_identifier` already exists, it's updated rather than duplicated. This ensures that re-indexing updates existing documents rather than creating duplicates.

**Refresh strategy:** The index can be refreshed immediately (documents searchable right away) or delayed (faster indexing, documents searchable after refresh). For large datasets, delayed refresh is more efficient.

### Step 4: Verifying Indexing

**What happens:** After indexing, the loader verifies that indexing succeeded:
- Checks document count (ensures all documents were indexed)
- Verifies search works (tests a sample query)
- Reports statistics (models indexed, errors encountered)

**Why verification matters:** Catching indexing errors early prevents search issues. If some documents fail to index, you want to know immediately so you can fix the problem.

---

## Document Mapping: Defining Searchable Fields

Elasticsearch uses **mappings** to define how documents are indexed and searched. Understanding mappings helps you understand how search works:

### Field Types: Text vs Keyword

**Text Fields** are analyzed for full-text search:
- **Analysis:** Text is tokenized (split into words), lowercased, and stemmed
- **Examples:** `name`, `description`
- **Use case:** Keyword search, phrase matching, relevance ranking

When you search for "sentiment analysis," Elasticsearch matches documents containing "sentiment" or "analysis" anywhere in the text fields, ranked by relevance.

**Keyword Fields** are stored exactly as-is for exact matches:
- **No analysis:** Values are stored exactly as provided
- **Examples:** `db_identifier`, `license`, `platform`
- **Use case:** Filtering, aggregations, exact matches

When you filter by `license: "apache-2.0"`, Elasticsearch matches documents with exactly that license value.

**Multi-value Fields** store arrays:
- **Arrays:** Multiple values per field
- **Examples:** `ml_tasks`, `keywords`
- **Use case:** Multiple tags, categories, filtering by any value

When you filter by `ml_tasks: "text-classification"`, Elasticsearch matches documents where that value appears in the array.

### Document Schema

**Example schema:**
```python
class HFModelDocument(Document):
    """Elasticsearch document for HF models."""
    
    db_identifier = Keyword()      # Exact match
    name = Text(fields={"raw": Keyword()})  # Full-text + exact
    description = Text()            # Full-text search
    shared_by = Keyword()           # Exact match
    license = Keyword()              # Exact match
    ml_tasks = Keyword(multi=True)  # Multi-value, exact match
    keywords = Keyword(multi=True)  # Multi-value, exact match
    platform = Keyword()            # Exact match
```

**Field Mappings:**
- `name`: Text (searchable) + Keyword (exact match via `name.raw`)
- `description`: Text (full-text search)
- `ml_tasks`: Keyword array (filtering)
- `keywords`: Keyword array (filtering)

**Why `name.raw`?** The `name` field is analyzed for search, but `name.raw` stores the exact value for exact matches. This enables both "find models with 'bert' in the name" (text search) and "find the exact model named 'bert-base-uncased'" (keyword match).

---

## Index Configuration: Optimizing for Search

Elasticsearch indexes have configuration settings that affect performance and behavior:

### Index Settings

**Shards and Replicas:**
```python
class Index:
    name = "hf_models"
    settings = {
        "number_of_shards": 1,
        "number_of_replicas": 0
    }
```

**Shards** split the index across multiple nodes for scalability. For small datasets, one shard is sufficient. For large datasets, multiple shards enable parallel processing.

**Replicas** are copies of shards for redundancy and performance. Replicas enable read scaling (multiple nodes can serve search requests) and provide redundancy (if one node fails, replicas continue serving).

**Configuration:**
- `number_of_shards`: Number of primary shards (default: 1 for small datasets)
- `number_of_replicas`: Number of replica shards (default: 0 for development, 1+ for production)

### Environment Variables

**Connection settings:**
- `ES_HOST`: Elasticsearch host (default: `localhost`)
- `ES_PORT`: Elasticsearch port (default: `9200`)
- `ES_USERNAME`: Username (optional, for secured Elasticsearch)
- `ES_PASSWORD`: Password (optional, for secured Elasticsearch)

**Index settings:**
- `HF_MODELS_INDEX`: Index name (default: `hf_models`)

These environment variables allow you to configure Elasticsearch connection and index names without changing code.

---

## Usage Examples: Running the Loader

The Elasticsearch loader can be used in several ways:

### Via Dagster UI

**Steps:**
1. Open Dagster UI (http://localhost:3000)
2. Navigate to Assets tab
3. Find `hf_index_models_elasticsearch` asset (or similar for other sources)
4. Click "Materialize"
5. Watch progress in real-time

**Benefits:** Visual interface, real-time progress, easy to see logs and errors.

### Via Command Line

**Index models:**
```bash
dagster asset materialize -m etl.repository -a hf_index_models_elasticsearch
```

**Index with dependencies:**
```bash
# This automatically runs transformation first
dagster asset materialize -m etl.repository -a hf_index_models_elasticsearch+
```

The `+` notation means "include dependencies," so this will automatically run the transformation stage first if needed.

### Programmatic Usage

**Standalone (without Dagster):**
```python
from etl_loaders.hf_index_loader import index_hf_models

stats = index_hf_models(
    json_path="/data/normalized/hf/mlmodels.json"
)

print(f"Indexed {stats['models_indexed']} models")
print(f"Errors: {stats['errors']}")
```

This allows you to use the loader programmatically, useful for testing, automation, or integration with other systems.

---

## Search Examples: Querying the Index

Once data is indexed, you can search it using Elasticsearch queries. Here are practical examples:

### Full-Text Search

**Search by description:**
```json
{
  "query": {
    "match": {
      "description": "sentiment analysis"
    }
  }
}
```

This finds models with "sentiment" or "analysis" in the description, ranked by relevance. Elasticsearch analyzes the query text and matches it against analyzed document fields.

**Search by name:**
```json
{
  "query": {
    "match": {
      "name": "bert"
    }
  }
}
```

This finds models with "bert" in the name. The text field is analyzed, so this matches "BERT", "bert-base", "bert-large", etc.

### Filtering

**Filter by ML task:**
```json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "ml_tasks": "text-classification"
          }
        }
      ]
    }
  }
}
```

This finds models where `ml_tasks` contains exactly "text-classification". The `term` query is used for exact matches on keyword fields.

**Filter by license:**
```json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "license": "apache-2.0"
          }
        }
      ]
    }
  }
}
```

This finds models with exactly "apache-2.0" license. Filters are fast because they don't calculate relevance scores—they just match or don't match.

### Combined Search

**Search + Filter:**
```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "description": "transformer"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "ml_tasks": "fill-mask"
          }
        }
      ]
    }
  }
}
```

This combines full-text search (find "transformer" in description) with filtering (must have "fill-mask" task). The `must` clause requires the search to match, and the `filter` clause narrows results.

**Why combine?** Full-text search finds relevant documents, and filters narrow results to exactly what you want. This combination provides both discovery (search) and precision (filtering).

### Faceted Search

**Count by ML task:**
```json
{
  "aggs": {
    "ml_tasks": {
      "terms": {
        "field": "ml_tasks"
      }
    }
  }
}
```

This returns a count of models for each ML task. Aggregations analyze the index and return statistics, enabling faceted search interfaces where users can see "how many models for each task?"

**Count by license:**
```json
{
  "aggs": {
    "licenses": {
      "terms": {
        "field": "license"
      }
    }
  }
}
```

This returns a count of models for each license. Faceted search helps users understand the distribution of models and refine their searches.

---

## Performance Optimization: Making Indexing Efficient

Indexing large amounts of data requires optimization:

### Bulk Indexing

**Batch processing:** Index multiple documents at once using Elasticsearch's bulk API. This is much more efficient than indexing documents one at a time.

**Example:**
```python
# Index 100 models at a time
batch_size = 100
for i in range(0, len(models), batch_size):
    batch = models[i:i+batch_size]
    # Bulk index batch
    es.bulk(index="hf_models", body=batch)
```

**Benefits:** Faster indexing (less overhead per document), better throughput (more documents processed per second), and efficient resource usage (fewer API calls).

### Refresh Strategy

**Immediate refresh:** Documents are searchable immediately after indexing. This is useful for small datasets or when you need immediate searchability.

**Delayed refresh:** Documents are searchable after an explicit refresh. This is faster for large datasets because Elasticsearch doesn't need to refresh after every batch.

**Configuration:**
```python
doc.save(using=es_client, refresh=False)  # Delayed (faster)
doc.save(using=es_client, refresh=True)   # Immediate (slower)
```

**Trade-offs:** Immediate refresh provides better user experience (documents searchable right away) but slower indexing. Delayed refresh provides faster indexing but documents aren't searchable until refresh.

### Index Settings

**Optimize for search speed:**
- More shards (parallel processing)
- More replicas (read scaling)
- Larger heap size (more memory for caching)

**Optimize for indexing speed:**
- Fewer shards (less overhead)
- No replicas (faster writes)
- Larger batch size (fewer API calls)

**Optimize for storage:**
- Compression enabled
- Smaller field sizes
- Remove unused fields

**For MLentory:** We balance search speed and indexing speed. For production, we use multiple shards and replicas for search performance. For development, we use single shard and no replicas for simplicity.

---

## Troubleshooting: Common Issues and Solutions

When indexing data into Elasticsearch, you might encounter issues:

### Connection Errors

**Problem:** Cannot connect to Elasticsearch

**Solutions:**
- Check Elasticsearch is running (`docker ps` or `systemctl status elasticsearch`)
- Verify host and port (should be `localhost:9200` for local)
- Check credentials (if Elasticsearch is secured)
- Review firewall settings (if Elasticsearch is remote)

### Indexing Errors

**Problem:** Some documents fail to index

**Solutions:**
- Check document structure (ensure it matches the mapping)
- Verify field mappings (ensure fields are correctly typed)
- Review error logs (Elasticsearch provides detailed error messages)
- Handle missing fields gracefully (use default values or skip documents)

**Common errors:**
- **Mapping errors:** Field type doesn't match (e.g., trying to index text as keyword)
- **Validation errors:** Document doesn't match mapping constraints
- **Size errors:** Document too large (Elasticsearch has size limits)

### Performance Issues

**Problem:** Indexing is slow

**Solutions:**
- Use bulk indexing (index multiple documents at once)
- Increase batch size (process more documents per batch)
- Disable refresh during indexing (refresh after all documents are indexed)
- Optimize index settings (shards, replicas, heap size)

**Performance tips:**
- Index in batches of 100-1000 documents
- Use delayed refresh for large datasets
- Monitor Elasticsearch metrics (CPU, memory, disk I/O)
- Scale horizontally (add more Elasticsearch nodes)

---

## Key Takeaways

The Elasticsearch loader indexes FAIR4ML models as searchable documents, enabling fast full-text search, filtering, and faceted search. This process involves converting FAIR4ML JSON to Elasticsearch documents, mapping fields to appropriate types (Text for search, Keyword for filtering), and indexing documents in batches for efficiency.

Understanding how the Elasticsearch loader works helps you appreciate how MLentory enables discovery through search, and how to optimize indexing and querying for performance.

---

## Next Steps

- See [Neo4j Loader](neo4j.md) - How we store data in the knowledge graph
- Check [RDF Exporter](rdf.md) - Semantic web export details
- Explore [Elasticsearch Queries Examples](../examples/elasticsearch-queries.md) - Practical query examples
- Review [Architecture Overview](../architecture/overview.md) - How Elasticsearch fits into the system

---

## Resources

- **Elasticsearch Documentation:** [https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html](https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html) - Comprehensive Elasticsearch guide
- **Elasticsearch DSL:** [https://elasticsearch-dsl.readthedocs.io/](https://elasticsearch-dsl.readthedocs.io/) - Python DSL for Elasticsearch
- **Query DSL:** [https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl.html) - Complete query reference
