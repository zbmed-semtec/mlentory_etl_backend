# Loaders Overview: Storing Data for Different Use Cases

Loaders are the final stage of the MLentory ETL pipeline, responsible for storing normalized FAIR4ML data in target systems optimized for different query patterns. Understanding loaders helps you appreciate why we use multiple storage systems, how data is organized for different use cases, and how the system supports both relationship queries and full-text search.

---

## What Are Loaders and Why Do We Need Multiple Systems?

After extraction and transformation, we have clean, standardized FAIR4ML data. But where should this data be stored? The answer might seem obvious—just put it in a database. But the reality is more nuanced because different use cases require different data structures and query patterns.

**Loaders** take normalized FAIR4ML data and store it in systems optimized for specific use cases. We use three different systems because each excels at different types of queries:

**Neo4j** is a graph database that excels at relationship queries. Want to find all models that use a specific dataset? Or trace a model's lineage through fine-tuning? Neo4j makes these queries fast and intuitive.

**Elasticsearch** is a search engine that excels at full-text search. Want to search for "models for sentiment analysis" or filter by license? Elasticsearch provides fast, flexible search capabilities.

**RDF Export** creates semantic web files for interoperability. Want to integrate with other FAIR data systems or enable SPARQL queries? RDF files provide that capability.

![Multiple Storage Systems](images/multiple-storage-systems.png)
*Figure 1: Different storage systems optimize for different query patterns, enabling both relationship exploration and full-text search.*

### Why Not Just One System?

You might wonder why we don't just use one database for everything. The answer is that different query patterns require different data structures, and optimizing for one pattern often hurts performance for another.

**Graph databases** (like Neo4j) store data as nodes and relationships. This structure is perfect for relationship queries but less efficient for full-text search. Searching for "sentiment analysis" in a graph database requires scanning all nodes, which is slow.

**Search engines** (like Elasticsearch) index text for fast search. This is perfect for keyword searches but less efficient for relationship queries. Finding "all models that use this dataset" in a search engine requires complex queries that don't leverage the relationship structure.

**RDF files** provide semantic web compatibility but aren't optimized for either pattern. They're valuable for interoperability and long-term preservation but not for day-to-day queries.

By using multiple systems, we get the best of all worlds: fast relationship queries, fast full-text search, and semantic web compatibility.

---

## The Loading Process: From Normalized Data to Storage

The loading process takes normalized FAIR4ML JSON files and stores them in target systems. This process involves format conversion, data organization, and conflict resolution.

### Step 1: Reading Normalized Data

Loading begins by reading the normalized FAIR4ML JSON files created during transformation. These files contain validated, enriched data in a consistent format.

**File Loading** reads JSON files from the transformation stage's output directory. Files are organized by source and run, making it easy to find the right data.

**Parsing** converts JSON into Python objects that can be processed. This parsing handles the FAIR4ML structure, including nested objects and arrays.

**Validation** ensures data is still valid (though it should be, since transformation already validated it). This provides a safety check before loading.

### Step 2: Transforming to Target Format

Each storage system requires data in a specific format. Loaders convert FAIR4ML JSON into these formats:

**Neo4j** requires RDF triples. Each FAIR4ML property becomes one or more RDF triples (subject-predicate-object). Models become nodes, properties become node attributes, and relationships become edges.

**Elasticsearch** requires searchable documents. FAIR4ML models become Elasticsearch documents with fields optimized for search. Text fields are analyzed for full-text search, keyword fields are stored for exact matching.

**RDF Export** requires Turtle format. FAIR4ML data is converted to RDF/Turtle syntax, creating human-readable semantic web files.

### Step 3: Loading to Target Systems

Once data is in the target format, it's loaded into the storage systems:

**Neo4j** creates graph nodes and relationships. Models become Model nodes, datasets become Dataset nodes, and relationships (like USES_DATASET) connect them.

**Elasticsearch** indexes documents. Each model becomes a searchable document in an index, with fields configured for appropriate search behavior.

**RDF Export** writes Turtle files. RDF triples are written to `.ttl` files in a human-readable format.

### Step 4: Handling Conflicts

When loading data, conflicts can arise. A model might already exist (from a previous load), or there might be duplicates. Loaders handle these conflicts gracefully:

**Upsert Logic** (update if exists, insert if new) ensures that existing records are updated rather than duplicated. This is crucial when re-running loads with updated data.

