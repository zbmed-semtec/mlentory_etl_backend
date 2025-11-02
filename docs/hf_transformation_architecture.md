# HuggingFace Transformation Architecture

## Modular Property Extraction Pipeline

The HuggingFace → FAIR4ML transformation uses a **modular, parallel extraction pattern** where each property group is processed independently, then merged into final validated MLModel objects.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    HF Extraction Phase                          │
│                                                                 │
│  hf_add_ancestor_models                                        │
│  └─> /data/raw/hf/<timestamp>_<runid>/                       │
│       hf_models_with_ancestors.json                            │
└────────────┬────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────┐
│              HF Transformation Phase (Modular)                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────┐      │
│  │ hf_normalized_run_folder                            │      │
│  │ └─> /data/normalized/hf/<timestamp>_<runid>/      │      │
│  └─────────────────────────────────────────────────────┘      │
│                                                                 │
│  ┌──────────────────────── Property Extraction ────────────────┐ │
│  │                      (Parallel Assets)                     │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_basic_properties                         │  │ │
│  │  │ Maps: modelId, author, dates, card                  │  │ │
│  │  │ To: identifier, name, url, dates, description       │  │ │
│  │  │ Output: partial_basic_properties.json               │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_keywords_language (TODO)                 │  │ │
│  │  │ Maps: tags                                          │  │ │
│  │  │ To: keywords, inLanguage                            │  │ │
│  │  │ Output: partial_keywords_language.json              │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_task_category (TODO)                     │  │ │
│  │  │ Maps: pipeline_tag, library_name, tags              │  │ │
│  │  │ To: mlTask, modelCategory                           │  │ │
│  │  │ Output: partial_task_category.json                  │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_license (TODO)                           │  │ │
│  │  │ Maps: tags, card frontmatter                        │  │ │
│  │  │ To: license, legal                                  │  │ │
│  │  │ Output: partial_license.json                        │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_lineage (TODO)                           │  │ │
│  │  │ Maps: tags (base_model:*)                           │  │ │
│  │  │ To: fineTunedFrom                                   │  │ │
│  │  │ Output: partial_lineage.json                        │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_code_usage (TODO)                        │  │ │
│  │  │ Maps: card (code blocks, usage sections)            │  │ │
│  │  │ To: codeSampleSnippet, usageInstructions            │  │ │
│  │  │ Output: partial_code_usage.json                     │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_datasets (TODO)                          │  │ │
│  │  │ Maps: card (frontmatter, text mentions)             │  │ │
│  │  │ To: trainedOn, evaluatedOn, evaluationMetrics       │  │ │
│  │  │ Output: partial_datasets.json                       │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_ethics_risks (TODO)                      │  │ │
│  │  │ Maps: card (limitations, ethical sections)          │  │ │
│  │  │ To: modelRisksBiasLimitations, ethicalSocial        │  │ │
│  │  │ Output: partial_ethics_risks.json                   │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│                             ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ hf_models_normalized (Merge & Validate)                  │  │
│  │                                                          │  │
│  │  1. Load all partial schemas                            │  │
│  │  2. Merge by model index                                │  │
│  │  3. Add platform metrics (downloads, likes)             │  │
│  │  4. Validate with Pydantic MLModel schema               │  │
│  │  5. Write final mlmodels.json                           │  │
│  │                                                          │  │
│  │  Output: /data/normalized/hf/<run>/mlmodels.json        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Example

