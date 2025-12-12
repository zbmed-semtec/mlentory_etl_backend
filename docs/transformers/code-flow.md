#Code Flow

This guide explains how the transformation system works, using HuggingFace as a concrete example. You'll learn how control flows through the system and how Dagster assets orchestrate parallel property extraction.

---

## Overview: The Big Picture

Transformation in MLentory follows a modular, parallel pattern:

1. **Dagster assets** orchestrate the transformation
2. **Mapping functions** convert source fields to FAIR4ML properties
3. **Property groups** are extracted in parallel for efficiency
4. **Partial schemas** are merged into complete FAIR4ML objects
5. **Pydantic validation** ensures data quality

Let's trace through this flow step by step using HuggingFace as our example.

---

## Step 1: How Dagster Assets Control the Flow

Transformation assets are defined in `etl/assets/hf_transformation.py`. They use a **modular architecture** where different property groups are extracted in parallel.

### Asset Dependency Graph

```
hf_add_ancestor_models (from extraction)
    ↓
hf_normalized_run_folder (creates output folder)
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
    hf_entity_linking (links to related entities)
            ↓
    hf_models_normalized (merges all partial schemas, validates)
```

### Key Design: Parallel Property Extraction

The HuggingFace transformer extracts properties in **parallel** rather than sequentially. This means:

- **8 property groups** can be extracted simultaneously
- **Total time** ≈ time of slowest property group (not sum of all)
- **Error isolation**: If one property group fails, others continue
- **Easy to extend**: Add new property groups without changing existing ones

---

## Step 2: How Run Folders Are Created

The transformation stage creates its own run folder, matching the extraction run folder name:

```140:168:etl/assets/hf_transformation.py
@asset(
    group_name="hf_transformation",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_normalized_run_folder(models_data: Tuple[str, str]) -> Tuple[str, str]:
    """
    Create a run folder for normalized HF models.
    
    Follows the same pattern as raw extraction for traceability.
    
    Args:
        models_data: Tuple of (models_json_path, raw_run_folder)
        
    Returns:
        Path to the normalized run-specific output directory
    """
    raw_data_json_path, raw_run_folder = models_data
    
    # Extract timestamp and run_id from raw folder name
    raw_folder_name = Path(raw_run_folder).name  # e.g., "2025-10-30_16-45-38_a510a3c3"
    
    # Create corresponding normalized folder
    normalized_base = Path("/data/2_normalized/hf")
    normalized_run_folder = normalized_base / raw_folder_name
    normalized_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created normalized run folder: {normalized_run_folder}")
    return (str(raw_data_json_path), str(normalized_run_folder))
```

**Why this matters:**

- Normalized folder name matches raw folder name
- Easy to trace from normalized data back to raw data
- Maintains run-level organization

---

## Step 3: How Property Extraction Works

Each property group has its own asset that extracts a subset of FAIR4ML properties. Let's look at the basic properties extractor:

```171:245:etl/assets/hf_transformation.py
@asset(
    group_name="hf_transformation",
    ins={
        "models_data": AssetIn("hf_normalized_run_folder"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_extract_basic_properties(
    models_data: Tuple[str, str],
) -> str:
    """
    Extract basic properties from HF models.
    
    Maps: modelId, author, createdAt, last_modified, card
    To: identifier, name, url, author, sharedBy, dates, description, URLs
    
    Args:
        models_data: Tuple of (raw_data_json_path, normalized_folder)
        
    Returns:
        Path to saved partial schema JSON file
    """
    raw_data_json_path, normalized_folder = models_data
    
    # Load raw models
    logger.info(f"Loading raw models from {raw_data_json_path}")
    with open(raw_data_json_path, 'r', encoding='utf-8') as f:
        raw_models = json.load(f)
    
    logger.info(f"Loaded {len(raw_models)} raw models")
    
    # Extract basic properties for each model
    partial_schemas: List[Dict[str, Any]] = []
    
    for idx, raw_model in enumerate(raw_models):
        model_id = raw_model.get("modelId", f"unknown_{idx}")
        
        try:
            # Map basic properties
            partial_data = map_basic_properties(raw_model)
            
            # Add model_id as key for merging later
            partial_data["_model_id"] = model_id
            partial_data["_index"] = idx
            
            partial_schemas.append(partial_data)
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Extracted basic properties for {idx + 1}/{len(raw_models)} models")
                
        except Exception as e:
            logger.error(f"Error extracting basic properties for {model_id}: {e}", exc_info=True)
            
            # Create minimal partial schema with error info
            partial_schemas.append({
                "_model_id": model_id,
                "_index": idx,
                "_error": str(e),
                "identifier": model_id,
                "name": model_id,
                "url": ""
            })
    
    logger.info(f"Extracted basic properties for {len(partial_schemas)} models")
    
    # Save partial schemas
    output_path = Path(normalized_folder) / "partial_basic_properties.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(partial_schemas, f,
                  indent=2,
                  ensure_ascii=False,
                  default=_json_default)
    
    logger.info(f"Saved basic properties to {output_path}")
    return str(output_path)
```