**Deduplication** removes duplicate records that might arise from multiple sources or extraction runs.

**Data Consistency** ensures referential integrity. If a model references a dataset, that dataset must exist. Loaders ensure these relationships are valid.

---

## Target Systems: Optimized for Different Queries

Each storage system is designed for specific query patterns. Understanding these patterns helps you understand why we use multiple systems.

### Neo4j: The Relationship Expert

**Neo4j** is a graph database that stores data as nodes (entities) and relationships (connections). This structure is perfect for queries that explore relationships.

**What makes Neo4j special:** Graph databases are designed from the ground up for relationship queries. Unlike relational databases that require JOINs (which get slow with many relationships), graph databases traverse relationships directly, making relationship queries fast even with complex graphs.

**What's stored:** Models become Model nodes, datasets become Dataset nodes, papers become Paper nodes. Relationships like USES_DATASET, CITES_PAPER, and BASED_ON connect these nodes, creating a knowledge graph.

**Use cases:** Finding related models (models that use the same datasets), tracing model lineage (following fine-tuning relationships), building recommendation systems (finding similar models based on relationships), and graph-based similarity (models with similar relationship patterns).

**Example query:**
```cypher
MATCH (m:Model)-[:USES_DATASET]->(d:Dataset {name: "SQuAD"})
RETURN m.name
```

This query finds all models that use the SQuAD dataset. In a relational database, this would require JOINs across multiple tables. In Neo4j, it's a simple graph traversal.

### Elasticsearch: The Search Expert

**Elasticsearch** is a search engine that indexes text for fast full-text search. This makes it perfect for keyword searches, filtering, and faceted search.

**What makes Elasticsearch special:** Search engines are designed for text search. They analyze text, build indexes, and provide fast search capabilities that would be slow in traditional databases.

**What's stored:** Models become searchable documents with fields like name, description, mlTask, keywords, etc. These fields are configured for appropriate search behavior—some for full-text search, others for exact matching.

**Use cases:** Keyword search (finding models by description text), filtering (models with specific tasks or licenses), faceted search (counting results by category), and autocomplete (suggesting search terms as users type).

**Example query:**
```json
{
  "query": {
    "match": {
      "description": "sentiment analysis"
    }
  }
}
```

This query finds models whose descriptions contain "sentiment analysis". Elasticsearch analyzes the text, finds relevant documents, and ranks them by relevance.

### RDF Export: The Interoperability Expert

**RDF Export** creates semantic web files that enable integration with other FAIR data systems and support SPARQL queries.

**What makes RDF special:** RDF is a standard format for semantic web data. It enables integration with other systems that understand RDF, supports SPARQL queries, and provides long-term preservation in a standard format.

**What's stored:** RDF/Turtle files containing FAIR4ML data in semantic web format. These files can be imported into other systems, queried with SPARQL, or used for data exchange.

**Use cases:** Integration with other FAIR systems (Zenodo, DataCite, etc.), semantic web tools (SPARQL endpoints, RDF validators), FAIR data compliance (meeting FAIR principles), and long-term preservation (standard format that won't become obsolete).

**Example:**
```turtle
@prefix fair4ml: <https://w3id.org/fair4ml#> .
@prefix schema: <https://schema.org/> .

<https://huggingface.co/bert-base-uncased>
  a fair4ml:MLModel ;
  schema:name "bert-base-uncased" ;
  fair4ml:mlTask "fill-mask" .
```

This Turtle format is human-readable and machine-processable, enabling both human understanding and automated integration.

---

## Upsert Logic: Handling Updates Gracefully

When loading data, you often need to update existing records rather than create duplicates. **Upsert** (update if exists, insert if new) logic handles this gracefully.

### Why Upsert Matters

**Models change over time.** A model's description might be updated, new tags might be added, or download counts might increase. When you re-run the pipeline, you want to update the existing record, not create a duplicate.

**Avoiding duplicates** is crucial for data quality. Duplicate models would confuse search results, break relationship queries, and waste storage space.

**Data consistency** requires that updates are atomic—either the entire update succeeds or it fails, preventing partial updates that leave data in an inconsistent state.

### How Upsert Works in Each System

**Neo4j** uses the MERGE operation, which creates a node if it doesn't exist or updates it if it does. MERGE is based on a unique identifier (like the model's URL), ensuring that each model appears only once.

