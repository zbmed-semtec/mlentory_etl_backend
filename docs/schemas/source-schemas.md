# Source Schemas
## Understanding Platform-Specific Data Formats

This comprehensive guide explains how different ML model platforms structure their data and how we transform that data into the standardized FAIR4ML format. Understanding source schemas is crucial for debugging transformation issues, extending support to new platforms, and understanding why certain mappings exist.

---

## 🎯 The Challenge of Multiple Formats

We are building a system that needs to work with ML models from different platforms. HuggingFace uses `modelId` to identify models, OpenML uses `flow_id`, and AI4Life uses `id`. Each platform has different field names, different data structures, and different conventions. Some platforms store dates as ISO 8601 strings, others as Unix timestamps. Some use arrays for tags, others use comma-separated strings.

This diversity is the fundamental challenge that source schemas address. By understanding each platform's format and how it maps to FAIR4ML, we can build robust transformation logic that handles these differences gracefully.
---

## 🤗 HuggingFace: The Most Comprehensive Source

HuggingFace Hub is the largest repository of ML models, with millions of models covering every imaginable task. Their data format is relatively rich, providing extensive metadata about models, but it's structured in a HuggingFace-specific way that requires careful transformation.

### 📊 Understanding HuggingFace's Data Structure

HuggingFace stores model metadata as JSON objects with a flat structure. Each model has a unique `modelId` that serves as its primary identifier. The metadata includes everything from basic information (name, author) to detailed model cards written in Markdown/html files.

Here's what a typical HuggingFace model looks like:

