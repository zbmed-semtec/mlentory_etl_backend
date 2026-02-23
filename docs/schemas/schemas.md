# Schemas in MLentory

MLentory uses three standardized schemas to describe machine learning models and their related entities. Understanding these schemas is essential for working with MLentory's data, whether you're transforming data, querying the knowledge graph, or extending the system.

---

## 📋 Overview

MLentory transforms data from multiple sources (HuggingFace, OpenML, AI4Life, etc.) into a unified, standardized format using three complementary schemas:

1. **FAIR4ML** - For describing machine learning models
2. **Croissant ML** - For describing datasets
3. **Schema.org** - For describing papers, licenses, languages, and other related entities

These schemas work together to create a rich, interconnected knowledge graph where models, datasets, papers, and people are all described consistently and can be linked together.

The three schemas work together to describe the complete ML ecosystem—models, datasets, papers, and related entities. FAIR4ML describes models, Croissant ML describes datasets, and Schema.org describes papers, licenses, and other related entities.

---

## 🎯 Why Three Schemas?

You might wonder why we need three different schemas instead of one. The answer lies in specialization and compatibility:

**FAIR4ML** is specifically designed for ML models. It includes ML-specific properties like `mlTask`, `modelCategory`, and `fineTunedFrom` that don't make sense for other types of entities.

**Croissant ML** is specifically designed for ML datasets. It provides rich metadata about dataset structure, licensing, and usage that's essential for understanding training and evaluation data.

**Schema.org** is a general-purpose vocabulary used across the web. It provides standard properties for papers, licenses, languages, and other entities that are part of the ML ecosystem but aren't ML-specific.

By using specialized schemas for specialized purposes, we get:

- **Better semantics**: Each schema has properties that are meaningful for its domain
- **Standards compliance**: We follow established standards rather than inventing our own
- **Interoperability**: Our data can be understood by systems that use these standards
- **Extensibility**: We can add new sources and entities without breaking existing systems

---

## 🤖 FAIR4ML: The ML Model Schema

**FAIR4ML** (FAIR for Machine Learning) is a standardized vocabulary specifically designed for describing machine learning model metadata. It's maintained by the Research Data Alliance (RDA) FAIR4ML Interest Group and provides a common language for describing ML models across different platforms.

### 🤔 What is FAIR4ML?

FAIR4ML extends Schema.org by adding ML-specific properties while reusing general-purpose properties like `name`, `description`, and `author`. This design ensures compatibility with web standards while providing ML-specific capabilities.

### 🔑 Key Properties

FAIR4ML models include properties for:

- **Core Identification**: `identifier`, `name`, `url`
- **Authorship**: `author`, `sharedBy`
- **Temporal Information**: `dateCreated`, `dateModified`, `datePublished`
- **Description**: `description`, `keywords`, `inLanguage`, `license`
- **ML-Specific**: `mlTask`, `modelCategory`, `fineTunedFrom`
- **Training Data**: `trainedOn`, `testedOn`, `evaluatedOn`
- **Evaluation**: `evaluationMetrics`
- **Ethics & Risks**: `modelRisksBiasLimitations`, `ethicalSocial`, `legal`
- **Usage**: `intendedUse`, `usageInstructions`, `codeSampleSnippet`

### 💡 Example FAIR4ML Model

```json
{
  "@type": "fair4ml:MLModel",
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "BERT Base Uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "Google",
  "mlTask": ["fill-mask"],
  "modelCategory": ["transformer", "bert"],
  "trainedOn": ["https://huggingface.co/datasets/wikipedia"],
  "license": "apache-2.0"
}
```

### 📚 Official Resources

