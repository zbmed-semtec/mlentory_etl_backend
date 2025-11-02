# HuggingFace → FAIR4ML Transformation Implementation

## Overview

This document describes the implementation of the HuggingFace to FAIR4ML MLModel transformation pipeline, completed on October 31, 2025.

## Architecture

### Data Flow

```
Raw HF Models (JSON)
    ↓
hf_add_ancestor_models asset (extraction)
    ↓
hf_normalized_run_folder asset (create output folder)
    ↓
hf_models_normalized asset (transform & validate)
    ↓
FAIR4ML MLModels (JSON)
    /data/normalized/hf/<timestamp_runid>/mlmodels.json
```

### File Structure

```
schemas/fair4ml/
├── __init__.py
└── mlmodel.py              # Pydantic FAIR4ML MLModel schema

transformers/hf/
├── __init__.py
└── mlmodel.py              # HF → FAIR4ML mapping functions

etl/assets/
├── hf_extraction.py        # Existing extraction assets
└── hf_transformation.py    # NEW: Transformation assets

tests/
└── test_hf_transformation.py   # Unit tests

docs/
└── hf_transformation_implementation.md  # This file
```

## Implemented Components

### 1. Pydantic Schema (`schemas/fair4ml/mlmodel.py`)

Defines the FAIR4ML MLModel structure with:

- **Core fields** (schema.org): identifier, name, url, author, dates, description, keywords, license
- **ML-specific fields** (fair4ml): mlTask, modelCategory, fineTunedFrom, usageInstructions, etc.
- **Ethics & Risk fields**: modelRisksBiasLimitations, ethicalSocial, legal
- **Dataset fields**: trainedOn, testedOn, validatedOn, evaluatedOn
- **Additional URLs**: discussionUrl, archivedAt, readme, issueTracker
- **Technical**: memoryRequirements, hasCO2eEmissions
- **Extensions**: metrics (downloads, likes), extraction_metadata (provenance tracking)

All fields use FAIR4ML local property names (without namespace prefixes) to facilitate future JSON-LD conversion.

### 2. Mapping Functions (`transformers/hf/mlmodel.py`)

#### `map_basic_properties(raw_model: Dict) -> Dict`

Maps fundamental HF fields to FAIR4ML:

| HF Field | FAIR4ML Field | Transformation |
|----------|---------------|----------------|
| `modelId` | `identifier` | Convert to HF URL |
| `modelId` | `name` | Extract last component after `/` |
| `modelId` | `url` | Generate HF model URL |
| `author` | `author`, `sharedBy` | Direct mapping |
| `createdAt` | `dateCreated`, `datePublished` | Parse ISO datetime |
| `last_modified` | `dateModified` | Parse ISO datetime |
| `card` | `description` | Strip YAML frontmatter |
| `modelId` | `discussionUrl` | Generate `/discussions` URL |
| `modelId` | `readme` | Generate `/blob/main/README.md` URL |
| `modelId` | `issueTracker`, `archivedAt` | Generate HF URLs |

**Extraction Metadata**: Each field includes provenance tracking:
- `extraction_method`: How the field was derived
- `confidence`: Reliability score (0.0-1.0)
- `source_field`: Original HF field name
- `notes`: Additional context

#### `normalize_hf_model(raw_model: Dict) -> MLModel`

Main orchestration function:
1. Calls `map_basic_properties()`
2. Adds platform metrics (downloads, likes)
3. Validates with Pydantic
4. Returns MLModel instance

**TODO**: Additional mapping functions to implement:
- `map_keywords_and_language()` - tags → keywords, inLanguage
- `map_task_and_category()` - pipeline_tag → mlTask, modelCategory
- `map_license()` - license extraction from tags/frontmatter
- `map_lineage()` - base_model tags → fineTunedFrom
- `map_code_and_usage()` - extract code snippets and usage docs
- `map_datasets()` - identify trainedOn, evaluatedOn from card
- `map_ethics_and_risks()` - extract limitations, biases sections

### 3. Dagster Assets (`etl/assets/hf_transformation.py`)

#### `hf_normalized_run_folder`
- **Dependencies**: `hf_add_ancestor_models`
- **Purpose**: Create output directory matching raw run folder structure
- **Output**: `/data/normalized/hf/<timestamp_runid>/`

#### `hf_models_normalized`
- **Dependencies**: `hf_add_ancestor_models`, `hf_normalized_run_folder`
- **Purpose**: Transform and validate all models
- **Process**:
  1. Load raw JSON from extraction
  2. Transform each model with `normalize_hf_model()`
  3. Validate with Pydantic
  4. Serialize to JSON
  5. Write `mlmodels.json` + optional `transformation_errors.json`
