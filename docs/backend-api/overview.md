# Backend API Overview

The MLentory Backend API is a FastAPI-based REST service that provides programmatic access to the MLentory knowledge graph. It enables search, discovery, and exploration of ML models, datasets, papers, and their relationships.

---

## 🎯 Purpose

The Backend API serves as the query interface for data stored by the ETL pipeline in Elasticsearch and Neo4j. It provides:

- **🔍 Search & Discovery:** Query models with full-text search, filters, and faceted navigation
- **🌐 Graph Exploration:** Traverse relationships between models, datasets, papers, and licenses
- **📊 Metadata Retrieval:** Access detailed model information with related entities
- **📈 Statistics:** Get platform-wide statistics and aggregations

---

## 🏗️ System Context

The MLentory API is the query interface for the MLentory knowledge graph. It sits on top of two data stores populated by the ETL pipeline:

```
┌─────────────────────────────────────────────────────────────┐
│                      MLentory System                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────┐        ┌──────────────┐                    │
│  │   Sources   │        │     ETL      │                     │
│  │             │───────>│   Pipeline   │                     │
│  │ • HF        │        │  (Dagster)   │                     │
│  │ • OpenML    │        └──────┬───────┘                     │
│  │ • Papers    │               │                             │
│  └─────────────┘               │                             │
│                                 │                             │
│                    ┌────────────┴────────────┐               │
│                    │                         │               │
│                    ▼                         ▼               │
│            ┌──────────────┐        ┌──────────────┐         │
│            │Elasticsearch │        │    Neo4j     │         │
│            │  (Indexed)   │        │   (Graph)    │         │
│            └──────┬───────┘        └──────┬───────┘         │
│                   │                       │                  │
│                   └───────────┬───────────┘                  │
│                               │                              │
│                               ▼                              │
│                      ┌─────────────────┐                     │
│                      │  MLentory API   │                     │
│                      │   (FastAPI)     │                     │
│                      └────────┬────────┘                     │
│                               │                              │
└───────────────────────────────┼──────────────────────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   Clients    │
                         │              │
                         │ • Web Apps   │
                         │ • CLI Tools  │
                         │ • Notebooks  │
                         └──────────────┘
```

---

## ✨ Key Features

### Search Capabilities

- **Full-text Search:** Search across model names, descriptions, and keywords
- **Faceted Navigation:** Dynamic facets with counts and filtering
- **Advanced Filtering:** Filter by license, task, platform, and more
- **Pagination:** Efficient pagination for large result sets

### Graph Exploration

- **Relationship Traversal:** Explore connections between entities
- **Configurable Depth:** Control how deep to traverse the graph
- **Batch Operations:** Fetch multiple entities efficiently
- **Entity Properties:** Retrieve specific properties for entities

### Data Access

- **FAIR4ML Compliance:** All responses follow FAIR4ML schema
- **Related Entities:** Include related datasets, papers, licenses on demand
- **Statistics:** Platform-wide aggregations and counts
- **Health Monitoring:** Health check endpoints for monitoring

---

## 🚀 Quick Start

### Using the API

The API is available at `http://localhost:8000` (or your configured host/port).

**Interactive Documentation:**
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

**Example Request:**
```bash
# List models
curl http://localhost:8000/api/v1/models?page=1&page_size=10

# Search for models
curl "http://localhost:8000/api/v1/models?search=bert&page=1&page_size=10"
```

For setup instructions, see the [Quick Start Guide](../getting-started/quickstart.md). For usage examples, see the [API Usage Guide](usage/quickstart.md).

---

## 📚 Documentation Structure

- **[Architecture](architecture.md)** - System design and component overview
- **[Components](components.md)** - Detailed component descriptions
- **[Data Flow](data-flow.md)** - How requests flow through the system
- **[Endpoints](endpoints/models.md)** - Complete API endpoint reference
- **[Usage](usage/quickstart.md)** - Quick start and examples
- **[Reference](reference/schemas.md)** - Response schemas and error handling

---

## 🔑 Design Principles

1. **Reuse ETL Components:** All database configurations and helper utilities are imported from `etl_loaders/`
2. **FAIR4ML Compliance:** Response schemas extend the existing FAIR4ML `MLModel` schema
3. **Separation of Concerns:** Clear separation between routing, business logic, and data access
4. **Type Safety:** Full Pydantic validation for all request/response models

---

## 🛠️ Technology Stack

- **FastAPI:** Modern, fast web framework for building APIs
- **Pydantic:** Data validation using Python type annotations
- **Elasticsearch:** Search and indexing engine
- **Neo4j:** Graph database for relationship storage
- **OpenAPI:** Automatic API documentation generation

---

## 📖 Next Steps

1. **[Quick Start Guide](../getting-started/quickstart.md)** → Set up the API
2. **[API Architecture](architecture.md)** → Understand the system design
3. **[API Endpoints](endpoints/models.md)** → Explore available endpoints
4. **[API Usage](usage/quickstart.md)** → Start using the API
5. **[API Examples](usage/examples.md)** → See code examples

