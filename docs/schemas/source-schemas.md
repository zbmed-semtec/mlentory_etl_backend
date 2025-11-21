# Source Schemas: Understanding Platform-Specific Data Formats

This comprehensive guide explains how different ML model platforms structure their data and how we transform that data into the standardized FAIR4ML format. Understanding source schemas is crucial for debugging transformation issues, extending support to new platforms, and understanding why certain mappings exist.

---

## The Challenge of Multiple Formats

Imagine you're building a system that needs to work with ML models from different platforms. HuggingFace uses `modelId` to identify models, OpenML uses `flow_id`, and AI4Life uses `id`. Each platform has different field names, different data structures, and different conventions. Some platforms store dates as ISO 8601 strings, others as Unix timestamps. Some use arrays for tags, others use comma-separated strings.

This diversity is the fundamental challenge that source schemas address. By understanding each platform's format and how it maps to FAIR4ML, we can build robust transformation logic that handles these differences gracefully.

![Source Schema Transformation](images/source-schema-transformation.png)
*Figure 1: Each source platform uses different data formats, which must be transformed into the unified FAIR4ML schema. Understanding these formats is key to building accurate transformations.*

---

## HuggingFace: The Most Comprehensive Source

HuggingFace Hub is the largest repository of ML models, with millions of models covering every imaginable task. Their data format is relatively rich, providing extensive metadata about models, but it's structured in a HuggingFace-specific way that requires careful transformation.

### Understanding HuggingFace's Data Structure

HuggingFace stores model metadata as JSON objects with a flat structure. Each model has a unique `modelId` (like "bert-base-uncased") that serves as its primary identifier. The metadata includes everything from basic information (name, author) to detailed model cards written in Markdown.

Here's what a typical HuggingFace model looks like:

```json
{
  "modelId": "bert-base-uncased",
  "author": "google",
  "createdAt": "2020-01-01T00:00:00Z",
  "last_modified": "2020-06-15T10:30:00Z",
  "downloads": 1000000,
  "likes": 500,
  "library_name": "transformers",
  "pipeline_tag": "fill-mask",
  "tags": ["bert", "transformer", "nlp", "en", "license:apache-2.0"],
  "card": "---\nlicense: apache-2.0\n---\n\n# BERT base model...",
  "base_model": "bert-base-uncased",
  "siblings": [
    {"rfilename": "config.json"},
    {"rfilename": "pytorch_model.bin"}
  ]
}
```

### Key Fields

| HuggingFace Field | Type | Description |
|-------------------|------|-------------|
| `modelId` | string | Unique model identifier |
| `author` | string | Model author/organization |
| `createdAt` | string (ISO 8601) | Creation timestamp |
| `last_modified` | string (ISO 8601) | Last modification timestamp |
| `downloads` | integer | Download count |
| `likes` | integer | Like count |
| `library_name` | string | Library (e.g., "transformers") |
| `pipeline_tag` | string | Primary ML task |
| `tags` | array of strings | Tags/keywords |
| `card` | string (Markdown) | Model card content |
| `base_model` | string | Base model identifier |
| `siblings` | array of objects | Model files |

### HuggingFace → FAIR4ML Mapping

| HuggingFace Field | FAIR4ML Property | Transformation |
|-------------------|------------------|----------------|
| `modelId` | `identifier` | `["https://huggingface.co/{modelId}"]` |
| `modelId` | `name` | Direct copy |
| `modelId` | `url` | `"https://huggingface.co/{modelId}"` |
| `author` | `author` | Direct copy |
| `author` | `sharedBy` | Direct copy (if same) |
| `createdAt` | `dateCreated` | Parse ISO 8601 → datetime |
| `last_modified` | `dateModified` | Parse ISO 8601 → datetime |
| `card` | `description` | Extract from Markdown |
| `tags` | `keywords` | Filter out language codes and licenses |
| `tags` | `inLanguage` | Extract language codes (e.g., "en", "de") |
| `tags` | `license` | Extract from "license:xxx" tags |
| `pipeline_tag` | `mlTask` | `[pipeline_tag]` |
| `library_name` | `modelCategory` | Infer from library (e.g., "transformers" → "transformer") |
| `base_model` | `fineTunedFrom` | `["https://huggingface.co/{base_model}"]` |
| `downloads`, `likes` | `metrics` | `{"downloads": ..., "likes": ...}` |

### Example Transformation

**Input (HuggingFace):**
```json
{
  "modelId": "bert-base-uncased",
  "author": "google",
  "createdAt": "2020-01-01T00:00:00Z",
  "pipeline_tag": "fill-mask",
  "tags": ["bert", "transformer", "nlp", "en", "license:apache-2.0"],
  "downloads": 1000000
}
```