- **Error Handling**: Captures validation errors without stopping pipeline

### 4. Tests (`tests/test_hf_transformation.py`)

Unit tests covering:
- Helper functions (`_extract_model_name`, `_strip_frontmatter`, `_parse_datetime`)
- `map_basic_properties()` with minimal and full data
- `normalize_hf_model()` end-to-end
- JSON serialization
- Integration test with actual sample file

## Output Format

### Example MLModel JSON

```json
{
  "identifier": "https://huggingface.co/bert-base-uncased",
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "sharedBy": "google",
  "dateCreated": "2020-01-01T00:00:00Z",
  "dateModified": "2020-06-15T10:30:00Z",
  "datePublished": "2020-01-01T00:00:00Z",
  "description": "# BERT base model (uncased)...",
  "keywords": ["bert", "transformer", "nlp"],
  "inLanguage": ["en"],
  "license": "apache-2.0",
  "mlTask": "fill-mask",
  "modelCategory": ["transformer", "bert"],
  "discussionUrl": "https://huggingface.co/bert-base-uncased/discussions",
  "readme": "https://huggingface.co/bert-base-uncased/blob/main/README.md",
  "metrics": {
    "downloads": 1000000,
    "likes": 500
  },
  "extraction_metadata": {
    "identifier": {
      "extraction_method": "Parsed_from_HF_dataset",
      "confidence": 1.0,
      "source_field": "modelId",
      "notes": "Converted to HuggingFace URL format"
    }
  }
}
```

## Usage

### Running the Pipeline

```bash
# Via Dagster UI (recommended)
# 1. Start Dagster: dagster dev
# 2. Navigate to Assets
# 3. Materialize: hf_models_normalized

# Via CLI
dagster asset materialize -m etl.repository -a hf_models_normalized
```

### Programmatic Usage

```python
from transformers.hf.mlmodel import normalize_hf_model

raw_model = {
    "modelId": "bert-base-uncased",
    "author": "google",
    "createdAt": "2020-01-01T00:00:00Z",
    "downloads": 1000000
}

mlmodel = normalize_hf_model(raw_model)
print(mlmodel.model_dump_json(indent=2))
```

### Running Tests

```bash
pytest tests/test_hf_transformation.py -v
```

## Configuration

No additional configuration required. The pipeline:
- Reads from: `/data/raw/hf/<timestamp_runid>/hf_models_with_ancestors.json`
- Writes to: `/data/normalized/hf/<timestamp_runid>/mlmodels.json`

## Next Steps

### Phase 2: Additional Property Mappings

1. **Keywords & Language** (`map_keywords_and_language`)
   - Parse `tags` array → `keywords`
   - Extract language codes (e.g., `en`, `tr`) → `inLanguage`

2. **Task & Category** (`map_task_and_category`)
   - `pipeline_tag` → `mlTask`
   - Infer `modelCategory` from `library_name` and tags

3. **License** (`map_license`)
   - Extract from `tags` (e.g., `license:mit`)
   - Parse frontmatter `license` field
   - Populate `legal` if non-standard

4. **Lineage** (`map_lineage`)
   - Extract `base_model:*` tags → `fineTunedFrom`

5. **Code & Usage** (`map_code_and_usage`)
   - Extract first code block from card → `codeSampleSnippet`
   - Parse "Quick start" / "Usage" sections → `usageInstructions`

6. **Datasets** (`map_datasets`)
   - Parse frontmatter `datasets` field
   - Extract from card (e.g., "trained on X")
   - Map to `trainedOn`, `evaluatedOn`, etc.

7. **Ethics & Risks** (`map_ethics_and_risks`)
   - Extract "Limitations" section → `modelRisksBiasLimitations`
   - Extract "Ethical Considerations" → `ethicalSocial`

### Phase 3: JSON-LD Conversion

Add optional JSON-LD output format with proper `@context` and `@type` annotations.

### Phase 4: Memory Requirements

Implement `get_repository_weight_HF()` equivalent to fetch model size from HF API.

## References

- **FAIR4ML 0.1.0 Spec**: https://rda-fair4ml.github.io/FAIR4ML-schema/release/0.1.0/index.html
- **Schema.org**: https://schema.org/
- **CodeMeta**: https://codemeta.github.io/
- **HuggingFace Model Hub API**: https://huggingface.co/docs/hub/api

## Changelog

### 2025-10-31 - Initial Implementation
- ✅ Created Pydantic FAIR4ML MLModel schema
- ✅ Implemented `map_basic_properties()` for core fields
- ✅ Implemented `normalize_hf_model()` orchestration
- ✅ Created Dagster transformation assets
- ✅ Added unit tests
- ✅ Integrated into Dagster repository
- ⏳ Additional property mappings (Phase 2)