**Elasticsearch** uses document IDs for upsert. When indexing a document, Elasticsearch checks if a document with that ID already exists. If it does, it updates it. If not, it creates a new document.

**RDF Export** regenerates files each time, so upsert isn't needed. Files are replaced entirely, ensuring they always reflect the current state of the data.

---

## Data Flow: Understanding the Pipeline

The loading process follows a clear flow from normalized data to storage systems:

### Loading Pipeline

```
Normalized FAIR4ML JSON
    ↓
    ├─→ Neo4j Loader
    │   ├─→ Convert to RDF triples
    │   ├─→ Create graph nodes
    │   ├─→ Create relationships
    │   └─→ Export to Turtle (optional)
    │
    ├─→ Elasticsearch Loader
    │   ├─→ Build searchable documents
    │   ├─→ Index documents
    │   └─→ Update mappings
    │
    └─→ RDF Exporter
        └─→ Generate Turtle files
```

This parallel loading approach means that data is loaded into all systems simultaneously, maximizing efficiency.

### Output Structure

RDF exports are organized in run folders:

```
/data/rdf/<source>/
└── <timestamp>_<uuid>/
    ├── models.ttl
    ├── datasets.ttl
    └── papers.ttl
```

This structure matches the extraction and transformation stages, making it easy to trace data through the pipeline.

---

## Error Handling: Maximizing Success

Loading includes comprehensive error handling to ensure maximum success:

### Validation Errors

If data fails validation during loading (which shouldn't happen if transformation worked correctly), errors are handled gracefully:

**Error Logging** captures detailed information about what went wrong.

**Error Files** save loading errors to separate files, organized by entity type.

**Partial Success** means that if some models fail to load, others continue. This ensures you get as much data loaded as possible.

### Connection Errors

When connecting to storage systems, network issues can occur:

**Retry Logic** implements exponential backoff, giving systems time to recover before retrying.

**Error Logging** captures connection failures with context about what was being attempted.

**Graceful Degradation** means that if one system is unavailable, others continue. If Neo4j is down, Elasticsearch loading can still succeed.

### Data Consistency

Maintaining data consistency is crucial:

**Transactions** ensure atomicity—either all changes in a transaction succeed or all fail, preventing partial updates.

**Rollback** on failure ensures that if loading fails partway through, changes are rolled back, leaving the system in a consistent state.

**Referential Integrity** ensures that if a model references a dataset, that dataset exists. Loaders validate these relationships before creating them.

---

## Performance Considerations: Loading at Scale

Loading large amounts of data requires careful performance optimization:

### Batch Processing

**Neo4j** benefits from batch RDF triple insertion. Instead of inserting triples one at a time, batches are inserted together, reducing overhead.

**Elasticsearch** uses bulk indexing, inserting multiple documents at once. This is much faster than individual document indexing.

**RDF Export** streams large files to avoid memory issues, writing incrementally rather than building entire files in memory.

### Parallel Processing

**Multi-threading** allows loading multiple models simultaneously. This is especially valuable when loading to multiple systems in parallel.

**Connection Pooling** reuses database connections, avoiding the overhead of creating new connections for each operation.

**Load Balancing** distributes work across multiple threads or processes, maximizing resource utilization.

### Optimization Tips

**Batch Size** should be tuned based on system resources. Larger batches are more efficient but require more memory.

**Parallel Processing** should match system capabilities. Too many threads can overwhelm systems, too few waste resources.

**Connection Pooling** reduces connection overhead, especially important for database systems.

**Indexing Strategy** balances speed and consistency. Immediate indexing is slower but ensures data is immediately searchable. Delayed indexing is faster but requires refresh.

---

## Key Takeaways

Loaders are the final stage that makes data usable. They store data in systems optimized for different query patterns, enabling both relationship exploration and full-text search. They handle updates gracefully through upsert logic, maximize success through comprehensive error handling, and optimize performance through batching and parallelization.

Understanding loaders helps you appreciate why we use multiple storage systems, how data is organized for different use cases, and how the system supports both researchers exploring relationships and users searching for models.

---

## Next Steps

- Learn about [Neo4j Loader](neo4j.md) - How we build the knowledge graph
- See [Elasticsearch Loader](elasticsearch.md) - How we enable fast search
- Check [RDF Exporter](rdf.md) - How we enable semantic web integration
- Explore [Architecture Overview](../architecture/overview.md) - How loaders fit into the system