**Flow:**

1. Asset receives raw models JSON path and normalized folder
2. Loads raw models from JSON file
3. For each model, calls `map_basic_properties()` mapping function
4. Saves partial schemas to `partial_basic_properties.json`
5. Returns path to partial schema file

---

## Step 4: How Mapping Functions Work

Mapping functions in `etl_transformers/hf/transform_mlmodel.py` do the actual field conversion:

```1:50:etl_transformers/hf/transform_mlmodel.py
"""
HuggingFace to FAIR4ML MLModel transformation functions.

This module provides modular mapping functions that transform raw HuggingFace
model metadata into FAIR4ML-compliant MLModel objects.

Each mapping function handles a specific group of related properties and returns
a dictionary with the mapped fields plus extraction metadata for provenance tracking.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, Any, Optional
import logging
from etl_extractors.hf import HFHelper
import pycountry

from schemas.fair4ml import MLModel, ExtractionMetadata


logger = logging.getLogger(__name__)


def _create_extraction_metadata(
    method: str,
    confidence: float = 1.0,
    source_field: Optional[str] = None,
    notes: Optional[str] = None,
) -> ExtractionMetadata:
    """
    Create extraction metadata for a field.
    
    Args:
        method: Extraction method description
        confidence: Confidence score (0.0 to 1.0)
        source_field: Name of source field in raw data
        notes: Additional notes
        
    Returns:
        ExtractionMetadata object
    """
    return ExtractionMetadata(
        extraction_method=method,
        confidence=confidence,
        source_field=source_field,
        notes=notes,
    )
```

### Example Mapping Function

Here's how `map_basic_properties()` works:

```python
def map_basic_properties(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map basic properties from HuggingFace to FAIR4ML.
    
    Maps:
    - modelId → identifier, name, url
    - author → author, sharedBy
    - createdAt → dateCreated
    - last_modified → dateModified
    - card → description
    
    Returns:
        Dictionary with mapped properties and extraction metadata
    """
    model_id = raw_model.get("modelId", "")
    
    # Build identifier as full URL
    identifier = f"https://huggingface.co/{model_id}" if model_id else ""
    
    result = {
        "identifier": [identifier],
        "name": model_id.split("/")[-1] if model_id else "",
        "url": identifier,
        "author": raw_model.get("author", ""),
        "sharedBy": raw_model.get("author", ""),  # Same as author for HF
        "dateCreated": _parse_datetime(raw_model.get("createdAt")),
        "dateModified": _parse_datetime(raw_model.get("last_modified")),
        "description": _strip_frontmatter(raw_model.get("card", "")),
        # ... extraction metadata ...
    }
    
    return result
```

**Key Points:**

- Pure function: takes raw model dict, returns FAIR4ML dict
- Handles missing fields gracefully
- Includes extraction metadata for provenance
- Can be tested independently

---

## Step 5: How Partial Schemas Are Merged

After all property groups are extracted, they're merged into complete FAIR4ML objects:

```python
@asset(
    group_name="hf_transformation",
    ins={
        "basic_props": AssetIn("hf_extract_basic_properties"),
        "keywords_lang": AssetIn("hf_extract_keywords_language"),
        "task_category": AssetIn("hf_extract_task_category"),
        "license": AssetIn("hf_extract_license"),
        "lineage": AssetIn("hf_extract_lineage"),
        "code_usage": AssetIn("hf_extract_code_usage"),
        "datasets": AssetIn("hf_extract_datasets"),
        "ethics_risks": AssetIn("hf_extract_ethics_risks"),
        "entity_linking": AssetIn("hf_entity_linking"),
        "models_data": AssetIn("hf_normalized_run_folder"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_models_normalized(
    basic_props: str,
    keywords_lang: str,
    task_category: str,
    license: str,
    lineage: str,
    code_usage: str,
    datasets: str,
    ethics_risks: str,
    entity_linking: str,
    models_data: Tuple[str, str],
) -> Tuple[str, str]:
    """
    Merge all partial schemas and validate with Pydantic.
    
    This is the final transformation step that:
    1. Loads all partial schema files
    2. Merges them by model_id
    3. Validates each merged model with Pydantic
    4. Saves validated FAIR4ML models to mlmodels.json
    """
    # Load all partial schemas
    partial_files = {
        "basic": basic_props,
        "keywords": keywords_lang,
        "task": task_category,
        "license": license,
        "lineage": lineage,
        "code": code_usage,
        "datasets": datasets,
        "ethics": ethics_risks,
    }
    
    # Load and merge by model_id
    merged_models = {}
    for prop_type, file_path in partial_files.items():
        with open(file_path, 'r') as f:
            partials = json.load(f)
        
        for partial in partials:
            model_id = partial.get("_model_id")
            if model_id not in merged_models:
                merged_models[model_id] = {}
            
            # Merge properties (partials may have overlapping keys)
            merged_models[model_id].update(partial)
    
    # Validate and save
    validated_models = []
    for model_id, merged_data in merged_models.items():
        try:
            # Remove internal keys
            clean_data = {k: v for k, v in merged_data.items() 
                          if not k.startswith("_")}
            
            # Validate with Pydantic
            model = MLModel(**clean_data)
            validated_models.append(model.model_dump(mode='json', by_alias=True))
        except ValidationError as e:
            logger.error(f"Validation failed for {model_id}: {e}")
            # Save error for debugging
    
    # Save validated models
    normalized_folder = models_data[1]
    output_path = Path(normalized_folder) / "mlmodels.json"
    with open(output_path, 'w') as f:
        json.dump(validated_models, f, indent=2, default=_json_default)
    
    return (str(output_path), normalized_folder)
```

