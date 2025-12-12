# FAIR4ML Schema

FAIR4ML is a standardized vocabulary for describing machine learning model metadata. This guide explains what FAIR4ML is, why it matters, and how it's used in the MLentory pipeline.

---

## What is FAIR4ML?

**FAIR4ML** (FAIR for Machine Learning) is a semantic vocabulary designed to describe ML model metadata in a structured, machine-readable format. It extends [schema.org](https://schema.org/) to provide ML-specific properties while maintaining compatibility with existing web standards.

### Official Resources

- **GitHub Repository:** [RDA-FAIR4ML/FAIR4ML-schema](https://github.com/RDA-FAIR4ML/FAIR4ML-schema)
- **Vocabulary URL:** `https://w3id.org/fair4ml#` (with content negotiation)
- **Latest Version:** v0.1.0 (as of 2024)
- **Paper:** [FAIR4ML, a vocabulary to describe Machine/Deep Learning models](https://zenodo.org/records/16735334)

### Why FAIR4ML Exists

**The Problem:**
- ML models are scattered across multiple platforms (HuggingFace, OpenML, etc.)
- Each platform uses different metadata formats
- Model descriptions are often buried in text (READMEs, papers)
- No standard way to compare models across platforms
- Difficult to find and reuse models

**The Solution:**
FAIR4ML provides a standardized vocabulary that:
- Enables comparison across different sources
- Supports machine-readable metadata
- Facilitates model discovery and reuse
- Adheres to FAIR principles (Findable, Accessible, Interoperable, Reusable)

---

## FAIR Principles

FAIR4ML is designed to make ML models **FAIR**:

### Findable
- Models have unique, persistent identifiers
- Rich metadata makes models discoverable
- Models are indexed in searchable systems

### Accessible
- Metadata is retrievable via standard protocols
- Clear access conditions (licenses, terms)
- Persistent identifiers link to model resources

### Interoperable
- Uses standard vocabularies (schema.org, RDF)
- Compatible with other research metadata schemas
- Machine-readable format (JSON-LD, RDF)

### Reusable
- Rich metadata describes model capabilities
- Clear licensing and usage terms
- Documentation of training data and methods
- Reproducibility information

---

## Schema Structure

FAIR4ML extends schema.org, which means:

1. **Core Properties** use schema.org terms (e.g., `name`, `description`, `author`)
2. **ML-Specific Properties** use FAIR4ML namespace (e.g., `fair4ml:mlTask`, `fair4ml:modelCategory`)
3. **Compatibility** with other schema.org extensions (Bioschemas, CodeMeta, Croissant)

### Namespace

- **FAIR4ML:** `https://w3id.org/fair4ml#`
- **Schema.org:** `https://schema.org/`
- **CodeMeta:** `https://w3id.org/codemeta/`

### Example Structure

```json
{
  "@context": {
    "schema": "https://schema.org/",
    "fair4ml": "https://w3id.org/fair4ml#"
  },
  "@type": "fair4ml:MLModel",
  "schema:identifier": "https://huggingface.co/bert-base-uncased",
  "schema:name": "BERT Base Uncased",
  "schema:description": "BERT model for masked language modeling",
  "fair4ml:mlTask": ["fill-mask"],
  "fair4ml:modelCategory": ["transformer"]
}
```

---

## Core Entities

### MLModel

The primary entity representing a machine learning model.

**Core Identification:**
- `identifier`: Unique identifier (typically URL)
- `name`: Human-readable name
- `url`: Primary access URL

**Authorship & Provenance:**
- `author`: Model creator(s)
- `sharedBy`: Person/organization who shared the model
- `dateCreated`, `dateModified`, `datePublished`: Temporal information

**Description:**
- `description`: Full model description
- `keywords`: Tags/keywords
- `inLanguage`: Natural languages the model works with
- `license`: License information

**ML-Specific:**
- `mlTask`: ML tasks addressed (e.g., "text-classification", "image-generation")
- `modelCategory`: Model architecture (e.g., "transformer", "CNN", "LLM")
- `fineTunedFrom`: Base model this was fine-tuned from
- `intendedUse`: Intended use cases
- `trainedOn`: Training datasets
- `evaluatedOn`: Evaluation datasets
- `evaluationMetrics`: Performance metrics

**Code & Usage:**
- `codeSampleSnippet`: Example code snippets
- `usageInstructions`: How to use the model

**Ethics & Risks:**
- `modelRisksBiasLimitations`: Known limitations and biases
- `ethicalSocial`: Ethical considerations

### Related Entities

FAIR4ML also defines entities for:

- **Dataset:** Training/evaluation datasets (uses Croissant ML schema)
- **Paper:** Research publications (uses Schema.org ScholarlyArticle)
- **Author:** Model/paper authors (uses Schema.org Person)
- **Organization:** Institutions/companies (uses Schema.org Organization)
- **Task:** ML tasks (uses Schema.org DefinedTerm)
- **License:** License information (uses Schema.org CreativeWork)

---

## FAIR4ML in MLentory

### How We Use It

1. **Transformation Target**
   - All source data (HuggingFace, OpenML, AI4Life) is transformed to FAIR4ML
   - Ensures unified format across all sources

2. **Validation**
   - Pydantic models enforce FAIR4ML structure
   - Catches errors early in the pipeline
   - Ensures data quality

3. **Storage**
   - FAIR4ML data stored in Neo4j as RDF triples
   - Enables semantic queries and relationships
   - Supports interoperability with other systems

4. **Export**
   - RDF/Turtle files use FAIR4ML vocabulary
   - Enables integration with semantic web tools
   - Supports FAIR data principles

### Implementation

Our Pydantic models in `schemas/fair4ml/mlmodel.py` implement FAIR4ML v0.1.0:

```python
from schemas.fair4ml import MLModel

# Create a FAIR4ML model
model = MLModel(
    identifier=["https://huggingface.co/bert-base-uncased"],
    name="BERT Base Uncased",
    mlTask=["fill-mask"],
    modelCategory=["transformer"]
)
```

---

## FAIR4ML Versions

### Current Version: v0.1.0

Released October 2024, includes:
- Core ML model properties
- Task and category definitions
- Lineage and provenance
- Usage and code examples

### Future Versions

Planned enhancements (discussed in [RDA FAIR4ML-IG](https://github.com/RDA-FAIR4ML/FAIR4ML-schema)):
- Metrics and evaluation results
- Hyperparameter representation
- Model generation process details
- External validation information

---

## Compatibility with Other Schemas

FAIR4ML is designed to work alongside other research metadata schemas:

### Schema.org Extensions
- **Bioschemas:** Life science data
- **CodeMeta:** Research software
- **Croissant ML:** ML datasets
- **Science on Schema.org:** Research artifacts

### RDA Standards
- **RDA Research Metadata:** Dataset descriptions
- **FAIR Digital Objects:** Research artifact packaging

### Why This Matters

- Models can be described alongside their datasets (Croissant)
- Models can reference their software dependencies (CodeMeta)
- Models can be packaged as FAIR Digital Objects
- Enables cross-platform discovery and integration

---

## Example: Complete FAIR4ML Model

```json
{
  "@context": {
    "schema": "https://schema.org/",
    "fair4ml": "https://w3id.org/fair4ml#"
  },
  "@type": "fair4ml:MLModel",
  "schema:identifier": ["https://huggingface.co/bert-base-uncased"],
  "schema:name": "BERT Base Uncased",
  "schema:url": "https://huggingface.co/bert-base-uncased",
  "schema:author": "Google",
  "schema:datePublished": "2018-10-11",
  "schema:description": "BERT model for masked language modeling",
  "schema:keywords": ["bert", "transformer", "nlp"],
  "schema:license": "Apache-2.0",
  "fair4ml:mlTask": ["fill-mask"],
  "fair4ml:modelCategory": ["transformer"],
  "fair4ml:fineTunedFrom": ["https://huggingface.co/google/bert-base-uncased"],
  "fair4ml:trainedOn": [
    {
      "@type": "schema:Dataset",
      "schema:name": "Wikipedia + BookCorpus"
    }
  ],
  "fair4ml:evaluatedOn": [
    {
      "@type": "schema:Dataset",
      "schema:name": "GLUE"
    }
  ]
}
```

---

## Key Takeaways

1. **FAIR4ML** is a standardized vocabulary for ML model metadata
2. **Extends schema.org** for compatibility with web standards
3. **Enables FAIR principles** (Findable, Accessible, Interoperable, Reusable)
4. **Unifies metadata** across different ML model platforms
5. **Machine-readable** format supports automated processing
6. **Compatible** with other research metadata schemas

---

## Further Reading

- **FAIR4ML Repository:** [https://github.com/RDA-FAIR4ML/FAIR4ML-schema](https://github.com/RDA-FAIR4ML/FAIR4ML-schema)
- **FAIR4ML Vocabulary:** [https://w3id.org/fair4ml](https://w3id.org/fair4ml)
- **Research Paper:** [FAIR4ML, a vocabulary to describe Machine/Deep Learning models](https://zenodo.org/records/16735334)
- **Schema.org:** [https://schema.org/](https://schema.org/)
- **RDA FAIR4ML Interest Group:** [RDA FAIR4ML-IG](https://www.rd-alliance.org/groups/fair-machine-learning-ig)

---

## Next Steps

- See [Schema Structure](../schemas/structure.md) - How we implement FAIR4ML in code
- Explore [Transformers](../transformers/overview.md) - How we transform data to FAIR4ML
- Check [Schemas API](../api/schemas.md) - Complete API reference