### Input: Raw HF Model
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
  "card": "---\nlicense: apache-2.0\n---\n\n# BERT base model..."
}
```

### Intermediate: Partial Schemas

#### partial_basic_properties.json
```json
{
  "_model_id": "bert-base-uncased",
  "_index": 0,
  "identifier": "https://huggingface.co/bert-base-uncased",
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "sharedBy": "google",
  "dateCreated": "2020-01-01T00:00:00Z",
  "dateModified": "2020-06-15T10:30:00Z",
  "description": "# BERT base model...",
  "extraction_metadata": { ... }
}
```

#### partial_keywords_language.json (example)
```json
{
  "_model_id": "bert-base-uncased",
  "_index": 0,
  "keywords": ["bert", "transformer", "nlp"],
  "inLanguage": ["en"],
  "extraction_metadata": { ... }
}
```

#### partial_task_category.json (example)
```json
{
  "_model_id": "bert-base-uncased",
  "_index": 0,
  "mlTask": "fill-mask",
  "modelCategory": ["transformer", "bert"],
  "extraction_metadata": { ... }
}
```

### Output: Merged FAIR4ML MLModel
```json
{
  "identifier": "https://huggingface.co/bert-base-uncased",
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "sharedBy": "google",
  "dateCreated": "2020-01-01T00:00:00Z",
  "dateModified": "2020-06-15T10:30:00Z",
  "description": "# BERT base model...",
  "keywords": ["bert", "transformer", "nlp"],
  "inLanguage": ["en"],
  "mlTask": "fill-mask",
  "modelCategory": ["transformer", "bert"],
  "license": "apache-2.0",
  "metrics": {
    "downloads": 1000000,
    "likes": 500
  },
  "extraction_metadata": {
    "identifier": { "extraction_method": "Parsed_from_HF_dataset", ... },
    "keywords": { "extraction_method": "Parsed_from_tags", ... },
    ...
  }
}
```

## Key Design Principles

### 1. Separation of Concerns
Each property group has:
- **Dedicated mapping function** (`transformers/hf/mlmodel.py`)
- **Dedicated Dagster asset** (`etl/assets/hf_transformation.py`)
- **Separate partial schema file** (intermediate output)

### 2. Parallelization
Dagster can execute property extraction assets in parallel since they are independent, significantly speeding up transformation.

### 3. Error Isolation
If one property extraction fails, others continue. The final merge handles missing partials gracefully.

### 4. Incremental Development
New property groups can be added without modifying existing code:
1. Add mapping function
2. Add extraction asset
3. Update merge logic in `hf_models_normalized`

### 5. Testability
Each mapping function is pure and can be unit tested independently with mock data.

### 6. Traceability
- Each partial schema is saved for inspection
- Extraction metadata tracks provenance for every field
- Errors are logged and saved separately

### 7. Type Safety
Pydantic validation ensures the final merged schema conforms to FAIR4ML specification.

## File Organization

```
/data/
├── raw/hf/<timestamp>_<runid>/
│   └── hf_models_with_ancestors.json    # Input from extraction
│
└── normalized/hf/<timestamp>_<runid>/
    ├── partial_basic_properties.json    # ✅ Implemented
    ├── partial_keywords_language.json   # ⏳ TODO
    ├── mlmodels.json                    # Final merged output
    └── transformation_errors.json       # Validation errors (if any)
```

## Merge Strategy

The `hf_models_normalized` asset uses **index-based merging**:

1. Each partial schema includes `_index` field matching model position
2. Partial schemas are indexed by `_index` for O(1) lookup
3. For each model, merge all partial schemas:
   ```python
   merged = {
       **basic_props[idx],
       **keywords_lang[idx],
       **task_cat[idx],
       # ... etc
   }
   ```
4. Deep merge `extraction_metadata` dictionaries
5. Validate merged result with Pydantic
6. Write to final output

## Performance Characteristics

### With Parallel Execution (Dagster Default)
- **Time**: ~O(n) where n = number of models
- **Speedup**: Up to 8x (number of property groups) with full parallelization
- **Memory**: O(n × p) where p = number of property groups (partial schemas stored)

### Sequential Execution (Fallback)
- **Time**: O(n × p)
- **Memory**: O(n × p)

## Current Implementation Status

| Property Group | Mapping Function | Dagster Asset | Status |
|----------------|------------------|---------------|--------|
| Basic Properties | `map_basic_properties` | `hf_extract_basic_properties` | ✅ Done |
| Keywords & Language | `map_keywords_language` | `hf_extract_keywords_language` | ⏳ TODO |
| Task & Category | `map_task_category` | `hf_extract_task_category` | ⏳ TODO |
| License | `map_license` | `hf_extract_license` | ⏳ TODO |
| Lineage | `map_lineage` | `hf_extract_lineage` | ⏳ TODO |
| Code & Usage | `map_code_usage` | `hf_extract_code_usage` | ⏳ TODO |
| Datasets | `map_datasets` | `hf_extract_datasets` | ⏳ TODO |
| Ethics & Risks | `map_ethics_risks` | `hf_extract_ethics_risks` | ⏳ TODO |

## Next Steps

See `adding_property_extraction_assets.md` for a complete template to add new property extraction assets.

Priority order:
1. **Keywords & Language** - Simple tag parsing
2. **Task & Category** - ML-specific metadata
3. **License** - Legal compliance
4. **Lineage** - Model relationships
5. **Code & Usage** - Practical usage information
6. **Datasets** - Training data provenance
7. **Ethics & Risks** - Responsible AI documentation