**Output (FAIR4ML):**
```json
{
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "sharedBy": "google",
  "dateCreated": "2020-01-01T00:00:00Z",
  "mlTask": ["fill-mask"],
  "keywords": ["bert", "transformer", "nlp"],
  "inLanguage": ["en"],
  "license": "apache-2.0",
  "metrics": {
    "downloads": 1000000
  }
}
```

---

## OpenML Raw Schema

### Data Structure

OpenML uses a **wrapped metadata format** where each field is wrapped with extraction metadata:

```json
{
  "run_id": [
    {
      "data": 12345,
      "extraction_method": "openml_python_package",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ],
  "flow_id": [
    {
      "data": 6789,
      "extraction_method": "openml_python_package",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ],
  "dataset_id": [
    {
      "data": 61,
      "extraction_method": "openml_python_package",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ],
  "task_id": [
    {
      "data": 1,
      "extraction_method": "openml_python_package",
      "confidence": 1.0,
      "extraction_time": "2025-01-15T12:00:00Z"
    }
  ]
}
```

### Key Fields

| OpenML Field | Type | Description |
|--------------|------|-------------|
| `run_id` | integer | Unique run identifier |
| `flow_id` | integer | Flow (model/algorithm) identifier |
| `dataset_id` | integer | Dataset identifier |
| `task_id` | integer | Task identifier |
| `setup_string` | string | Configuration string |
| `upload_time` | string (ISO 8601) | Upload timestamp |

### Flow (Model) Schema

```json
{
  "flow_id": [{"data": 6789, ...}],
  "name": [{"data": "Random Forest", ...}],
  "version": [{"data": "1.0", ...}],
  "uploader": [{"data": 123, ...}],
  "upload_date": [{"data": "2020-01-01T00:00:00Z", ...}]
}
```

### Dataset Schema

```json
{
  "dataset_id": [{"data": 61, ...}],
  "name": [{"data": "iris", ...}],
  "version": [{"data": "1", ...}],
  "uploader": [{"data": 123, ...}],
  "upload_date": [{"data": "2020-01-01T00:00:00Z", ...}]
}
```

### OpenML → FAIR4ML Mapping

**For Flows (Models):**

| OpenML Field | FAIR4ML Property | Transformation |
|--------------|------------------|----------------|
| `flow_id` | `identifier` | `["https://www.openml.org/f/{flow_id}"]` |
| `name` | `name` | Extract from wrapped format |
| `flow_id` | `url` | `"https://www.openml.org/f/{flow_id}"` |
| `uploader` | `author` | Resolve user ID to name |
| `upload_date` | `datePublished` | Parse ISO 8601 → datetime |
| `version` | `description` | Include in description |

**For Runs:**

Runs are not directly mapped to FAIR4ML models. Instead:
- Runs link flows (models) to datasets and tasks
- Relationships are created in the Load stage
- Performance metrics from runs are stored separately

### Example Transformation

**Input (OpenML Flow):**
```json
{
  "flow_id": [{"data": 6789, ...}],
  "name": [{"data": "Random Forest", ...}],
  "upload_date": [{"data": "2020-01-01T00:00:00Z", ...}]
}
```

**Output (FAIR4ML):**
```json
{
  "identifier": ["https://www.openml.org/f/6789"],
  "name": "Random Forest",
  "url": "https://www.openml.org/f/6789",
  "datePublished": "2020-01-01T00:00:00Z"
}
```

---

## AI4Life Raw Schema

### Data Structure

AI4Life models are stored as JSON objects from the Hypha platform:

```json
{
  "id": "bioimage-io-model-xyz",
  "name": "Cell Segmentation Model",
  "description": "Deep learning model for cell segmentation",
  "author": "John Doe",
  "created": "2023-01-01T00:00:00Z",
  "updated": "2023-06-15T10:30:00Z",
  "tags": ["segmentation", "bioimaging", "cells"],
  "license": "MIT",
  "parent_id": "bioimage-io/bioimage.io"
}
```

### Key Fields

| AI4Life Field | Type | Description |
|---------------|------|-------------|
| `id` | string | Unique model identifier |
| `name` | string | Model name |
| `description` | string | Model description |
| `author` | string | Model author |
| `created` | string (ISO 8601) | Creation timestamp |
| `updated` | string (ISO 8601) | Update timestamp |
| `tags` | array of strings | Tags/keywords |
| `license` | string | License identifier |
| `parent_id` | string | Parent collection ID |

