# MLentory ETL Documentation

Welcome to the comprehensive documentation for the **MLentory ETL Pipeline** the data processing engine that powers [MLentory](https://www.nfdi4datascience.de/services/mlentory_d/), a FAIR Digital Object registry for discovering machine learning models.

---

## 🎯 Overview

### What is MLentory?

[MLentory](https://www.nfdi4datascience.de/services/mlentory_d/) is a comprehensive **FAIR Digital Object (FDO) registry** that provides:

- **🔍 Unified Search** across multiple ML model repositories
- **📊 Harmonized Metadata** using the FAIR4ML schema
- **🤖 Recommendation Service** to find similar models
- **🌐 FAIR Digital Objects** with rich, standardized metadata
- **🔗 Relationship Discovery** between models, datasets, and papers
- **📡 REST API** for programmatic access

MLentory addresses a critical challenge in machine learning research: **finding and comparing ML models** scattered across multiple platforms.

### What is This ETL Pipeline?

**ETL (Extract, Transform, Load) pipeline** the data processing engine that powers MLentory. This documentation focuses on the ETL Pipeline component, which orchestrates a three-stage process that transforms raw model metadata into a harmonized, searchable knowledge base: 

1. **Extract:**  Pull raw metadata from source repositories (HuggingFace, OpenML, AI4Life, etc.)
2. **Transform:** Normalize and harmonize data into the standardized FAIR4ML schema
3. **Load:** Store processed data in Neo4j (graph relationships), Elasticsearch (search index), and export as RDF files

The processed data powers MLentory's search interface, recommendation system, and API.

---

## 🚀 Quick Start

Get up and running in minutes:

<div class="grid cards" markdown>

-   🚀 __[Quick Start Guide](getting-started/quickstart.md)__

    ---

    Get the pipeline running in 5 minutes

-   🔧 __[Configuration](getting-started/configuration.md)__

    ---

    Configure environment variables

-   📚 __[Architecture Overview](architecture/overview.md)__

    ---

    Understand the system design and components

-   💡 __[Key Concepts](concepts/etl-overview.md)__

    ---

    Learn about ETL, FAIR4ML, and related technologies

</div>

---

## ✨ Key Features

<div class="grid cards" markdown>

-   🧩 __Modular Design__

    ---

    Easily add new data sources without modifying existing code

-   ✅ __FAIR4ML Compliance__

    ---

    All metadata follows standardized schema for interoperability

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

-   🕐 __Version Tracking__

    ---

    Historical data stored in PostgreSQL for provenance

-   🌐 __RDF Export__

    ---

    Semantic web formats for integration with other systems

</div>

## 🔑 Key Concepts

### FAIR4ML Schema

A standardized way to describe machine learning models, enabling comparison across different sources. FAIR4ML provides consistent structure for tasks, training data, performance metrics, citations, licensing, and more.

### FAIR Digital Objects (FDOs)

Each model is packaged as a FAIR Digital Object with rich metadata, making models **Findable**, **Accessible**, **Interoperable**, and **Reusable**.

### Knowledge Graph (Neo4j)

MLentory builds a **knowledge graph** using Neo4j to represent rich relationships between ML models, datasets, papers, authors, and organizations. This graph structure enables powerful capabilities like discovering similar models, tracing connections between models and their training data, finding related research papers, and building recommendation systems based on graph-based similarity and relationships.

### Search Indexing (Elasticsearch)

Provides fast, powerful search capabilities with natural language queries, multi-criteria filtering, and relevance ranking across millions of models.

### Dagster Orchestration

Dagster is the orchestration framework that manages the entire ETL pipeline. It provides reliable execution, automatic retries, observability, and dependency management for the Extract, Transform, and Load stages, ensuring data quality and pipeline reliability.

---

## 🌐 About MLentory

MLentory is part of the [NFDI4DS](https://www.nfdi4datascience.de/) (National Research Data Infrastructure for Data Science and Artificial Intelligence) portfolio. The complete MLentory ecosystem includes:

- **ETL Pipeline** (this documentation) - Processes and stores metadata
- **Backend API** - REST API built with FastAPI
- **Frontend Interface** - User-friendly web interface built with Vue.js
- **Search Engine** - Natural language search powered by LLMs and Elasticsearch

---

## 📖 Documentation Structure

<div class="grid cards" markdown>

-   ▶️ __[Getting Started](getting-started/quickstart.md)__

    Quick start, configuration, and first run

-   🏗️ __[Architecture](architecture/overview.md)__

    System design, data flow, and components

-   📖 __[Concepts](concepts/etl-overview.md)__

    ETL fundamentals, FAIR4ML, Dagster, graph databases

-   📥 __[Extractors](extractors/overview.md)__

    HuggingFace, OpenML, AI4Life, and adding new sources

-   🔄 __[Transformers](transformers/overview.md)__

    Data normalization and transformation

-   💾 __[Loaders](loaders/overview.md)__

    Neo4j, Elasticsearch, and RDF export

-   📄 __[Schemas](schemas/fair4ml.md)__

    FAIR4ML schema reference

-   💻 __[Development](development/setup.md)__

    Setup, testing, debugging, contributing

-   🖥️ __[Operations](operations/running-pipelines.md)__

    Running, monitoring, troubleshooting

-   🔗 __[API Reference](api/extractors.md)__

    Complete API documentation

-   🎓 __[Examples](examples/basic-etl.md)__

    Practical examples and tutorials

-   📘 __[Guides](guides/adding-source.md)__

    Step-by-step guides for common tasks

</div>

---

## 🚦 Next Steps

Ready to get started? Follow this path:

1. **[Quick Start](getting-started/quickstart.md)** → Get up and running
2. **[Run your first extraction](getting-started/first-run.md)** → See it in action
3. **[Explore the architecture](architecture/overview.md)** → Understand the components
4. **[Learn the concepts](concepts/etl-overview.md)** → Build your knowledge

---

<div class="admonition tip" markdown>

**Need Help?**

This documentation is continuously being improved. If you have questions, suggestions, or want to contribute, please check out our [contributing guide](development/contributing.md) or open an issue.

</div>