**Flow:**

1. Asset receives paths to all partial schema files
2. Loads each partial schema file
3. Merges partial schemas by `_model_id` key
4. Validates each merged model with Pydantic `MLModel` schema
5. Saves validated models to `mlmodels.json`

---

## Step 6: How Validation Works

Pydantic validation ensures data quality:

```python
from schemas.fair4ml import MLModel
from pydantic import ValidationError

# Validate transformed data
try:
    model = MLModel(**transformed_data)
    # Valid! Model conforms to FAIR4ML schema
except ValidationError as e:
    # Invalid - log errors for debugging
    logger.error(f"Validation failed: {e}")
    save_validation_errors(model_id, e.errors())
```

**What Pydantic Validates:**

- **Type checking**: Fields have correct types (string, list, datetime, etc.)
- **Required fields**: All required fields are present
- **Value constraints**: Dates are valid, URLs are formatted correctly, etc.
- **Nested objects**: Related entities (datasets, papers) are properly structured

**Benefits:**

- Catches errors early (before loading to databases)
- Provides clear error messages
- Ensures data consistency

---

## Step 7: How Entity Linking Works

After extracting model properties, the system links models to related entities:

```248:324:etl/assets/hf_transformation.py
@asset(
    group_name="hf_transformation",
    ins={
        "datasets_mapping": AssetIn("hf_identified_datasets"),
        "articles_mapping": AssetIn("hf_identified_articles"),
        "keywords_mapping": AssetIn("hf_identified_keywords"),
        "licenses_mapping": AssetIn("hf_identified_licenses"),
        "base_models_mapping": AssetIn("hf_identified_base_models"),
        "languages_mapping": AssetIn("hf_identified_languages"),
        "tasks_mapping": AssetIn("hf_identified_tasks"),
        "run_folder_data": AssetIn("hf_normalized_run_folder"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_entity_linking(
    datasets_mapping: Tuple[Dict[str, List[str]], str],
    articles_mapping: Tuple[Dict[str, List[str]], str],
    keywords_mapping: Tuple[Dict[str, List[str]], str],
    licenses_mapping: Tuple[Dict[str, List[str]], str],
    base_models_mapping: Tuple[Dict[str, List[str]], str],
    languages_mapping: Tuple[Dict[str, List[str]], str],
    tasks_mapping: Tuple[Dict[str, List[str]], str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Link models to related entities (datasets, articles, etc.).
    
    Takes the entity mappings from extraction and creates proper
    FAIR4ML relationships in the normalized models.
    """
    # Implementation links models to entities
    # ...
```

**What Entity Linking Does:**

- Takes entity mappings from extraction (e.g., "model1" → ["squad", "glue"])
- Resolves entity names to full identifiers
- Creates proper FAIR4ML relationships (e.g., `trainedOn`, `cites`, `fineTunedFrom`)
- Links to normalized entity files (datasets.json, articles.json, etc.)

---

## Complete Flow Example: Transforming HuggingFace Models

Let's trace through a complete transformation run:

### 1. User Triggers Transformation

User clicks "Materialize" in Dagster UI for `hf_models_normalized` asset.

### 2. Dagster Resolves Dependencies

Dagster sees that `hf_models_normalized` depends on:

