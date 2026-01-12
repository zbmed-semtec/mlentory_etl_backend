# Adding a Transformer

Complete step-by-step guide for creating a new transformer to convert platform-specific data into FAIR4ML format.

---

## Prerequisites

Before starting, make sure you understand:

- [Transformers Overview](overview.md) - High-level concepts
- [Transformers Code Flow](code-flow.md) - How transformation works internally
- [FAIR4ML Schema](../schemas/fair4ml.md) - Target schema structure
- Python basics (functions, dictionaries, error handling)
- Pydantic models (for validation)

---

## Overview: What You're Building

A transformer consists of:

1. **Mapping functions** - Convert source fields to FAIR4ML properties
2. **Property extractors** - Extract different property groups (basic, tasks, datasets, etc.)
3. **Dagster assets** - Orchestrate parallel property extraction
4. **Schema merging** - Combine partial schemas into complete FAIR4ML objects
5. **Validation** - Ensure data conforms to FAIR4ML schema

---

## Step 1: Understand the Source Data Format

First, examine your raw data structure. Look at the JSON files from extraction:

```bash
cat /data/1_raw/newplatform/2025-01-15_12-00-00_abc123/newplatform_models.json
```

**Key questions:**

- What fields are available?
- How are dates formatted?
- Are there nested structures?
- What fields map to FAIR4ML properties?

**Example raw data:**
```json
{
  "id": "model-123",
  "name": "My Model",
  "author": "Alice",
  "created_at": "2024-01-15T10:00:00Z",
  "description": "A great model for NLP",
  "task": "text-classification",
  "license": "mit"
}
```

---

## Step 2: Create Mapping Functions

Create `etl_transformers/newplatform/transform_mlmodel.py`:

```python
"""
NewPlatform to FAIR4ML MLModel transformation functions.

This module provides modular mapping functions that transform raw NewPlatform
model metadata into FAIR4ML-compliant MLModel objects.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional
import logging

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


def _parse_datetime(value: Any) -> Optional[datetime]:
    """
    Parse a datetime value from various formats.
    
    Args:
        value: Input value (string, datetime, or None)
        
    Returns:
        Parsed datetime or None
    """
    if value is None:
        return None
    
    if isinstance(value, datetime):
        return value
    
    if isinstance(value, str):
        try:
            # Try parsing ISO format
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse datetime: {value}")
            return None
    
    return None


def map_basic_properties(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map basic identification, temporal, and URL properties from NewPlatform to FAIR4ML.
    
    This function handles:
    - Core identification: id → identifier, name, url
    - Temporal fields: created_at → dateCreated, dateModified, datePublished
    - Authorship: author → author, sharedBy
    - Description: description → description
    
    Args:
        raw_model: Dictionary containing raw NewPlatform model data
        
    Returns:
        Dictionary with mapped fields and extraction_metadata
    """
    model_id = raw_model.get("id", "")
    name = raw_model.get("name", "")
    author = raw_model.get("author", "")
    created_at = raw_model.get("created_at")
    description = raw_model.get("description", "")
    
    # Build identifier URL (adjust based on your platform)
    identifier_url = f"https://newplatform.com/models/{model_id}" if model_id else ""
    
    # Parse dates
    date_created = _parse_datetime(created_at)
    
    # Build result with mapped fields
    result = {
        # Core identification
        "identifier": [identifier_url] if identifier_url else [],
        "name": name,
        "url": identifier_url,
        
        # Authorship
        "author": author,
        "sharedBy": author,  # Adjust if different
        
        # Temporal
        "dateCreated": date_created,
        "dateModified": date_created,  # Use created if modified not available
        "datePublished": date_created,
        
        # Description
        "description": description if description else None,
    }
    
    # Build extraction metadata for each field
    extraction_metadata = {
        "identifier": _create_extraction_metadata(
            method="Parsed_from_NewPlatform_API",
            confidence=1.0,
            source_field="id",
            notes="Converted to NewPlatform URL format"
        ),
        "name": _create_extraction_metadata(
            method="Parsed_from_NewPlatform_API",
            confidence=1.0,
            source_field="name"
        ),
        "author": _create_extraction_metadata(
            method="Parsed_from_NewPlatform_API",
            confidence=1.0,
            source_field="author"
        ),
        "dateCreated": _create_extraction_metadata(
            method="Parsed_from_NewPlatform_API",
            confidence=1.0,
            source_field="created_at"
        ),
        "description": _create_extraction_metadata(
            method="Parsed_from_NewPlatform_API",
            confidence=1.0,
            source_field="description"
        ),
    }
    
    result["extraction_metadata"] = extraction_metadata
    
    return result


def map_ml_task(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map ML task from NewPlatform to FAIR4ML.
    
    Args:
        raw_model: Dictionary containing raw NewPlatform model data
        
    Returns:
        Dictionary with mlTask field and extraction_metadata
    """
    task = raw_model.get("task", "")
    
    result = {}
    
    if task:
        # Convert to list format (FAIR4ML expects lists)
        result["mlTask"] = [task]
        
        result["extraction_metadata"] = {
            "mlTask": _create_extraction_metadata(
                method="Parsed_from_NewPlatform_API",
                confidence=1.0,
                source_field="task"
            )
        }
    
    return result


def map_license(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map license from NewPlatform to FAIR4ML.
    
    Args:
        raw_model: Dictionary containing raw NewPlatform model data
        
    Returns:
        Dictionary with license field and extraction_metadata
    """
    license_value = raw_model.get("license", "")
    
    result = {}
    
    if license_value:
        result["license"] = license_value
        
        result["extraction_metadata"] = {
            "license": _create_extraction_metadata(
                method="Parsed_from_NewPlatform_API",
                confidence=1.0,
                source_field="license"
            )
        }
    
    return result
```