### AI4Life → FAIR4ML Mapping

| AI4Life Field | FAIR4ML Property | Transformation |
|---------------|------------------|----------------|
| `id` | `identifier` | `["https://hypha.aicell.io/{id}"]` |
| `name` | `name` | Direct copy |
| `id` | `url` | `"https://hypha.aicell.io/{id}"` |
| `author` | `author` | Direct copy |
| `created` | `dateCreated` | Parse ISO 8601 → datetime |
| `updated` | `dateModified` | Parse ISO 8601 → datetime |
| `description` | `description` | Direct copy |
| `tags` | `keywords` | Direct copy |
| `license` | `license` | Direct copy |

### Example Transformation

**Input (AI4Life):**
```json
{
  "id": "bioimage-io-model-xyz",
  "name": "Cell Segmentation Model",
  "description": "Deep learning model for cell segmentation",
  "author": "John Doe",
  "created": "2023-01-01T00:00:00Z",
  "tags": ["segmentation", "bioimaging"],
  "license": "MIT"
}
```

**Output (FAIR4ML):**
```json
{
  "identifier": ["https://hypha.aicell.io/bioimage-io-model-xyz"],
  "name": "Cell Segmentation Model",
  "url": "https://hypha.aicell.io/bioimage-io-model-xyz",
  "description": "Deep learning model for cell segmentation",
  "author": "John Doe",
  "dateCreated": "2023-01-01T00:00:00Z",
  "keywords": ["segmentation", "bioimaging"],
  "license": "MIT"
}
```

---

## Common Transformation Patterns

### Pattern 1: Direct Mapping

**Simple field copy:**
```python
fair4ml["author"] = raw["author"]
```

### Pattern 2: URL Construction

**Build identifier/URL from ID:**
```python
model_id = raw["modelId"]
fair4ml["identifier"] = [f"https://huggingface.co/{model_id}"]
fair4ml["url"] = f"https://huggingface.co/{model_id}"
```

### Pattern 3: Array Conversion

**Single value → array:**
```python
# HuggingFace: "fill-mask" (string)
# FAIR4ML: ["fill-mask"] (array)
fair4ml["mlTask"] = [raw["pipeline_tag"]]
```

### Pattern 4: Field Extraction

**Extract from complex field:**
```python
# Extract license from tags
tags = raw["tags"]
license_tags = [t for t in tags if t.startswith("license:")]
if license_tags:
    fair4ml["license"] = license_tags[0].replace("license:", "")
```

### Pattern 5: Wrapped Metadata Unwrapping

**OpenML format:**
```python
# OpenML: [{"data": value, ...}]
# Extract value
wrapped = raw["name"]
if wrapped and len(wrapped) > 0:
    fair4ml["name"] = wrapped[0]["data"]
```

### Pattern 6: Date Parsing

**ISO 8601 → datetime:**
```python
from datetime import datetime

date_str = raw["createdAt"]
fair4ml["dateCreated"] = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
```

### Pattern 7: Field Combination

**Combine multiple fields:**
```python
# Combine tags and library_name into keywords
keywords = raw.get("tags", [])
if raw.get("library_name"):
    keywords.append(raw["library_name"])
fair4ml["keywords"] = keywords
```

---

## Schema Evolution

### Handling Missing Fields

**Strategy:**
- Optional fields can be omitted
- Required fields must have defaults or be inferred
- Log missing data for review

**Example:**
```python
# Optional field
fair4ml["description"] = raw.get("card") or raw.get("description") or None

# Required field with default
fair4ml["name"] = raw.get("modelId") or raw.get("name") or "Unknown Model"
```

### Handling Type Mismatches

**Strategy:**
- Convert types when possible
- Validate after conversion
- Log conversion errors

**Example:**
```python
# String → List
if isinstance(raw["mlTask"], str):
    fair4ml["mlTask"] = [raw["mlTask"]]
elif isinstance(raw["mlTask"], list):
    fair4ml["mlTask"] = raw["mlTask"]
```

---

## Key Takeaways

1. **Each source** has its own schema format
2. **Mapping rules** convert source fields to FAIR4ML
3. **Transformation patterns** handle common conversions
4. **Schema evolution** requires handling missing/unknown fields
5. **Validation** ensures data quality after transformation

---

## Next Steps

- See [FAIR4ML Schema Reference](fair4ml.md) - Complete FAIR4ML property reference
- Explore [Schema Structure](structure.md) - Pydantic implementation details
- Check [Transformers](../transformers/overview.md) - How transformation works
- Review [HuggingFace Transformation](../transformers/huggingface.md) - Detailed HF mapping