```json
{
  "modelId": "google-bert/bert-base-uncased",
  "author": "google-bert",
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

### 🔑 Key Fields

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

### 🔄 HuggingFace → FAIR4ML Mapping

**Implemented Mappings:**

| HuggingFace Field | FAIR4ML Property | Transformation | Status |
|-------------------|------------------|----------------|--------|
| `modelId` | `identifier` | `["https://huggingface.co/{modelId}", mlentory_id]` | ✅ Implemented |
| `modelId` | `name` | Extract name part (last component after "/") | ✅ Implemented |
| `modelId` | `url` | `"https://huggingface.co/{modelId}"` | ✅ Implemented |
| `author` | `author` | Direct copy | ✅ Implemented |
| `author` | `sharedBy` | Direct copy (assumed same as author) | ✅ Implemented |
| `createdAt` | `dateCreated` | Parse ISO 8601 → datetime | ✅ Implemented |
| `last_modified` | `dateModified` | Parse ISO 8601 → datetime | ✅ Implemented |
| `createdAt` | `datePublished` | Parse ISO 8601 → datetime (uses createdAt) | ✅ Implemented |
| `card` | `description` | Extract from Markdown (frontmatter removed) | ✅ Implemented |
| `modelId` | `discussionUrl` | `"https://huggingface.co/{modelId}/discussions"` | ✅ Implemented |
| `modelId` | `readme` | `"https://huggingface.co/{modelId}/blob/main/README.md"` | ✅ Implemented |
| `downloads`, `likes` | `metrics` | `{"downloads": ..., "likes": ...}` | ✅ Implemented |

**Planned Mappings (Not Yet Implemented):**

| HuggingFace Field | FAIR4ML Property | Transformation | Status |
|-------------------|------------------|----------------|--------|
| `tags` | `keywords` | Filter out language codes and licenses | ⏳ TODO |
| `tags` | `inLanguage` | Extract language codes (e.g., "en", "de") | ⏳ TODO |
| `tags` | `license` | Extract from "license:xxx" tags | ⏳ TODO |
| `pipeline_tag` | `mlTask` | `[pipeline_tag]` | ⏳ TODO |
| `library_name` | `modelCategory` | Infer from library (e.g., "transformers" → "transformer") | ⏳ TODO |
| `base_model` | `fineTunedFrom` | `["https://huggingface.co/{base_model}"]` | ⏳ TODO |

### 💡 Example Transformation

**Input (HuggingFace):**
```json
{
  "modelId": "google-bert/bert-base-uncased",
  "author": "google-bert",
  "createdAt": "2020-01-01T00:00:00Z",
  "pipeline_tag": "fill-mask",
  "tags": ["bert", "transformer", "nlp", "en", "license:apache-2.0"],
  "downloads": 1000000
}
```

**Output (FAIR4ML):**
```json
{
  "identifier": [
    "https://huggingface.co/google-bert/bert-base-uncased",
    "mlentory:model:abc123..."
  ],
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/google-bert/bert-base-uncased",
  "author": "google-bert",
  "sharedBy": "google-bert",
  "dateCreated": "2020-01-01T00:00:00Z",
  "dateModified": null,
  "datePublished": "2020-01-01T00:00:00Z",
  "description": null,
  "discussionUrl": "https://huggingface.co/google-bert/bert-base-uncased/discussions",
  "readme": "https://huggingface.co/google-bert/bert-base-uncased/blob/main/README.md",
  "metrics": {
    "downloads": 1000000,
    "likes": 0
  }
}
```

**Note:** Fields like `mlTask`, `keywords`, `inLanguage`, `license`, `modelCategory`, and `fineTunedFrom` are not yet implemented in the transformation code. See the mapping table above for implementation status.

---

## 📊 OpenML Raw Schema

> **⚠️ Note:** OpenML transformation is not yet implemented. This section describes the expected raw data format and planned mappings.

### 📋 Data Structure

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

### 🔑 Key Fields

| OpenML Field | Type | Description |
|--------------|------|-------------|
| `run_id` | integer | Unique run identifier |
| `flow_id` | integer | Flow (model/algorithm) identifier |
| `dataset_id` | integer | Dataset identifier |
| `task_id` | integer | Task identifier |
| `setup_string` | string | Configuration string |
| `upload_time` | string (ISO 8601) | Upload timestamp |

### 🔄 Flow (Model) Schema

```json
{
  "flow_id": [{"data": 6789, ...}],
  "name": [{"data": "Random Forest", ...}],
  "version": [{"data": "1.0", ...}],
  "uploader": [{"data": 123, ...}],
  "upload_date": [{"data": "2020-01-01T00:00:00Z", ...}]
}
```

### 📊 Dataset Schema

```json
{
  "dataset_id": [{"data": 61, ...}],
  "name": [{"data": "iris", ...}],
  "version": [{"data": "1", ...}],
  "uploader": [{"data": 123, ...}],
  "upload_date": [{"data": "2020-01-01T00:00:00Z", ...}]
}
```

### 🔄 OpenML → FAIR4ML Mapping (Planned)

**For Flows (Models):**

| OpenML Field | FAIR4ML Property | Transformation | Status |
|--------------|------------------|----------------|--------|
| `flow_id` | `identifier` | `["https://www.openml.org/f/{flow_id}"]` | ⏳ TODO |
| `name` | `name` | Extract from wrapped format | ⏳ TODO |
| `flow_id` | `url` | `"https://www.openml.org/f/{flow_id}"` | ⏳ TODO |
| `uploader` | `author` | Resolve user ID to name | ⏳ TODO |
| `upload_date` | `datePublished` | Parse ISO 8601 → datetime | ⏳ TODO |
| `version` | `description` | Include in description | ⏳ TODO |

**For Runs:**

Runs are not directly mapped to FAIR4ML models. Instead:
- Runs link flows (models) to datasets and tasks
- Relationships are created in the Load stage
- Performance metrics from runs are stored separately

### 💡 Example Transformation

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

## 🔬 AI4Life Raw Schema

> **⚠️ Note:** AI4Life transformation is not yet implemented. This section describes the expected raw data format and planned mappings.

### 📋 Data Structure

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

### 🔑 Key Fields

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

### 🔄 AI4Life → FAIR4ML Mapping (Planned)

| AI4Life Field | FAIR4ML Property | Transformation | Status |
|---------------|------------------|----------------|--------|
| `id` | `identifier` | `["https://hypha.aicell.io/{id}"]` | ⏳ TODO |
| `name` | `name` | Direct copy | ⏳ TODO |
| `id` | `url` | `"https://hypha.aicell.io/{id}"` | ⏳ TODO |
| `author` | `author` | Direct copy | ⏳ TODO |
| `created` | `dateCreated` | Parse ISO 8601 → datetime | ⏳ TODO |
| `updated` | `dateModified` | Parse ISO 8601 → datetime | ⏳ TODO |
| `description` | `description` | Direct copy | ⏳ TODO |
| `tags` | `keywords` | Direct copy | ⏳ TODO |
| `license` | `license` | Direct copy | ⏳ TODO |

### 💡 Example Transformation

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

## 🔧 Common Transformation Patterns

### 1️⃣ Pattern 1: Direct Mapping

**Simple field copy:**
```python
fair4ml["author"] = raw["author"]
```

### 2️⃣ Pattern 2: URL Construction

**Build identifier/URL from ID:**
```python
model_id = raw["modelId"]
mlentory_id = generate_mlentory_id(model_id)  # Generate unique ID
hf_url = f"https://huggingface.co/{model_id}"
fair4ml["identifier"] = [hf_url, mlentory_id]  # Both URL and mlentory_id
fair4ml["url"] = hf_url
```

### 3️⃣ Pattern 3: Name Extraction

**Extract model name from full model ID:**
```python
# HuggingFace: "google-bert/bert-base-uncased" (full ID)
# FAIR4ML: "bert-base-uncased" (name only)
model_id = raw["modelId"]
fair4ml["name"] = model_id.split("/")[-1] if "/" in model_id else model_id
```

### 4️⃣ Pattern 4: Array Conversion

**Single value → array:**
```python
# HuggingFace: "fill-mask" (string)
# FAIR4ML: ["fill-mask"] (array)
if raw.get("pipeline_tag"):
    fair4ml["mlTask"] = [raw["pipeline_tag"]]
