# Elasticsearch Basics

### 🎯 What is Elasticsearch?

**Elasticsearch** is a search and analytics engine built on Apache Lucene. It's designed to store, search, and analyze large volumes of data quickly. Think of it as a super-powered search engine for your data.

### 🤔 Why Elasticsearch?

Traditional databases are great for storing and retrieving data, but they struggle with:

- Fast full-text search across large datasets
- Complex search queries with filters
- Real-time search results
- Analyzing and aggregating data

**Elasticsearch excels at:**

- Full-text search (finding documents by content)
- Filtering and faceted search
- Real-time search and analytics
- Handling large volumes of data

### 🧩 Core Concepts

#### 📄 1. Documents

**Documents** are the basic unit of information in Elasticsearch. Think of them as JSON objects.

**Example Document:**

```json
{
  "id": "model-123",
  "name": "BERT Base",
  "description": "A transformer model for NLP tasks",
  "task": "text-classification",
  "downloads": 5000000
}
```

**Key Points:**

- Documents are JSON objects
- Each document has fields (like name, description)
- Documents are stored in indices

#### 📚 2. Indices

An **index** is a collection of documents. Think of it as a database in traditional terms.

**Example:**

- Index: `models`
- Contains: All model documents
- Purpose: Organize related documents

#### 🗺️ 3. Fields and Mapping

**Fields** are the properties of documents (like name, description).

**Mapping** defines the structure of documents in an index—what fields exist and their types.

**Analogy:**

- Index = Database
- Mapping = Table
- Document = Row
- Field = Column

**Field Types:**
- `text`: Full-text searchable (like descriptions)
- `keyword`: Exact match (like IDs, tags)
- `number`: Numeric values (like downloads)
- `date`: Date/time values
- `boolean`: True/false values

**Example Mapping:**
```json
{
  "mappings": {
    "properties": {
      "name": { "type": "text" },
      "id": { "type": "keyword" },
      "downloads": { "type": "integer" },
      "created_date": { "type": "date" }
    }
  }
}
```

#### 🔍 4. Queries

**Queries** are how you search for documents. Elasticsearch supports many query types.

**Basic Query Types:**
- **Match**: Full-text search
- **Term**: Exact match
- **Range**: Numeric/date ranges
- **Bool**: Combine multiple queries
- **Filter**: Non-scoring queries (faster)

### ⚙️ Basic Operations

#### ➕ 1. Indexing (Adding Documents)

**Add a document:**
```bash
PUT /models/_doc/1
{
  "name": "BERT Base",
  "description": "A transformer model",
  "task": "text-classification"
}
```

This creates/updates a document with ID `1` in the `models` index.

#### 🔍 2. Searching

**Simple search:**
```bash
GET /models/_search
{
  "query": {
    "match": {
      "name": "BERT"
    }
  }
}
```

This searches for documents where the `name` field contains "BERT".

**Search with filters:**
```bash
GET /models/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "BERT" } }
      ],
      "filter": [
        { "range": { "downloads": { "gte": 1000000 } } }
      ]
    }
  }
}
```

This finds BERT models with at least 1 million downloads.

#### 📊 3. Aggregations

**Aggregations** analyze and summarize data.

**Count by task:**
```bash
GET /models/_search
{
  "size": 0,
  "aggs": {
    "tasks": {
      "terms": {
        "field": "task"
      }
    }
  }
}
```

This groups models by task and counts them.

### 🌐 Elasticsearch REST API

Elasticsearch provides a REST API for all operations. You interact with it using HTTP requests.

#### 🔌 Common Endpoints

**Check cluster health:**
```bash
GET /_cluster/health
```

**List all indices:**
```bash
GET /_cat/indices
```

**Get index info:**
```bash
GET /models
```

**Search:**
```bash
GET /models/_search
{
  "query": { ... }
}
```

**Count documents:**
```bash
GET /models/_count
```

#### 💻 Using cURL or Other HTTP Clients

You can use **cURL**, **Postman**, **HTTPie**, **wget**, or any HTTP client to interact with Elasticsearch. All examples below use cURL, but you can adapt them to your preferred HTTP client.