- **Vocabulary**: [https://w3id.org/fair4ml](https://w3id.org/fair4ml)
- **Specification**: [FAIR4ML v0.1.0](https://rda-fair4ml.github.io/FAIR4ML-schema/release/0.1.0/index.html)
- **Repository**: [RDA-FAIR4ML/FAIR4ML-schema](https://github.com/RDA-FAIR4ML/FAIR4ML-schema)

> **📖 For complete property reference**: See [FAIR4ML Schema Reference](fair4ml.md)

---

## 📊 Croissant ML: The Dataset Schema

**Croissant ML** is a metadata format for machine learning datasets, developed by MLCommons. It extends Schema.org's Dataset with ML-specific properties and provides rich metadata about dataset structure, licensing, and usage.

### 🤔 What is Croissant ML?

Croissant ML is designed to make ML datasets more discoverable, reusable, and interoperable. It provides structured metadata that helps researchers understand what datasets contain, how they're structured, and how they can be used.

### 🔑 Key Properties

Croissant datasets include properties for:

- **Core Identification**: `identifier`, `name`, `url`, `sameAs`
- **Description**: `description`, `keywords`
- **Licensing**: `license`
- **Citation**: `citeAs`
- **Creator Information**: `creator`
- **Temporal Information**: `datePublished`, `dateModified`
- **Conformance**: `conformsTo` (Croissant version)

### 💡 Example Croissant Dataset

```json
{
  "@type": "cr:Dataset",
  "identifier": ["https://huggingface.co/datasets/squad"],
  "name": "SQuAD",
  "url": "https://huggingface.co/datasets/squad",
  "description": "Stanford Question Answering Dataset",
  "license": "https://creativecommons.org/licenses/by-sa/4.0/",
  "creator": "Stanford NLP",
  "conformsTo": "http://mlcommons.org/croissant/1.0"
}
```

### 📚 Official Resources

- **Specification**: [Croissant ML Specification](https://raw.githubusercontent.com/mlcommons/croissant/main/docs/croissant-spec.md)
- **Repository**: [mlcommons/croissant](https://github.com/mlcommons/croissant)

---

## 🌐 Schema.org: The General-Purpose Schema

**Schema.org** is a collaborative effort by Google, Microsoft, Yahoo, and Yandex to create a common vocabulary for structured data on the web. It provides standard properties for describing various types of entities, from creative works to organizations.

### 🤔 What is Schema.org?

Schema.org is the foundation that both FAIR4ML and Croissant ML build upon. It provides general-purpose properties that work for any type of content, ensuring compatibility across different systems and domains.

### 🏷️ Schema.org Entities Used in MLentory

MLentory uses several Schema.org entity types:

**ScholarlyArticle** - Represents research papers that describe or cite models:
- Properties: `identifier`, `name`, `url`, `description`, `author`, `datePublished`
- Used for: Linking models to their research papers

**DefinedTerm** - Represents ML tasks and categories:
- Properties: `name`, `description`
- Used for: Representing ML tasks like "text-classification" or "image-generation"

**Language** - Represents natural languages:
- Properties: `name`, `identifier`
- Used for: Representing languages that models support (e.g., "en", "de", "fr")

**CreativeWork** - Represents licenses and other creative works:
- Properties: `name`, `identifier`, `url`
- Used for: Representing licenses like "apache-2.0" or "mit"

### 💡 Example Schema.org Entities

**ScholarlyArticle:**
```json
{
  "@type": "schema:ScholarlyArticle",
  "identifier": ["https://arxiv.org/abs/1810.04805"],
  "name": "BERT: Pre-training of Deep Bidirectional Transformers",
  "url": "https://arxiv.org/abs/1810.04805",
  "author": ["Devlin, Jacob", "Chang, Ming-Wei"],
  "datePublished": "2018-10-11"
}
```

**DefinedTerm (ML Task):**
```json
{
  "@type": "schema:DefinedTerm",
  "name": "fill-mask",
  "description": "Predicting masked words in text"
}
```

### 📚 Official Resources

- **Vocabulary**: [https://schema.org/](https://schema.org/)
- **Documentation**: [Schema.org Documentation](https://schema.org/docs/gs.html)

---

## 🔄 How Schemas Work Together

The three schemas work together to create a comprehensive knowledge graph. Here's how they interact:

### 🔗 The Model-Dataset-Paper Connection

1. **FAIR4ML models** reference **Croissant datasets** through properties like `trainedOn`, `testedOn`, and `evaluatedOn`
2. **FAIR4ML models** reference **Schema.org ScholarlyArticle** papers through `referencePublication`
3. **FAIR4ML models** reference **Schema.org DefinedTerm** entities for ML tasks and categories
4. **FAIR4ML models** reference **Schema.org Language** entities through `inLanguage`
5. **FAIR4ML models** reference **Schema.org CreativeWork** entities for licenses

This creates a rich, interconnected graph where you can:

- Find all models trained on a specific dataset
- Find all papers that describe a model
- Find all models that perform a specific task
- Find all models that support a specific language

### 💡 Example: Complete Model with Related Entities

```json
{
  "@type": "fair4ml:MLModel",
  "name": "BERT Base Uncased",
  "mlTask": [
    {
      "@type": "schema:DefinedTerm",
      "name": "fill-mask"
    }
  ],
  "trainedOn": [
    {
      "@type": "cr:Dataset",
      "name": "Wikipedia",
      "identifier": ["https://huggingface.co/datasets/wikipedia"]
    }
  ],
  "referencePublication": [
    {
      "@type": "schema:ScholarlyArticle",
      "name": "BERT: Pre-training of Deep Bidirectional Transformers",
      "url": "https://arxiv.org/abs/1810.04805"
    }
  ],
  "inLanguage": [
    {
      "@type": "schema:Language",
      "name": "English",
      "identifier": "en"
    }
  ],
  "license": {
    "@type": "schema:CreativeWork",
    "name": "Apache License 2.0",
    "identifier": "apache-2.0"
  }
}
```

---

## 🛠️ How MLentory Uses These Schemas

MLentory uses these schemas throughout the ETL pipeline:

### 🔄 Transformation

During transformation, source-specific data is converted into standardized schemas:

- **Raw HuggingFace data** → **FAIR4ML MLModel**
- **Raw dataset information** → **Croissant Dataset**
- **Raw paper references** → **Schema.org ScholarlyArticle**
- **Raw task tags** → **Schema.org DefinedTerm**
- **Raw language codes** → **Schema.org Language**
- **Raw license strings** → **Schema.org CreativeWork**

This ensures data from different sources (HuggingFace, OpenML, AI4Life) is normalized into a common format that can be compared and linked together.

> **📖 For transformation details**: See [Transformers Overview](../transformers/overview.md) and [Source Schemas](source-schemas.md)

### 💾 Storage

The normalized schemas are stored in multiple systems optimized for different query patterns:

**Neo4j** stores the graph structure:

- Models, datasets, papers, and other entities are nodes
- Relationships connect them (e.g., `TRAINED_ON`, `CITES`, `PERFORMS_TASK`)
- Enables relationship-based queries and graph traversal

**Elasticsearch** stores the full-text search index:

- All schema properties are indexed for fast search
- Enables full-text search across models, datasets, and papers
- Faceted search uses schema properties as filters

**RDF Export** creates semantic web files:

- JSON-LD format using schema property IRIs
- Enables semantic web compatibility
- Can be imported into other RDF systems

> **📖 For storage details**: See [Loaders Overview](../loaders/overview.md)

### 🔌 API

The Backend API uses the schemas to:

- Return data in standardized formats
- Enable filtering by schema properties
- Support graph queries that traverse relationships
- Provide faceted search using schema properties

> **📖 For API details**: See [Backend API Overview](../backend-api/overview.md)

---

## 💻 Implementation in MLentory

MLentory implements these schemas using **Pydantic**, a Python library for data validation. This provides:

- **Type Safety**: Fields are validated against their expected types
- **Automatic Validation**: Invalid data is caught early
- **JSON-LD Compatibility**: Fields use aliases that match JSON-LD property IRIs
- **Documentation**: Models serve as living documentation

### 📁 Schema Location in Codebase

- **FAIR4ML**: `schemas/fair4ml/mlmodel.py`
- **Croissant**: `schemas/croissant/dataset.py`
- **Schema.org**: `schemas/schemaorg/` (multiple files for different entity types)

### 💻 Using Schemas in Code

```python
from schemas.fair4ml import MLModel
from schemas.croissant import CroissantDataset
from schemas.schemaorg import ScholarlyArticle

# Create a FAIR4ML model
model = MLModel(
    identifier=["https://huggingface.co/bert-base-uncased"],
    name="BERT Base Uncased",
    mlTask=["fill-mask"]
)

# Create a Croissant dataset
dataset = CroissantDataset(
    identifier=["https://huggingface.co/datasets/wikipedia"],
    name="Wikipedia",
    license="cc-by-sa-4.0"
)

# Create a Schema.org article
article = ScholarlyArticle(
    identifier=["https://arxiv.org/abs/1810.04805"],
    name="BERT: Pre-training of Deep Bidirectional Transformers",
    url="https://arxiv.org/abs/1810.04805"
)
```

> **📖 For complete implementation details**: See [Schema Structure](structure.md)

---

## 🎓 Key Takeaways

1. **Three Specialized Schemas**: FAIR4ML for models, Croissant for datasets, Schema.org for related entities
2. **Interconnected Ecosystem**: Schemas work together to create a rich knowledge graph
3. **Standards Compliance**: Using established standards ensures interoperability
4. **Transformation Pipeline**: MLentory converts source data into these standardized formats
5. **Dual Storage**: Data is stored in Neo4j (graph) and Elasticsearch (search)
6. **Pydantic Implementation**: Schemas are implemented as Pydantic models for validation

---

## 🚀 Next Steps

Now that you understand the schemas:

- **[FAIR4ML Schema Reference](fair4ml.md)** → Complete FAIR4ML property reference
- **[Source Schemas](source-schemas.md)** → How source data maps to schemas
- **[Schema Structure](structure.md)** → Pydantic implementation details
- **[Transformers Overview](../transformers/overview.md)** → How transformation works
- **[ETL Pipeline Architecture](../architecture/overview.md)** → Complete system overview

---

## 📖 Further Reading

- **FAIR4ML**: [Official Specification](https://rda-fair4ml.github.io/FAIR4ML-schema/release/0.1.0/index.html)
- **Croissant ML**: [MLCommons Croissant](https://github.com/mlcommons/croissant)
- **Schema.org**: [Schema.org Documentation](https://schema.org/docs/gs.html)
- **RDA FAIR4ML Interest Group**: [RDA FAIR4ML-IG](https://www.rd-alliance.org/groups/fair-machine-learning-ig)