**Key Points:**

- Each mapping function handles one property group
- Functions are pure (no side effects)
- Always include extraction metadata
- Handle missing fields gracefully (return empty dict or None)
- Convert values to FAIR4ML format (lists, proper types, etc.)

---

## Step 3: Create Property Extraction Assets

Create `etl/assets/newplatform_transformation.py`:

```python
"""
Dagster assets for NewPlatform → FAIR4ML transformation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple, List, Dict, Any
import logging

from dagster import asset, AssetIn

from etl_transformers.newplatform.transform_mlmodel import (
    map_basic_properties,
    map_ml_task,
    map_license,
)
from schemas.fair4ml import MLModel
from pydantic import ValidationError


logger = logging.getLogger(__name__)


def _json_default(o):
    """JSON serializer for non-serializable types."""
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    return str(o)


@asset(
    group_name="newplatform_transformation",
    ins={"models_data": AssetIn("newplatform_raw_models")},
    tags={"pipeline": "newplatform_etl"}
)
def newplatform_normalized_run_folder(
    models_data: Tuple[str, str],
) -> Tuple[str, str]:
    """
    Create a run folder for normalized NewPlatform models.
    
    Args:
        models_data: Tuple of (models_json_path, raw_run_folder)
        
    Returns:
        Tuple of (raw_data_json_path, normalized_folder)
    """
    raw_data_json_path, raw_run_folder = models_data
    
    # Extract timestamp and run_id from raw folder name
    raw_folder_name = Path(raw_run_folder).name  # e.g., "2025-01-15_12-00-00_abc123"
    
    # Create corresponding normalized folder
    normalized_base = Path("/data/2_normalized/newplatform")
    normalized_run_folder = normalized_base / raw_folder_name
    normalized_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created normalized run folder: {normalized_run_folder}")
    return (str(raw_data_json_path), str(normalized_run_folder))


@asset(
    group_name="newplatform_transformation",
    ins={"models_data": AssetIn("newplatform_normalized_run_folder")},
    tags={"pipeline": "newplatform_etl"}
)
def newplatform_extract_basic_properties(
    models_data: Tuple[str, str],
) -> str:
    """
    Extract basic properties from NewPlatform models.
    
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
        model_id = raw_model.get("id", f"unknown_{idx}")
        
        try:
            # Map basic properties
            partial_data = map_basic_properties(raw_model)
            
            # Add model_id as key for merging later
            partial_data["_model_id"] = model_id
            partial_data["_index"] = idx
            
            partial_schemas.append(partial_data)
            
        except Exception as e:
            logger.error(f"Error extracting basic properties for {model_id}: {e}", exc_info=True)
            
            # Create minimal partial schema with error info
            partial_schemas.append({
                "_model_id": model_id,
                "_index": idx,
                "_error": str(e),
                "identifier": [model_id],
                "name": model_id,
            })
    
    logger.info(f"Extracted basic properties for {len(partial_schemas)} models")
    
    # Save partial schemas
    output_path = Path(normalized_folder) / "partial_basic_properties.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(partial_schemas, f, indent=2, ensure_ascii=False, default=_json_default)
    
    logger.info(f"Saved basic properties to {output_path}")
    return str(output_path)


@asset(
    group_name="newplatform_transformation",
    ins={"models_data": AssetIn("newplatform_normalized_run_folder")},
    tags={"pipeline": "newplatform_etl"}
)
def newplatform_extract_ml_task(
    models_data: Tuple[str, str],
) -> str:
    """
    Extract ML task from NewPlatform models.
    
    Args:
        models_data: Tuple of (raw_data_json_path, normalized_folder)
        
    Returns:
        Path to saved partial schema JSON file
    """
    raw_data_json_path, normalized_folder = models_data
    
    # Load raw models
    with open(raw_data_json_path, 'r', encoding='utf-8') as f:
        raw_models = json.load(f)
    
    # Extract ML task for each model
    partial_schemas: List[Dict[str, Any]] = []
    
    for idx, raw_model in enumerate(raw_models):
        model_id = raw_model.get("id", f"unknown_{idx}")
        
        try:
            partial_data = map_ml_task(raw_model)
            partial_data["_model_id"] = model_id
            partial_data["_index"] = idx
            partial_schemas.append(partial_data)
        except Exception as e:
            logger.error(f"Error extracting ML task for {model_id}: {e}")
            partial_schemas.append({
                "_model_id": model_id,
                "_index": idx,
            })
    
    # Save partial schemas
    output_path = Path(normalized_folder) / "partial_ml_task.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(partial_schemas, f, indent=2, ensure_ascii=False, default=_json_default)
    
    return str(output_path)


@asset(
    group_name="newplatform_transformation",
    ins={
        "basic_props": AssetIn("newplatform_extract_basic_properties"),
        "ml_task": AssetIn("newplatform_extract_ml_task"),
        "models_data": AssetIn("newplatform_normalized_run_folder"),
    },
    tags={"pipeline": "newplatform_etl"}
)
def newplatform_models_normalized(
    basic_props: str,
    ml_task: str,
    models_data: Tuple[str, str],
) -> Tuple[str, str]:
    """
    Merge all partial schemas and validate with Pydantic.
    
    This is the final transformation step that:
    1. Loads all partial schema files
    2. Merges them by model_id
    3. Validates each merged model with Pydantic
    4. Saves validated FAIR4ML models to mlmodels.json
    
    Args:
        basic_props: Path to basic properties partial schema
        ml_task: Path to ML task partial schema
        models_data: Tuple of (raw_data_json_path, normalized_folder)
        
    Returns:
        Tuple of (mlmodels_json_path, normalized_folder)
    """
    normalized_folder = models_data[1]
    
    # Load all partial schemas
    partial_files = {
        "basic": basic_props,
        "ml_task": ml_task,
    }
    
    # Load and merge by model_id
    merged_models = {}
    for prop_type, file_path in partial_files.items():
        with open(file_path, 'r') as f:
            partials = json.load(f)
        
        for partial in partials:
            model_id = partial.get("_model_id")
            if not model_id:
                continue
            
            if model_id not in merged_models:
                merged_models[model_id] = {}
            
            # Merge properties (partials may have overlapping keys)
            merged_models[model_id].update(partial)
    
    # Validate and save
    validated_models = []
    validation_errors = []
    
    for model_id, merged_data in merged_models.items():
        try:
            # Remove internal keys
            clean_data = {
                k: v for k, v in merged_data.items()
                if not k.startswith("_")
            }
            
            # Validate with Pydantic
            model = MLModel(**clean_data)
            validated_models.append(model.model_dump(mode='json', by_alias=True))
            
        except ValidationError as e:
            logger.error(f"Validation failed for {model_id}: {e}")
            validation_errors.append({
                "model_id": model_id,
                "errors": e.errors(),
                "data": clean_data,
            })
    
    # Save validated models
    output_path = Path(normalized_folder) / "mlmodels.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(validated_models, f, indent=2, ensure_ascii=False, default=_json_default)
    
    logger.info(f"Saved {len(validated_models)} validated models to {output_path}")
    
    # Save validation errors if any
    if validation_errors:
        errors_path = Path(normalized_folder) / "mlmodels_transformation_errors.json"
        with open(errors_path, 'w', encoding='utf-8') as f:
            json.dump(validation_errors, f, indent=2, ensure_ascii=False)
        logger.warning(f"Saved {len(validation_errors)} validation errors to {errors_path}")
    
    return (str(output_path), normalized_folder)
```

