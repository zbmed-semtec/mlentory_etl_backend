# MLentory Documentation

Welcome to the comprehensive documentation for **MLentory**, a FAIR Digital Object registry for discovering machine learning models. This documentation covers both the **ETL Pipeline** (data processing engine) and the **Backend API** (REST API service).

---

## 🎯 Overview

### 🤔 What is MLentory?

[MLentory](https://mlentory.zbmed.de/) is a comprehensive **FAIR Digital Object (FDO) registry** that provides:

**🔍 Unified Search** across multiple ML model repositories

**📊 Harmonized Metadata** using the FAIR4ML schema

**🤖 Recommendation Service** to find similar models

**🌐 FAIR Digital Objects** with rich, standardized metadata

**🔗 Relationship Discovery** between models, datasets, and papers

**📡 REST API** for programmatic access

MLentory addresses a critical challenge in machine learning research: **finding and comparing ML models** scattered across multiple platforms.

### 🧩 MLentory Components

The MLentory system consists of two main components documented here:

#### 1. 🔄 ETL Pipeline

The **ETL (Extract, Transform, Load) pipeline** is the data processing engine that powers MLentory. It orchestrates a three-stage process that transforms raw model metadata into a harmonized, searchable knowledge base:

1. **Extract:** Pull raw metadata from source repositories (HuggingFace, OpenML, AI4Life, etc.)
2. **Transform:** Normalize and harmonize data into the standardized FAIR4ML schema
3. **Load:** Store processed data in Neo4j (graph relationships), Elasticsearch (search index), and export as RDF files

The processed data powers MLentory's search interface, recommendation system, and API.

#### 2. 🌐 Backend API

The **Backend API** is a FastAPI-based REST service that provides programmatic access to the MLentory knowledge graph. It enables:

- **Search & Discovery:** Query models with full-text search, filters, and faceted navigation
- **Graph Exploration:** Traverse relationships between models, datasets, papers, and licenses
- **Metadata Retrieval:** Access detailed model information with related entities
- **Statistics:** Get platform-wide statistics and aggregations

The API serves as the query interface for data stored by the ETL pipeline in Elasticsearch and Neo4j.

---

## 🚀 Quick Start

Get up and running in minutes:

<div class="grid cards" markdown>

-   🚀 __[Quick Start Guide](getting-started/quickstart.md)__

    ---

    Get the system running in 5 minutes

-   🔧 __[Configuration](getting-started/configuration.md)__

    ---

    Configure environment variables

-   📚 __[ETL Architecture](architecture/overview.md)__

    ---

    Understand the ETL pipeline design

-   🌐 __[Backend API Overview](backend-api/overview.md)__

    ---

    Learn about the REST API service

</div>

## ✨ Key Features

<div class="grid cards" markdown>

-   🧩 __Modular Design__

    ---

    Easily add new data sources and API endpoints without modifying existing code

-   ✅ __FAIR4ML Compliance__

    ---

    All metadata follows standardized schema for FAIRness

-   📊 __Graph Storage__

    ---

    Neo4j enables relationship-based discovery and recommendations

-   🔍 __Fast Indexing__

    ---

    Elasticsearch provides powerful search capabilities

-   ⚙️ __Dagster Orchestration__

    ---

    Reliable, observable pipeline execution with automatic retries

-   🐳 __Docker-Based__

    ---

    Isolated components for easy deployment and scaling

-   🌐 __REST API__

    ---

    FastAPI-based API with automatic OpenAPI documentation

-   📡 __Graph Exploration__

    ---

    Query and traverse relationships in the knowledge graph

</div>

## 🌐 About MLentory

MLentory is part of the [NFDI4DS](https://www.nfdi4datascience.de/) (National Research Data Infrastructure for Data Science and Artificial Intelligence) portfolio. The complete MLentory ecosystem includes:

- **ETL Pipeline** - Processes and stores metadata (documented here)
- **Backend API** - REST API built with FastAPI (documented here)
- **Frontend Interface** - User-friendly web interface built with Vue.js
- **Search Engine** - Natural language search powered by LLMs and Elasticsearch

---

## 🚦 Next Steps

Ready to get started? Choose your path:

### 📚 New to These Concepts?

If you're unfamiliar with schemas, Dagster, Neo4j, or Elasticsearch:

**[Key Concepts Tutorial](concepts-tutorial.md)** → Quick beginner-friendly tutorials

### 📐 Understanding Schemas

Learn about the three standardized schemas that power MLentory:

**[Schemas Overview](schemas/schemas.md)** → FAIR4ML, Croissant ML, and Schema.org explained

### 🔄 For ETL Pipeline

1. **[Quick Start](getting-started/quickstart.md)** → Get the pipeline running
2. **[Explore the architecture](architecture/overview.md)** → Understand the components
3. **[Learn the concepts](concepts/etl-overview.md)** → Build your knowledge

### 🌐 For Backend API

1. **[Quick Start Guide](getting-started/quickstart.md)** → Complete setup (ETL + API)
2. **[API Overview](backend-api/overview.md)** → Understand the API structure
3. **[API Usage Guide](backend-api/usage/quickstart.md)** → Start using the API
4. **[API Endpoints](backend-api/endpoints/models.md)** → Explore available endpoints
5. **[API Examples](backend-api/usage/examples.md)** → See code examples

---

<div class="admonition tip" markdown>

**Need Help?**

This documentation is continuously being improved. If you have questions, suggestions, or want to contribute, please check out our [contributing guide](development/contributing.md) or open an issue.

</div>