**Note:** Replace `http://localhost:9201` with your Elasticsearch URL if different.

##### 📋 List All Indices

```bash
# List all indices with basic info
curl -X GET "http://localhost:9201/_cat/indices?v"

# List indices in JSON format
curl -X GET "http://localhost:9201/_cat/indices?format=json&pretty"

# List only index names
curl -X GET "http://localhost:9201/_cat/indices?h=index"
```

**Output example:**
```
health status index     uuid                   pri rep docs.count docs.deleted store.size pri.store.size
green  open   hf_models abc123def456           1   0       1500            0      2.5mb          2.5mb
```

##### 🗺️ Check Index Mapping

```bash
# Get mapping for a specific index
curl -X GET "http://localhost:9201/hf_models/_mapping?pretty"

# Get mapping for all indices
curl -X GET "http://localhost:9201/_mapping?pretty"

# Get only field mappings (simplified)
curl -X GET "http://localhost:9201/hf_models/_mapping/field/name,description?pretty"
```

**Output example:**
```json
{
  "hf_models": {
    "mappings": {
      "properties": {
        "name": {
          "type": "text",
          "fields": {
            "raw": {
              "type": "keyword"
            }
          }
        },
        "description": {
          "type": "text"
        }
      }
    }
  }
}
```

##### 📊 Get Index Statistics

```bash
# Get detailed index information
curl -X GET "http://localhost:9201/hf_models?pretty"

# Get index statistics (document count, size, etc.)
curl -X GET "http://localhost:9201/hf_models/_stats?pretty"

# Get index settings
curl -X GET "http://localhost:9201/hf_models/_settings?pretty"
```

##### 🔍 Search Operations

```bash
# Simple search
curl -X GET "http://localhost:9201/hf_models/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": { "name": "BERT" }
    }
  }'

# Count documents
curl -X GET "http://localhost:9201/hf_models/_count?pretty"

# Count documents matching a query
curl -X GET "http://localhost:9201/hf_models/_count?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": { "name": "BERT" }
    }
  }'
```

##### 🏥 Cluster and Health Checks

```bash
# Check cluster health
curl -X GET "http://localhost:9201/_cluster/health?pretty"

# Get cluster information
curl -X GET "http://localhost:9201/_cluster/stats?pretty"

# List all nodes
curl -X GET "http://localhost:9201/_cat/nodes?v"
```

##### 📝 Document Operations

```bash
# Get a specific document by ID
curl -X GET "http://localhost:9201/hf_models/_doc/123?pretty"

# Check if a document exists
curl -X HEAD "http://localhost:9201/hf_models/_doc/123"

# Get multiple documents by IDs
curl -X GET "http://localhost:9201/hf_models/_mget?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "ids": ["123", "456", "789"]
  }'
```

##### 🔧 Index Management

```bash
# Delete an index (use with caution!)
curl -X DELETE "http://localhost:9201/hf_models"

# Create an index with mapping
curl -X PUT "http://localhost:9201/my_index?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "mappings": {
      "properties": {
        "name": { "type": "text" },
        "id": { "type": "keyword" }
      }
    }
  }'

# Refresh an index (make recent changes searchable)
curl -X POST "http://localhost:9201/hf_models/_refresh"
```

##### 🔍 Advanced Search Examples

```bash
# Search with filters
curl -X GET "http://localhost:9201/hf_models/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": [
          { "match": { "name": "BERT" } }
        ],
        "filter": [
          { "range": { "downloads": { "gte": 1000000 } } }
        ]
      }
    }
  }'

# Search with aggregations
curl -X GET "http://localhost:9201/hf_models/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "size": 0,
    "aggs": {
      "tasks": {
        "terms": { "field": "ml_tasks" }
      }
    }
  }'
```

### 🔍 How Elasticsearch Search Works

Understanding how Elasticsearch performs searches helps you write better queries and understand results. Elasticsearch uses a sophisticated process involving indexing, analysis, and scoring.

#### 📚 The Search Process

**1. Indexing Phase (Before Search)**
- Documents are analyzed (tokenized, lowercased, stemmed)
- Terms are stored in an inverted index
- Each term points to documents containing it

