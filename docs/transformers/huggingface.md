# HuggingFace Transformation

Complete guide to transforming HuggingFace model metadata into FAIR4ML format.

---

## Overview

The HuggingFace transformer converts raw HuggingFace model metadata into standardized FAIR4ML MLModel objects. It uses a **modular architecture** where different property groups are extracted in parallel for efficiency.

### Transformation Flow

```
Raw HF Models JSON
    ↓
Modular Property Extraction (Parallel)
    ├─→ Basic Properties
    ├─→ Keywords & Language
    ├─→ Task & Category
    ├─→ License
    ├─→ Lineage
    ├─→ Code & Usage
    ├─→ Datasets
    └─→ Ethics & Risks
    ↓
Merge All Partial Schemas
    ↓
Validate with Pydantic
    ↓
FAIR4ML MLModels JSON
```

---

## Modular Architecture

### Why Modular?

**Benefits:**
- **Parallel Processing:** Extract properties simultaneously
- **Error Isolation:** One failure doesn't stop others
- **Easy to Extend:** Add new property groups easily
- **Testability:** Test each property group independently
- **Maintainability:** Clear separation of concerns

### Property Groups

Each property group is processed independently:

#### 1. Basic Properties ✅

**What's extracted:**
- Core identification (identifier, name, url)
- Authorship (author, sharedBy)
- Temporal information (dateCreated, dateModified, datePublished)
- Description (from model card)

**Mapping:**
```python
# HuggingFace → FAIR4ML
raw["modelId"] → fair4ml["identifier"]
raw["author"] → fair4ml["author"]
raw["createdAt"] → fair4ml["dateCreated"]
raw["card"] → fair4ml["description"]
```

**Status:** ✅ Implemented

#### 2. Keywords & Language ⏳

**What's extracted:**
- Keywords/tags
- Natural languages (inLanguage)

**Mapping:**
```python
# HuggingFace → FAIR4ML
raw["tags"] → fair4ml["keywords"]
raw["tags"] (language codes) → fair4ml["inLanguage"]
```

**Status:** ⏳ TODO

#### 3. Task & Category ⏳

**What's extracted:**
- ML tasks (mlTask)
- Model category/architecture (modelCategory)

**Mapping:**
```python
# HuggingFace → FAIR4ML
raw["pipeline_tag"] → fair4ml["mlTask"]
raw["library_name"] + raw["tags"] → fair4ml["modelCategory"]
```

**Status:** ⏳ TODO

#### 4. License ⏳

**What's extracted:**
- License identifier
- Legal terms

**Mapping:**
```python
# HuggingFace → FAIR4ML
raw["tags"] (license:*) → fair4ml["license"]
raw["card"] (frontmatter) → fair4ml["license"]
```

**Status:** ⏳ TODO

#### 5. Lineage ⏳

**What's extracted:**
- Base models (fineTunedFrom)
- Model dependencies

**Mapping:**
```python
# HuggingFace → FAIR4ML
raw["tags"] (base_model:*) → fair4ml["fineTunedFrom"]
```

**Status:** ⏳ TODO

#### 6. Code & Usage ⏳

**What's extracted:**
- Code snippets
- Usage instructions

**Mapping:**
```python
# HuggingFace → FAIR4ML
raw["card"] (code blocks) → fair4ml["codeSampleSnippet"]
raw["card"] (usage sections) → fair4ml["usageInstructions"]
```

**Status:** ⏳ TODO

#### 7. Datasets ⏳

**What's extracted:**
- Training datasets (trainedOn)
- Evaluation datasets (evaluatedOn)
- Performance metrics

**Mapping:**
```python
# HuggingFace → FAIR4ML
raw["card"] (dataset mentions) → fair4ml["trainedOn"]
raw["card"] (evaluation mentions) → fair4ml["evaluatedOn"]
```

**Status:** ⏳ TODO

#### 8. Ethics & Risks ⏳

**What's extracted:**
- Limitations
- Biases
- Ethical considerations

**Mapping:**
```python
# HuggingFace → FAIR4ML
raw["card"] (limitations section) → fair4ml["modelRisksBiasLimitations"]
raw["card"] (ethical section) → fair4ml["ethicalSocial"]
```

**Status:** ⏳ TODO

---

## Transformation Process

### Step 1: Read Raw Data

**Input:**
- `/data/raw/hf/<timestamp>_<uuid>/hf_models_with_ancestors.json`

**What happens:**
- Load JSON file
- Parse HuggingFace model structure
- Handle missing or malformed data

### Step 2: Extract Properties (Parallel)