```

**Note:** This pattern is planned but not yet implemented in the HuggingFace transformer.

### 5️⃣ Pattern 5: Field Extraction

**Extract from complex field:**
```python
# Extract license from tags
tags = raw.get("tags", [])
license_tags = [t for t in tags if t.startswith("license:")]
if license_tags:
    fair4ml["license"] = license_tags[0].replace("license:", "")
```

**Note:** This pattern is planned but not yet implemented in the HuggingFace transformer.

### 6️⃣ Pattern 6: Wrapped Metadata Unwrapping

**OpenML format:**
```python
# OpenML: [{"data": value, ...}]
# Extract value
wrapped = raw["name"]
if wrapped and len(wrapped) > 0:
    fair4ml["name"] = wrapped[0]["data"]
```

**Note:** This pattern is for OpenML transformation, which is not yet implemented.

### 7️⃣ Pattern 7: Date Parsing

**ISO 8601 → datetime:**
```python
from datetime import datetime

date_str = raw["createdAt"]
# Handle timezone: replace 'Z' with '+00:00' for fromisoformat
fair4ml["dateCreated"] = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
```

### 8️⃣ Pattern 8: Field Combination

**Combine multiple fields:**
```python
# Combine tags and library_name into keywords
keywords = raw.get("tags", [])
if raw.get("library_name"):
    keywords.append(raw["library_name"])
fair4ml["keywords"] = keywords
```

---

## 🔄 Schema Evolution

### ⚠️ Handling Missing Fields

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

### 🔧 Handling Type Mismatches

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

## 🎓 Key Takeaways

1. **Each source** has its own schema format
2. **Mapping rules** convert source fields to FAIR4ML
3. **Transformation patterns** handle common conversions
4. **Schema evolution** requires handling missing/unknown fields
5. **Validation** ensures data quality after transformation

---

## 🚀 Next Steps

- See [FAIR4ML Schema Reference](fair4ml.md) - Complete FAIR4ML property reference
- Explore [Schema Structure](structure.md) - Pydantic implementation details
- Check [Transformers](../transformers/overview.md) - How transformation works
- Review [HuggingFace Transformation](../transformers/huggingface.md) - Detailed HF mapping
