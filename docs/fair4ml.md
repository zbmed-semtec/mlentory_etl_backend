# FAIR4ML Schema Documentation

Release metadata (aligned with FAIR4ML 0.1.0):

- Release date: 2024-10-27
- Version: 0.1.0
- Status: Draft (under review)
- This version URI: https://w3id.org/fair4ml/0.1.0
- Latest version URI: https://w3id.org/fair4ml#
- License: CC0-1.0
- Specification: https://rda-fair4ml.github.io/FAIR4ML-schema/release/0.1.0/index.html

### Namespaces used

- `rdf`: http://www.w3.org/1999/02/22-rdf-syntax-ns#
- `rdfs`: http://www.w3.org/2000/01/rdf-schema#
- `owl`: http://www.w3.org/2002/07/owl#
- `schema`: http://schema.org/
- `codemeta`: https://w3id.org/codemeta/
- `fair4ml`: https://w3id.org/fair4ml#
- `cr`: http://mlcommons.org/croissant/

### Extending Schema.org hierarchy

This profile extends Schema.org with two main classes:

```
schema:Thing > schema:CreativeWork > fair4ml:MLModel
schema:Thing > schema:CreativeWork > fair4ml:MLModelEvaluation
```

### fair4ml:MLModel — new properties

| Property | Expected Type | Description |
|---|---|---|
| [fair4ml:legal](https://w3id.org/fair4ml#legal) | [schema:Text](http://schema.org/Text) | Considerations with respect to legal aspects. |
| [fair4ml:ethicalSocial](https://w3id.org/fair4ml#ethicalSocial) | [schema:Text](http://schema.org/Text) | Considerations with respect to ethical and social aspects. |
| [fair4ml:evaluatedOn](https://w3id.org/fair4ml#evaluatedOn) | [schema:Dataset](http://schema.org/Dataset), [cr:Dataset](http://mlcommons.org/croissant/1.0) | Dataset used for evaluating the model (may be extrinsic). |
| [fair4ml:fineTunedFrom](https://w3id.org/fair4ml#fineTunedFrom) | [fair4ml:MLModel](https://w3id.org/fair4ml#MLModel) | Source model used for fine-tuning. |
| [fair4ml:hasCO2eEmissions](https://w3id.org/fair4ml#hasCO2eEmissions) | [schema:Text](http://schema.org/Text) | CO2e emissions produced by training (include units, e.g., "10 tonnes"). |
| [fair4ml:intendedUse](https://w3id.org/fair4ml#intendedUse) | [schema:Text](http://schema.org/Text), [schema:DefinedTerm](http://schema.org/DefinedTerm), [schema:URL](http://schema.org/URL) | Purpose and intended use to help assess suitability. |
| [fair4ml:mlTask](https://w3id.org/fair4ml#mlTask) | [schema:Text](http://schema.org/Text), [schema:DefinedTerm](http://schema.org/DefinedTerm) | ML task addressed by the model (e.g., binary classification). |
| [fair4ml:modelCategory](https://w3id.org/fair4ml#modelCategory) | [schema:Text](http://schema.org/Text), [schema:DefinedTerm](http://schema.org/DefinedTerm) | Category (e.g., Supervised), architecture (e.g., transformer), or algorithm. |
| [fair4ml:modelRisksBiasLimitations](https://w3id.org/fair4ml#modelRisksBiasLimitations) | [schema:Text](http://schema.org/Text) | Description of risks, biases, and limitations. |
| [fair4ml:sharedBy](https://w3id.org/fair4ml#sharedBy) | [schema:Person](http://schema.org/Person), [schema:Organization](http://schema.org/Organization) | Person or organization who shared the model online. |
| [fair4ml:testedOn](https://w3id.org/fair4ml#testedOn) | [schema:Dataset](http://schema.org/Dataset), [cr:Dataset](http://mlcommons.org/croissant/1.0) | Dataset used to test the model (train/test/validation splits). |
| [fair4ml:trainedOn](https://w3id.org/fair4ml#trainedOn) | [schema:Dataset](http://schema.org/Dataset), [cr:Dataset](http://mlcommons.org/croissant/1.0) | AI-ready dataset used for training/optimization. |
| [fair4ml:usageInstructions](https://w3id.org/fair4ml#usageInstructions) | [schema:Text](http://schema.org/Text) | Instructions needed to run the model (may include code). |
| [fair4ml:codeSampleSnippet](https://w3id.org/fair4ml#codeSampleSnippet) | [schema:Text](http://schema.org/Text) | Code snippet with an example usage of the model. |
| [fair4ml:validatedOn](https://w3id.org/fair4ml#validatedOn) | [schema:Dataset](http://schema.org/Dataset), [cr:Dataset](http://mlcommons.org/croissant/1.0) | Dataset used to validate the model. |

Note: `fair4ml:MLModel` also inherits properties from Schema.org `CreativeWork` and CodeMeta.

### fair4ml:MLModelEvaluation — new properties

| Property | Expected Type | Description |
|---|---|---|
| [fair4ml:hasEvaluation](https://w3id.org/fair4ml#hasEvaluation) | [fair4ml:MLModelEvaluation](https://w3id.org/fair4ml#MLModelEvaluation) | Associates a model with an evaluation instance. |
| [fair4ml:evaluatedMLModel](https://w3id.org/fair4ml#evaluatedMLModel) | [fair4ml:MLModel](https://w3id.org/fair4ml#MLModel) | Model evaluated (reverse: `fair4ml:evaluatedWith`). |
| [fair4ml:evaluationDataset](https://w3id.org/fair4ml#evaluationDataset) | [cr:Dataset](http://mlcommons.org/croissant/1.0) | Dataset used for the evaluation. |
| [fair4ml:evaluationMetrics](https://w3id.org/fair4ml#evaluationMetrics) | [schema:Text](http://schema.org/Text), [schema:PropertyValue](http://schema.org/PropertyValue) | Metrics used for evaluating the model (text or structured values). |
| [fair4ml:evaluationResults](https://w3id.org/fair4ml#evaluationResults) | [schema:Text](http://schema.org/Text) | Summary of the evaluation results. |
| [fair4ml:evaluationSoftware](https://w3id.org/fair4ml#evaluationSoftware) | [schema:SoftwareSourceCode](http://schema.org/SoftwareSourceCode), [schema:SoftwareApplication](http://schema.org/SoftwareApplication) | Code/software used to perform the evaluation. |
| [fair4ml:extrinsicEvaluation](https://w3id.org/fair4ml#extrinsicEvaluation) | [schema:Boolean](http://schema.org/Boolean) | Whether the evaluation is extrinsic (outside the training scope, unseen dataset). |

Note: `fair4ml:MLModelEvaluation` inherits from Schema.org `CreativeWork` and CodeMeta.

## Overview

FAIR4ML is a schema for representing ML model metadata in a FAIR (Findable, Accessible, Interoperable, Reusable) manner. This document describes the core entities and their relationships.

## Core Entities

### Model

Represents an ML model with its metadata.

**Fields:**
- `id` (str): Unique identifier
- `name` (str): Model name
- `description` (str, optional): Model description
- `version` (str, optional): Model version
- `framework` (Framework): ML framework used
- `task` (Task): Primary ML task
- `datasets` (list[Dataset]): Associated datasets
- `metrics` (list[Metric]): Performance metrics
- `authors` (list[Author]): Model creators
- `organization` (Organization, optional): Publishing organization
- `license` (str, optional): License information
- `created_at` (datetime): Creation timestamp
- `updated_at` (datetime): Last update timestamp
- `source` (str): Data source (e.g., "huggingface")
- `source_url` (str): Original URL

### Dataset

Represents a dataset used for training or evaluation.

**Fields:**
- `id` (str): Unique identifier
- `name` (str): Dataset name
- `description` (str, optional): Dataset description
- `size` (int, optional): Number of samples
- `task` (Task): Associated ML task
- `license` (str, optional): License information
- `source_url` (str, optional): Dataset URL

### Paper

Represents a research paper associated with a model.

**Fields:**
- `id` (str): Unique identifier (e.g., arXiv ID)
- `title` (str): Paper title
- `abstract` (str, optional): Paper abstract
- `authors` (list[Author]): Paper authors
- `published_at` (datetime, optional): Publication date
- `venue` (str, optional): Publication venue
- `url` (str, optional): Paper URL
- `arxiv_id` (str, optional): arXiv identifier
- `doi` (str, optional): DOI

### Author

Represents an individual who created a model or paper.

**Fields:**
- `id` (str): Unique identifier
- `name` (str): Author name
- `email` (str, optional): Contact email
- `affiliation` (str, optional): Organization affiliation
- `orcid` (str, optional): ORCID identifier

### Organization

Represents an institution or company.

**Fields:**
- `id` (str): Unique identifier
- `name` (str): Organization name
- `type` (str): Organization type (academic, industry, etc.)
- `website` (str, optional): Organization website

### Task

Represents an ML task type.

**Fields:**
- `id` (str): Unique identifier
- `name` (str): Task name (e.g., "image-classification")
- `category` (str): Task category (e.g., "computer-vision")
- `description` (str, optional): Task description

### Framework

Represents an ML framework.

**Fields:**
- `id` (str): Unique identifier
- `name` (str): Framework name (e.g., "pytorch")
- `version` (str, optional): Framework version

### Metric

Represents a performance metric.

**Fields:**
- `id` (str): Unique identifier
- `name` (str): Metric name (e.g., "accuracy")
- `value` (float): Metric value
- `dataset` (Dataset, optional): Evaluation dataset
- `config` (dict, optional): Additional configuration

## Relationships

### Neo4j Graph Model

```
(Model)-[:USES_FRAMEWORK]->(Framework)
(Model)-[:PERFORMS_TASK]->(Task)
(Model)-[:TRAINED_ON]->(Dataset)
(Model)-[:EVALUATED_ON]->(Dataset)
(Model)-[:HAS_METRIC]->(Metric)
(Model)-[:CREATED_BY]->(Author)
(Model)-[:PUBLISHED_BY]->(Organization)
(Model)-[:DESCRIBED_IN]->(Paper)
(Paper)-[:AUTHORED_BY]->(Author)
(Author)-[:AFFILIATED_WITH]->(Organization)
(Dataset)-[:FOR_TASK]->(Task)
(Metric)-[:ON_DATASET]->(Dataset)
```

## Pydantic Schema Structure

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class Framework(BaseModel):
    id: str
    name: str
    version: Optional[str] = None

class Task(BaseModel):
    id: str
    name: str
    category: str
    description: Optional[str] = None

class Author(BaseModel):
    id: str
    name: str
    email: Optional[str] = None
    affiliation: Optional[str] = None
    orcid: Optional[str] = None

class Organization(BaseModel):
    id: str
    name: str
    type: str
    website: Optional[str] = None

class Dataset(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    size: Optional[int] = None
    task: Task
    license: Optional[str] = None
    source_url: Optional[str] = None

class Metric(BaseModel):
    id: str
    name: str
    value: float
    dataset: Optional[Dataset] = None
    config: Optional[dict] = None

class Paper(BaseModel):
    id: str
    title: str
    abstract: Optional[str] = None
    authors: List[Author]
    published_at: Optional[datetime] = None
    venue: Optional[str] = None
    url: Optional[str] = None
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None

class Model(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    version: Optional[str] = None
    framework: Framework
    task: Task
    datasets: List[Dataset] = []
    metrics: List[Metric] = []
    authors: List[Author] = []
    organization: Optional[Organization] = None
    license: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    source: str  # e.g., "huggingface", "paperswithcode"
    source_url: str
```

## Elasticsearch Mapping

Models are indexed in Elasticsearch with the following mapping:

## RDF Representation

Models are exported as RDF using the MLSchema ontology:

```turtle
@prefix mlschema: <http://mlschema.org/> .
@prefix dcat: <http://www.w3.org/ns/dcat#> .
@prefix dct: <http://purl.org/dc/terms/> .

<http://mlentory.org/model/bert-base-uncased>
    a mlschema:Model ;
    dct:title "bert-base-uncased" ;
    dct:description "BERT base model (uncased)" ;
    mlschema:framework "pytorch" ;
    mlschema:task "fill-mask" ;
    dct:creator <http://mlentory.org/author/google> ;
    dct:created "2018-11-03T00:00:00Z"^^xsd:dateTime ;
    dcat:distribution <http://huggingface.co/bert-base-uncased> .
```

## References

- [FAIR Principles](https://www.go-fair.org/fair-principles/)
- [MLSchema.org](http://mlschema.org/)
- [DCAT Vocabulary](https://www.w3.org/TR/vocab-dcat-2/)
- [Croissant Format](https://github.com/mlcommons/croissant)

- FAIR4ML 0.1.0 specification: https://rda-fair4ml.github.io/FAIR4ML-schema/release/0.1.0/index.html