**Key Points:**

- Create normalized run folder matching raw run folder name
- Extract properties in parallel (separate assets)
- Save partial schemas with `_model_id` for merging
- Merge all partial schemas in final asset
- Validate with Pydantic before saving
- Save validation errors separately

---

## Step 4: Register Assets in Repository

Add to `etl/repository.py`:

```python
from etl.assets import newplatform_transformation as newplatform_transformation_module

@repository
def mlentory_etl_repository():
    # ... existing assets ...
    newplatform_transformation_assets = load_assets_from_modules([newplatform_transformation_module])
    return [..., *newplatform_transformation_assets]
```

---

## Step 5: Create Module Structure

Create `etl_transformers/newplatform/__init__.py`:

```python
"""
NewPlatform transformer module.
"""

from .transform_mlmodel import (
    map_basic_properties,
    map_ml_task,
    map_license,
)

__all__ = [
    "map_basic_properties",
    "map_ml_task",
    "map_license",
]
```

---

## Step 6: Testing

Create tests in `tests/test_newplatform_transformer.py`:

```python
"""Tests for NewPlatform transformer."""

import pytest
from etl_transformers.newplatform.transform_mlmodel import (
    map_basic_properties,
    map_ml_task,
)


def test_map_basic_properties():
    """Test basic properties mapping."""
    raw_model = {
        "id": "model-123",
        "name": "Test Model",
        "author": "Alice",
        "created_at": "2024-01-15T10:00:00Z",
        "description": "A test model",
    }
    
    result = map_basic_properties(raw_model)
    
    assert result["name"] == "Test Model"
    assert result["author"] == "Alice"
    assert "identifier" in result
    assert "extraction_metadata" in result


def test_map_ml_task():
    """Test ML task mapping."""
    raw_model = {
        "id": "model-123",
        "task": "text-classification",
    }
    
    result = map_ml_task(raw_model)
    
    assert result["mlTask"] == ["text-classification"]
    assert "extraction_metadata" in result


def test_map_basic_properties_missing_fields():
    """Test mapping handles missing fields gracefully."""
    raw_model = {
        "id": "model-123",
    }
    
    result = map_basic_properties(raw_model)
    
    assert result["name"] == ""  # Empty string for missing name
    assert result.get("author") is None or result["author"] == ""
```