- `hf_extract_basic_properties`
- `hf_extract_keywords_language`
- `hf_extract_task_category`
- `hf_extract_license`
- `hf_extract_lineage`
- `hf_extract_code_usage`
- `hf_extract_datasets`
- `hf_extract_ethics_risks`
- `hf_entity_linking`

All of these depend on `hf_normalized_run_folder`, which depends on `hf_add_ancestor_models` (from extraction).

### 3. Parallel Property Extraction

Dagster executes all property extraction assets **in parallel**:

- `hf_extract_basic_properties` → `partial_basic_properties.json`
- `hf_extract_keywords_language` → `partial_keywords_language.json`
- `hf_extract_task_category` → `partial_task_category.json`
- ... (all run simultaneously)

### 4. Entity Linking

After property extraction, `hf_entity_linking` links models to related entities.

### 5. Schema Merging and Validation

`hf_models_normalized` asset:

- Loads all partial schema files
- Merges them by model_id
- Validates each merged model with Pydantic
- Saves validated models to `mlmodels.json`

### 6. Final Output

All normalized data is saved in the run folder:
```
/data/2_normalized/hf/2025-01-15_12-00-00_abc123/
├── partial_basic_properties.json
├── partial_keywords_language.json
├── partial_task_category.json
├── ...
├── mlmodels.json              (final validated models)
├── datasets.json               (normalized datasets)
├── articles.json               (normalized articles)
└── mlmodels_transformation_errors.json  (validation errors)
```

---

## Key Concepts for Beginners

### What is a Partial Schema?

A partial schema is a dictionary containing:

- Some FAIR4ML properties (not all)
- `_model_id` key for merging
- `_index` key for ordering
- Extraction metadata

**Example:**
```json
{
  "_model_id": "bert-base-uncased",
  "_index": 0,
  "identifier": ["https://huggingface.co/bert-base-uncased"],
  "name": "bert-base-uncased",
  "author": "google"
}
```

### Why Parallel Extraction?

**Sequential** (slow):
```
Extract basic → 1s
Extract keywords → 1s
Extract tasks → 1s
Extract license → 1s
Total: 4s
```

**Parallel** (fast):
```
Extract basic ┐
Extract keywords ├→ All run simultaneously
Extract tasks ┤
Extract license ┘
Total: ~1s (time of slowest)
```

### How Does Merging Work?

Partial schemas are merged by `_model_id`:

```python
# Partial 1
{"_model_id": "model1", "identifier": ["url1"], "name": "Model1"}

# Partial 2
{"_model_id": "model1", "mlTask": ["classification"], "author": "Alice"}

# Merged
{"_model_id": "model1", "identifier": ["url1"], "name": "Model1", 
 "mlTask": ["classification"], "author": "Alice"}
```

### What is Pydantic Validation?

Pydantic validates that data matches the schema:

```python
from schemas.fair4ml import MLModel

# Valid
model = MLModel(identifier=["url"], name="Model")

# Invalid (missing required field)
model = MLModel(name="Model")  # Error: identifier is required
```

---

## Common Patterns

### Pattern 1: Modular Property Extraction

Each property group is a separate asset and mapping function:

- Easy to test independently
- Easy to add new property groups
- Error isolation (one failure doesn't stop others)

### Pattern 2: Partial Schema Merging

Extract properties separately, merge at the end:

- Enables parallel processing
- Makes debugging easier (see which property group failed)
- Allows incremental development

### Pattern 3: Extraction Metadata

Track how each field was obtained:

- Provenance tracking
- Confidence scores
- Source field names
- Debugging information

### Pattern 4: Graceful Error Handling

Continue processing even when individual models fail:

- Maximize success rate
- Log errors for debugging
- Save error files for analysis

---

## Debugging Tips

### View Partial Schemas

Check partial schema files to see what was extracted:
```bash
cat /data/2_normalized/hf/2025-01-15_12-00-00_abc123/partial_basic_properties.json
```

### Check Validation Errors

Look at transformation error files:
```bash
cat /data/2_normalized/hf/2025-01-15_12-00-00_abc123/mlmodels_transformation_errors.json
```

### Test Mapping Functions

Test mapping functions independently:
```python
from etl_transformers.hf.transform_mlmodel import map_basic_properties

raw_model = {"modelId": "bert-base-uncased", "author": "google"}
result = map_basic_properties(raw_model)
print(result)
```

### View Asset Dependencies

In Dagster UI, click an asset to see:

- What it depends on
- What depends on it
- Execution history

---

## Next Steps

- See [HuggingFace Transformation](huggingface.md) for detailed HuggingFace-specific documentation
- Review [Adding a Transformer](adding-transformer.md) for step-by-step guide
- Explore [Transformers Overview](overview.md) for high-level concepts
- Review [Architecture Overview](../architecture/overview.md) to see how transformers fit into the system