**2. Query Phase (During Search)**
- Query is analyzed using the same analyzer
- Elasticsearch looks up terms in the inverted index
- Finds matching documents
- Calculates relevance scores
- Returns ranked results

**3. Scoring**
- **TF-IDF** (Term Frequency-Inverse Document Frequency): More common terms in a document increase score, but very common terms across all documents decrease score
- **Field length**: Shorter fields with matches score higher
- **Term proximity**: Terms appearing close together score higher
- **Boost factors**: Certain fields or terms can be boosted

**Example:**
```
Document: "BERT is a transformer model"
Query: "transformer model"

Process:
1. Query analyzed → ["transformer", "model"]
2. Inverted index lookup → finds document
3. Score calculated:
   - Both terms present: +2.0
   - Terms close together: +0.5
   - Field length: +0.3
   Total score: 2.8
```

### ⭐ Key Features

#### 🔎 1. Full-Text Search (Text-Based Search)

**Text-based search** is Elasticsearch's primary search method. It analyzes text content to find relevant documents based on meaning, not just exact matches.

**How It Works:**
1. **Analysis**: Text is broken down into tokens (words)
2. **Normalization**: Tokens are lowercased, stemmed (e.g., "running" → "run")
3. **Matching**: Query terms are matched against analyzed tokens
4. **Ranking**: Results are scored by relevance

**Example:**
```bash
# Search query
curl -X GET "http://localhost:9201/hf_models/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": {
        "description": "transformer model for NLP"
      }
    }
  }'
```

**What happens:**
- Query "transformer model for NLP" is analyzed → ["transformer", "model", "nlp"]
- Elasticsearch finds documents containing these terms
- Documents with more matching terms score higher
- Documents with terms appearing close together score higher
- Results are ranked by relevance score

**Key Characteristics:**
- ✅ Handles typos and variations
- ✅ Finds partial matches
- ✅ Ranks by relevance
- ✅ Supports phrase matching
- ✅ Works with analyzed text fields

#### 🧮 2. Vector-Based Search

**Vector-based search** (also called semantic search) uses dense vector representations to find documents based on meaning, not just keywords. This enables finding documents that are semantically similar even if they don't share exact words.

**How It Works:**
1. **Embedding Generation**: Text is converted to dense vectors (arrays of numbers) using machine learning models
2. **Vector Storage**: Vectors are stored in special `dense_vector` fields
3. **Similarity Search**: Query is also converted to a vector, then compared using distance metrics (cosine similarity, dot product, etc.)
4. **Ranking**: Documents are ranked by vector similarity

**Example:**
```json
{
  "mappings": {
    "properties": {
      "description": { "type": "text" },
      "description_vector": {
        "type": "dense_vector",
        "dims": 768
      }
    }
  }
}
```

**Vector Search Query:**
```bash
curl -X GET "http://localhost:9201/hf_models/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "script_score": {
        "query": { "match_all": {} },
        "script": {
          "source": "cosineSimilarity(params.query_vector, 'description_vector') + 1.0",
          "params": {
            "query_vector": [0.1, 0.2, 0.3, ...]  # 768-dimensional vector
          }
        }
      }
    }
  }'
```

**Key Characteristics:**
- ✅ Finds semantically similar content
- ✅ Works even without exact keyword matches
- ✅ Requires pre-computed embeddings
- ✅ More computationally expensive
- ✅ Better for "find similar" queries

**When to Use:**
- **Text-based search**: Keyword queries, exact matches, filtering
- **Vector-based search**: Semantic similarity, "find similar models", recommendation systems

#### 🔗 3. Multi-Index Search

Elasticsearch can search across **multiple indices** simultaneously, combining results from different sources. This is essential when you have data split across multiple indices (e.g., different sources, time periods, or categories).

**How It Works:**
1. **Index Selection**: Specify multiple indices in the search request
2. **Parallel Search**: Elasticsearch searches each index in parallel
3. **Result Merging**: Results from all indices are merged
4. **Unified Ranking**: Results are re-scored and ranked together