---

## Common Mapping Patterns

### Pattern 1: Direct Mapping

Simple field copy:

```python
result["name"] = raw_model.get("name", "")
```

### Pattern 2: Value Transformation

Convert format:

```python
# Source: single value
task = raw_model.get("task", "")

# Target: list format
result["mlTask"] = [task] if task else []
```

### Pattern 3: URL Generation

Build URLs from IDs:

```python
model_id = raw_model.get("id", "")
result["url"] = f"https://platform.com/models/{model_id}" if model_id else ""
```

### Pattern 4: Date Parsing

Handle various date formats:

```python
date_created = _parse_datetime(raw_model.get("created_at"))
result["dateCreated"] = date_created
```

### Pattern 5: Field Combination

Merge multiple fields:

```python
keywords = []
if raw_model.get("tags"):
    keywords.extend(raw_model["tags"])
if raw_model.get("categories"):
    keywords.extend(raw_model["categories"])
result["keywords"] = keywords
```

### Pattern 6: Default Values

Provide sensible defaults:

```python
result["sharedBy"] = raw_model.get("author", raw_model.get("owner", ""))
```

---

## Handling Complex Cases

### Nested Structures

If your source has nested data:

```python
def map_datasets(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """Extract datasets from nested structure."""
    training_data = raw_model.get("training", {})
    datasets = training_data.get("datasets", [])
    
    result = {}
    if datasets:
        # Extract dataset identifiers
        dataset_ids = [d.get("id") for d in datasets if d.get("id")]
        result["trainedOn"] = dataset_ids
    
    return result
```

