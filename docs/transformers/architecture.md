# Transformation Architecture

Detailed guide to the modular transformation architecture used in MLentory, with focus on the HuggingFace transformer.

---

## Architecture Overview

The transformation system uses a **modular, parallel extraction pattern** where each property group is processed independently, then merged into final validated FAIR4ML objects.

### Key Design Principles

1. **Separation of Concerns:** Each property group has dedicated mapping function and Dagster asset
2. **Parallelization:** Property extraction assets run in parallel
3. **Error Isolation:** One failure doesn't stop others
4. **Incremental Development:** Add new property groups without modifying existing code
5. **Testability:** Each mapping function is pure and testable
6. **Traceability:** Extraction metadata tracks provenance
7. **Type Safety:** Pydantic validation ensures schema compliance

---

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
│  │  │ hf_extract_keywords_language                        │  │ │
│  │  │ Maps: tags                                          │  │ │
│  │  │ To: keywords, inLanguage                            │  │ │
│  │  │ Output: partial_keywords_language.json             │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_task_category                            │  │ │
│  │  │ Maps: pipeline_tag, library_name, tags              │  │ │
│  │  │ To: mlTask, modelCategory                           │  │ │
│  │  │ Output: partial_task_category.json                  │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_license                                 │  │ │
│  │  │ Maps: tags, card frontmatter                        │  │ │
│  │  │ To: license, legal                                  │  │ │
│  │  │ Output: partial_license.json                        │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_lineage                                 │  │ │
│  │  │ Maps: tags (base_model:*)                          │  │ │
│  │  │ To: fineTunedFrom                                  │  │ │
│  │  │ Output: partial_lineage.json                        │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_code_usage                               │  │ │
│  │  │ Maps: card (code blocks, usage sections)            │  │ │
│  │  │ To: codeSampleSnippet, usageInstructions            │  │ │
│  │  │ Output: partial_code_usage.json                     │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_datasets                                 │  │ │
│  │  │ Maps: card (frontmatter, text mentions)            │  │ │
│  │  │ To: trainedOn, evaluatedOn, evaluationMetrics       │  │ │
│  │  │ Output: partial_datasets.json                       │  │ │
│  │  └─────────────────────────────────────────────────────┘  │ │
│  │                                                             │ │
│  │  ┌─────────────────────────────────────────────────────┐  │ │
│  │  │ hf_extract_ethics_risks                            │  │ │
│  │  │ Maps: card (limitations, ethical sections)          │  │ │
│  │  │ To: modelRisksBiasLimitations, ethicalSocial        │  │ │
│  │  │ Output: partial_ethics_risks.json                    │  │ │
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
│  │  Output: /data/normalized/hf/<run>/mlmodels.json       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

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
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "sharedBy": "google",
  "dateCreated": "2020-01-01T00:00:00Z",
  "dateModified": "2020-06-15T10:30:00Z",
  "description": "# BERT base model...",
  "extraction_metadata": {
    "identifier": {
      "extraction_method": "Parsed_from_HF_dataset",
      "confidence": 1.0,
      "source_field": "modelId"
    }
  }
}
```

#### partial_keywords_language.json

```json
{
  "_model_id": "bert-base-uncased",
  "_index": 0,
  "keywords": ["bert", "transformer", "nlp"],
  "inLanguage": ["en"],
  "extraction_metadata": {
    "keywords": {
      "extraction_method": "Parsed_from_tags",
      "confidence": 1.0,
      "source_field": "tags"
    }
  }
}
```

#### partial_task_category.json

```json
{
  "_model_id": "bert-base-uncased",
  "_index": 0,
  "mlTask": ["fill-mask"],
  "modelCategory": ["transformer", "bert"],
  "extraction_metadata": {
    "mlTask": {
      "extraction_method": "Parsed_from_pipeline_tag",
      "confidence": 1.0,
      "source_field": "pipeline_tag"
    }
  }
}
```

### Output: Merged FAIR4ML MLModel

```json
{
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "url": "https://huggingface.co/bert-base-uncased",
  "author": "google",
  "sharedBy": "google",
  "dateCreated": "2020-01-01T00:00:00Z",
  "dateModified": "2020-06-15T10:30:00Z",
  "description": "# BERT base model...",
  "keywords": ["bert", "transformer", "nlp"],
  "inLanguage": ["en"],
  "mlTask": ["fill-mask"],
  "modelCategory": ["transformer", "bert"],
  "license": "apache-2.0",
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
    "keywords": {
      "extraction_method": "Parsed_from_tags",
      "confidence": 1.0,
      "source_field": "tags"
    },
    ...
  }
}
```

---

## Merge Strategy

The `hf_models_normalized` asset uses **index-based merging**:

### Process

1. **Load Partial Schemas**
   - Read all partial schema JSON files
   - Index by `_index` field for O(1) lookup

2. **Merge by Index**
   ```python
   for idx in range(num_models):
       merged = {
           **basic_props[idx],
           **keywords_lang[idx],
           **task_cat[idx],
           # ... etc
       }
   ```

3. **Deep Merge Extraction Metadata**
   - Combine extraction metadata dictionaries
   - Preserve all provenance information

4. **Add Platform Metrics**
   - Add downloads, likes from raw data
   - Store in `metrics` field

5. **Validate**
   - Validate merged result with Pydantic
   - Log validation errors

6. **Write Output**
   - Save validated models to `mlmodels.json`
   - Save errors to `transformation_errors.json`

### Index Matching

Each partial schema includes:
- `_model_id`: Model identifier (for debugging)
- `_index`: Position in original array (for merging)

**Example:**
```json
{
  "_model_id": "bert-base-uncased",
  "_index": 0,
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  ...
}
```

---

## File Organization

```
/data/
├── raw/hf/<timestamp>_<runid>/
│   └── hf_models_with_ancestors.json    # Input from extraction
│
└── normalized/hf/<timestamp>_<runid>/
    ├── partial_basic_properties.json    # ✅ Implemented
    ├── partial_keywords_language.json   # ⏳ TODO
    ├── partial_task_category.json       # ⏳ TODO
    ├── partial_license.json             # ⏳ TODO
    ├── partial_lineage.json             # ⏳ TODO
    ├── partial_code_usage.json          # ⏳ TODO
    ├── partial_datasets.json            # ⏳ TODO
    ├── partial_ethics_risks.json        # ⏳ TODO
    ├── mlmodels.json                    # Final merged output
    └── transformation_errors.json       # Validation errors (if any)
```

---

## Performance Characteristics

### With Parallel Execution (Dagster Default)

- **Time:** ~O(n) where n = number of models
- **Speedup:** Up to 8x (number of property groups) with full parallelization
- **Memory:** O(n × p) where p = number of property groups (partial schemas stored)

### Sequential Execution (Fallback)

- **Time:** O(n × p)
- **Memory:** O(n × p)

**Recommendation:** Always use Dagster for automatic parallelization.

---

## Implementation Status

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

---

## Key Takeaways

1. **Modular architecture** enables parallel processing and easy extension
2. **Partial schemas** allow independent property extraction
3. **Index-based merging** efficiently combines partial results
4. **Pydantic validation** ensures schema compliance
5. **Extraction metadata** tracks data provenance
6. **Error isolation** allows partial success

---

## Next Steps

- See [HuggingFace Transformation](huggingface.md) - Detailed transformation guide
- Check [Adding a Transformer](adding-transformer.md) - How to add new transformers
- Explore [Loaders](../loaders/overview.md) - How normalized data is loaded
- Review [FAIR4ML Schema](../concepts/fair4ml-schema.md) - Schema reference
