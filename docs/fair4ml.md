# FAIR4ML Schema Documentation

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

```json
{
  "mappings": {
    "properties": {
      "id": { "type": "keyword" },
      "name": { "type": "text", "fields": { "keyword": { "type": "keyword" } } },
      "description": { "type": "text" },
      "framework": { "type": "keyword" },
      "task": { "type": "keyword" },
      "authors": { "type": "keyword" },
      "organization": { "type": "keyword" },
      "license": { "type": "keyword" },
      "created_at": { "type": "date" },
      "updated_at": { "type": "date" },
      "source": { "type": "keyword" }
    }
  }
}
```

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

## Source-Specific Mappings

### HuggingFace → FAIR4ML

| HF Field | FAIR4ML Field |
|----------|---------------|
| `modelId` | `id` |
| `modelName` | `name` |
| `pipeline_tag` | `task.name` |
| `library_name` | `framework.name` |
| `downloads` | metadata |
| `tags` | metadata |

### PapersWithCode → FAIR4ML

| PWC Field | FAIR4ML Field |
|-----------|---------------|
| `id` | `id` |
| `name` | `name` |
| `paper` | `Paper` entity |
| `tasks` | `task` |
| `results` | `metrics` |

### OpenML → FAIR4ML

| OpenML Field | FAIR4ML Field |
|--------------|---------------|
| `run_id` | `id` |
| `flow_name` | `name` |
| `task_id` | `task` |
| `evaluations` | `metrics` |

## Validation Rules

1. **Required Fields**: `id`, `name`, `source`, `source_url`
2. **Unique IDs**: Globally unique within source
3. **Date Formats**: ISO 8601
4. **URLs**: Must be valid HTTP/HTTPS URLs
5. **Licenses**: Should use SPDX identifiers when possible

## Extensibility

To extend the schema for new sources:

1. Define source-specific schema in `schemas/sources/<source>.py`
2. Implement mapping logic in transformer
3. Update documentation
4. Ensure backward compatibility

## References

- [FAIR Principles](https://www.go-fair.org/fair-principles/)
- [MLSchema.org](http://mlschema.org/)
- [DCAT Vocabulary](https://www.w3.org/TR/vocab-dcat-2/)
- [Croissant Format](https://github.com/mlcommons/croissant)