**What happens:**
- Each property group extracts its fields independently
- Creates partial schema files
- Runs in parallel (Dagster handles this)

**Output:**
- `/data/normalized/hf/<timestamp>_<uuid>/partial_basic_properties.json`
- `/data/normalized/hf/<timestamp>_<uuid>/partial_keywords_language.json`
- `/data/normalized/hf/<timestamp>_<uuid>/partial_task_category.json`
- ... (one per property group)

### Step 3: Merge Partial Schemas

**What happens:**
- Load all partial schema files
- Merge by model index (`_index` field)
- Combine extraction metadata
- Add platform metrics (downloads, likes)

**Example:**
```python
merged = {
    **basic_props[idx],
    **keywords_lang[idx],
    **task_cat[idx],
    # ... etc
}
```

### Step 4: Validate

**What happens:**
- Validate merged data against FAIR4ML Pydantic schema
- Check required fields exist
- Verify data types are correct
- Ensure values are valid

**Error handling:**
- Invalid models logged to error file
- Valid models continue processing
- Partial success allowed

### Step 5: Save Normalized Data

**Output:**
- `/data/normalized/hf/<timestamp>_<uuid>/mlmodels.json`
- `/data/normalized/hf/<timestamp>_<uuid>/transformation_errors.json` (if any)

---

## Mapping Functions

### Basic Properties Mapping

**Function:** `map_basic_properties(raw_model: Dict) -> Dict`

**Mappings:**

| HuggingFace Field | FAIR4ML Field | Transformation |
|-------------------|---------------|----------------|
| `modelId` | `identifier` | Convert to `https://huggingface.co/{modelId}` |
| `modelId` | `name` | Extract last component after `/` |
| `modelId` | `url` | Generate `https://huggingface.co/{modelId}` |
| `author` | `author` | Direct mapping |
| `author` | `sharedBy` | Same as author |
| `createdAt` | `dateCreated` | Parse ISO datetime |
| `createdAt` | `datePublished` | Same as dateCreated |
| `last_modified` | `dateModified` | Parse ISO datetime |
| `card` | `description` | Strip YAML frontmatter |
| `modelId` | `discussionUrl` | Generate `/discussions` URL |
| `modelId` | `readme` | Generate `/blob/main/README.md` URL |
| `modelId` | `issueTracker` | Generate `/issues` URL |
| `modelId` | `archivedAt` | Generate `/tree/main` URL |

**Example:**
```python
# Input
{
  "modelId": "bert-base-uncased",
  "author": "google",
  "createdAt": "2020-01-01T00:00:00Z"
}

# Output
{
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "sharedBy": "google",
  "dateCreated": "2020-01-01T00:00:00Z",
  "datePublished": "2020-01-01T00:00:00Z"
}
```

---

## Extraction Metadata

Each field includes provenance tracking:

```json
{
  "identifier": {
    "extraction_method": "Parsed_from_HF_dataset",
    "confidence": 1.0,
    "source_field": "modelId",
    "notes": "Converted to HuggingFace URL"
  }
}
```

**Fields:**
- `extraction_method`: How the field was derived
- `confidence`: Reliability score (0.0-1.0)
- `source_field`: Original HuggingFace field name
- `notes`: Additional context

**Benefits:**
- Track data provenance
- Debug transformation issues
- Assess data quality

---

## Dagster Assets

### Transformation Assets

**`hf_normalized_run_folder`**
- Creates unique run folder for normalized outputs
- Returns: Path to normalized run folder

**`hf_extract_basic_properties`** ✅
- Extracts basic properties from raw models
- Depends on: `hf_add_ancestor_models`
- Returns: Path to partial_basic_properties.json

**`hf_extract_keywords_language`** ⏳
- Extracts keywords and languages
- Depends on: `hf_add_ancestor_models`
- Returns: Path to partial_keywords_language.json

**`hf_extract_task_category`** ⏳
- Extracts ML tasks and model categories
- Depends on: `hf_add_ancestor_models`
- Returns: Path to partial_task_category.json

**`hf_models_normalized`**
- Merges all partial schemas
- Validates with Pydantic
- Depends on: All property extraction assets
- Returns: Path to mlmodels.json

### Asset Dependency Graph

```
hf_add_ancestor_models (extraction)
    ↓
hf_normalized_run_folder
    ↓
    ├─→ hf_extract_basic_properties (parallel)
    ├─→ hf_extract_keywords_language (parallel)
    ├─→ hf_extract_task_category (parallel)
    ├─→ hf_extract_license (parallel)
    ├─→ hf_extract_lineage (parallel)
    ├─→ hf_extract_code_usage (parallel)
    ├─→ hf_extract_datasets (parallel)
    └─→ hf_extract_ethics_risks (parallel)
        ↓
    hf_models_normalized (merge & validate)
```