### Multiple Sources

If data comes from multiple fields:

```python
def map_description(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """Combine description from multiple sources."""
    description_parts = []
    
    if raw_model.get("summary"):
        description_parts.append(raw_model["summary"])
    if raw_model.get("details"):
        description_parts.append(raw_model["details"])
    
    result = {}
    if description_parts:
        result["description"] = "\n\n".join(description_parts)
    
    return result
```

### Conditional Mapping

Map based on conditions:

```python
def map_category(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """Infer category from other fields."""
    library = raw_model.get("library", "")
    
    result = {}
    if "transformers" in library.lower():
        result["modelCategory"] = ["transformer"]
    elif "torch" in library.lower():
        result["modelCategory"] = ["neural-network"]
    
    return result
```

---

## Checklist

Before considering your transformer complete:

- [ ] Mapping functions implemented for all property groups
- [ ] Extraction metadata included for all fields
- [ ] Dagster assets created for property extraction
- [ ] Schema merging asset implemented
- [ ] Pydantic validation working
- [ ] Assets registered in repository
- [ ] Module exports in `__init__.py`
- [ ] Basic tests written
- [ ] Error handling implemented
- [ ] Logging added throughout
- [ ] Handles missing fields gracefully
- [ ] Documentation updated

---

## Next Steps

After creating your transformer:

1. **Test it** - Run transformation manually to verify it works
2. **Create loader** - See [Loaders Code Flow](../loaders/code-flow.md)
3. **Update documentation** - Add your platform to relevant docs
4. **Add more properties** - Gradually expand property coverage

---

## Getting Help

- Review [Transformers Code Flow](code-flow.md) for detailed flow explanation
- Check [HuggingFace Transformation](huggingface.md) for a complete example
- Review [FAIR4ML Schema](../schemas/fair4ml.md) for target structure
- See [Transformers Overview](overview.md) for high-level concepts

---

## Example: Complete Minimal Transformer

Here's a minimal working example:

```python
# etl_transformers/simple/transform_mlmodel.py

from typing import Dict, Any

def map_basic_properties(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal basic properties mapping."""
    return {
        "identifier": [raw_model.get("id", "")],
        "name": raw_model.get("name", ""),
        "author": raw_model.get("author", ""),
        "description": raw_model.get("description", ""),
    }
```

```python
# etl/assets/simple_transformation.py

from dagster import asset, AssetIn
import json
from pathlib import Path
from etl_transformers.simple.transform_mlmodel import map_basic_properties
from schemas.fair4ml import MLModel

@asset(
    group_name="simple_transformation",
    ins={"models_data": AssetIn("simple_raw_models")},
)
def simple_models_normalized(models_data: tuple) -> tuple:
    """Transform and validate models."""
    json_path, run_folder = models_data
    
    with open(json_path, 'r') as f:
        raw_models = json.load(f)
    
    normalized_models = []
    for raw_model in raw_models:
        mapped = map_basic_properties(raw_model)
        model = MLModel(**mapped)  # Validate
        normalized_models.append(model.model_dump(mode='json'))
    
    output_path = Path(run_folder.replace("1_raw", "2_normalized")) / "mlmodels.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(normalized_models, f, indent=2)
    
    return (str(output_path), str(output_path.parent))
```

This minimal example shows the core pattern - map fields, validate with Pydantic, save to JSON.