**Example:**
```bash
# Search across multiple indices
curl -X GET "http://localhost:9201/hf_models,openml_models,ai4life_models/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": { "name": "BERT" }
    }
  }'

# Search all indices with wildcard
curl -X GET "http://localhost:9201/*_models/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": { "name": "BERT" }
    }
  }'

# Search all indices
curl -X GET "http://localhost:9201/_all/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "match": { "name": "BERT" }
    }
  }'
```

**Index Patterns:**
- `index1,index2,index3` - Specific indices
- `*_models` - All indices ending with "_models"
- `hf_*` - All indices starting with "hf_"
- `_all` - All indices (use with caution!)

**Result Structure:**
```json
{
  "took": 5,
  "timed_out": false,
  "_shards": {
    "total": 3,
    "successful": 3,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 150,
      "relation": "eq"
    },
    "hits": [
      {
        "_index": "hf_models",
        "_id": "123",
        "_score": 2.5,
        "_source": { ... }
      },
      {
        "_index": "openml_models",
        "_id": "456",
        "_score": 2.3,
        "_source": { ... }
      }
    ]
  }
}
```

**Key Characteristics:**
- ✅ Search across multiple data sources
- ✅ Unified results from different indices
- ✅ Parallel execution for performance
- ✅ Consistent ranking across indices
- ✅ Useful for federated search scenarios

**Use Cases:**
- Searching models from multiple platforms (HuggingFace, OpenML, AI4Life)
- Time-based indices (searching across monthly/yearly indices)
- Category-based indices (searching across different model categories)

#### 🔽 2. Filtering

Filters narrow down results without affecting relevance scores.

**Common Filters:**
- Range filters (downloads > 1000)
- Term filters (exact match)
- Exists filters (field must exist)
- Bool filters (combine multiple)

#### 🎯 3. Faceted Search

Facets provide counts for different categories, enabling filtering.

**Example:**
- Show count of models by task
- Show count of models by license
- Users can filter by clicking facets

#### ⚡ 4. Real-Time

Elasticsearch is near real-time—documents are searchable within seconds of being indexed.

### 💼 Common Use Cases

#### 🔍 1. Search Interface

**Use Case:** User searches for "BERT models for classification"
```bash
GET /models/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "name": "BERT" } },
        { "match": { "description": "classification" } }
      ]
    }
  }
}
```

#### 🎛️ 2. Filtered Browsing

**Use Case:** Show all transformer models with >1M downloads
```bash
GET /models/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "category": "transformer" } }
      ],
      "filter": [
        { "range": { "downloads": { "gte": 1000000 } } }
      ]
    }
  }
}
```

#### 📈 3. Analytics

**Use Case:** Count models by task and platform
```bash
GET /models/_search
{
  "size": 0,
  "aggs": {
    "by_task": {
      "terms": { "field": "task" }
    },
    "by_platform": {
      "terms": { "field": "platform" }
    }
  }
}
```

### ⚖️ Elasticsearch vs Traditional Databases

| Feature | Traditional DB | Elasticsearch |
|---------|----------------|---------------|
| Full-text search | Limited | Excellent |
| Complex queries | Good | Excellent |
| Real-time search | Good | Excellent |
| Analytics | Good | Excellent |
| Transactions | Excellent | Limited |
| Structured queries | Excellent | Good |

**When to use Elasticsearch:**
- You need fast full-text search
- You have large volumes of data
- You need real-time search
- You need analytics and aggregations

**When not to use:**
- You need ACID transactions
- Data is highly structured with simple queries
- You need complex joins

### ✅ Key Takeaways

- **Elasticsearch** is a search and analytics engine
- **Documents** are JSON objects stored in indices
- **Indices** organize related documents
- **Queries** search and filter documents
- **Aggregations** analyze and summarize data
- Elasticsearch excels at full-text search and real-time analytics

### 📋 Quick Reference

| Concept | Description |
|---------|-------------|
| Document | A JSON object (like a row in a database) |
| Index | A collection of documents (like a database) |
| Field | A property of a document (like a column) |
| Mapping | The schema/structure of documents |
| Query | A search request |
| Aggregation | Analysis/summarization of data |

---

**Previous:** [Neo4j Introduction](neo4j.md) | [Back to Tutorial Overview](../concepts-tutorial.md)