---

## Output Format

### Normalized Models JSON

```json
[
  {
    "identifier": ["https://huggingface.co/bert-base-uncased"],
    "name": "bert-base-uncased",
    "url": "https://huggingface.co/bert-base-uncased",
    "author": "google",
    "sharedBy": "google",
    "dateCreated": "2020-01-01T00:00:00Z",
    "dateModified": "2020-06-15T10:30:00Z",
    "datePublished": "2020-01-01T00:00:00Z",
    "description": "# BERT base model...",
    "keywords": ["bert", "transformer", "nlp"],
    "inLanguage": ["en"],
    "mlTask": ["fill-mask"],
    "modelCategory": ["transformer", "bert"],
    "license": "apache-2.0",
    "fineTunedFrom": [],
    "metrics": {
      "downloads": 1000000,
      "likes": 500
    },
    "extraction_metadata": {
      "identifier": {
        "extraction_method": "Parsed_from_HF_dataset",
        "confidence": 1.0,
        "source_field": "modelId"
      },
      ...
    }
  }
]
```

### Error File

If validation fails:

```json
{
  "model_id": "invalid-model",
  "errors": [
    {
      "field": "dateCreated",
      "error": "Invalid date format",
      "value": "not-a-date"
    }
  ]
}
```

---

## Usage Examples

### Via Dagster UI

1. Open Dagster UI (http://localhost:3000)
2. Navigate to Assets tab
3. Find `hf_models_normalized` asset
4. Click "Materialize"
5. Watch progress in real-time

### Via Command Line

**Transform models:**
```bash
dagster asset materialize -m etl.repository -a hf_models_normalized
```

**Transform with dependencies:**
```bash
# This automatically runs all property extraction assets
dagster asset materialize -m etl.repository -a hf_models_normalized+
```

**Transform all HF assets:**
```bash
dagster asset materialize -m etl.repository --select "hf*"
```

### Programmatic Usage

**Standalone (without Dagster):**
```python
from etl_transformers.hf import normalize_hf_model

# Transform single model
raw_model = {
    "modelId": "bert-base-uncased",
    "author": "google",
    ...
}

normalized = normalize_hf_model(raw_model)
# Returns: MLModel instance (validated)
```

---

## Performance

### Parallel Execution

**With parallel property extraction:**
- **Time:** ~O(n) where n = number of models
- **Speedup:** Up to 8x (number of property groups)
- **Memory:** O(n × p) where p = property groups

### Sequential Execution

**Without parallelization:**
- **Time:** O(n × p)
- **Memory:** O(n × p)

**Recommendation:** Use Dagster for automatic parallelization.

---

## Troubleshooting

### Validation Errors

**Problem:** Some models fail validation

**Solutions:**
- Check error file for details
- Review raw data for missing fields
- Verify data types are correct
- Partial failures are OK (valid models continue)

### Missing Properties

**Problem:** Some properties not extracted

**Solutions:**
- Check if property extraction asset exists
- Verify raw data contains source fields
- Review extraction logic
- Some properties may be optional

### Performance Issues

**Problem:** Transformation is slow

**Solutions:**
- Ensure parallel execution (Dagster)
- Reduce number of models
- Check system resources (CPU, memory)
- Review property extraction logic

---

## Key Takeaways

1. **Modular architecture** enables parallel processing
2. **Property groups** are extracted independently
3. **Partial schemas** are merged into final FAIR4ML models
4. **Pydantic validation** ensures data quality
5. **Extraction metadata** tracks data provenance
6. **Error handling** allows partial success

---

## Next Steps

- See [Transformation Architecture](architecture.md) - Detailed architecture guide
- Check [Adding a Transformer](adding-transformer.md) - How to add new transformers
- Explore [Loaders](../loaders/overview.md) - How normalized data is loaded
- Review [FAIR4ML Schema](../concepts/fair4ml-schema.md) - Schema reference

---

## Resources

- **FAIR4ML Schema:** [https://github.com/RDA-FAIR4ML/FAIR4ML-schema](https://github.com/RDA-FAIR4ML/FAIR4ML-schema)
- **Pydantic Documentation:** [https://docs.pydantic.dev/](https://docs.pydantic.dev/)
- **HuggingFace Hub:** [https://huggingface.co/](https://huggingface.co/)
