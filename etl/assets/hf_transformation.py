"""
Dagster assets for HuggingFace → FAIR4ML transformation.

Pipeline:
1) Read raw HF models from extraction (hf_models_with_ancestors.json)
2) Create separate assets for each property group:
   - hf_extract_basic_properties: Core identification, temporal, URLs
   - hf_extract_keywords_language: Tags → keywords, inLanguage
   - hf_extract_task_category: pipeline_tag, library_name → mlTask, modelCategory
   - hf_extract_license: License information
   - hf_extract_lineage: Base model relationships
   - hf_extract_code_usage: Code snippets and usage instructions
   - hf_extract_datasets: Training/evaluation datasets
   - hf_extract_ethics_risks: Limitations, biases, ethical considerations
3) Merge all partial schemas in hf_models_normalized
4) Validate with Pydantic
5) Write normalized models to /data/normalized/hf/<timestamp_uuid>/mlmodels.json
"""

from __future__ import annotations

import json
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Any
import logging

import pandas as pd
from pydantic import BaseModel, ValidationError

from dagster import asset, AssetIn

from etl_transformers.hf.transform_mlmodel import map_basic_properties
from schemas.fair4ml import MLModel


logger = logging.getLogger(__name__)


def _json_default(o):
    """Non-recursive JSON serializer for known non-serializable types."""
    if isinstance(o, BaseModel):
        return o.model_dump(mode='json')
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return list(o)
    if isinstance(o, tuple):
        return list(o)
    return str(o)

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
    normalized_base = Path("/data/normalized/hf")
    normalized_run_folder = normalized_base / raw_folder_name
    normalized_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created normalized run folder: {normalized_run_folder}")
    return (str(raw_data_json_path), str(normalized_run_folder))


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

@asset(
    group_name="hf_transformation",
    ins={
        "models_data": AssetIn("hf_normalized_run_folder"),
        "basic_properties": AssetIn("hf_extract_basic_properties"),
        # TODO: Add more partial schema inputs as we implement them:
        # "keywords_language": AssetIn("hf_extract_keywords_language"),
        # "task_category": AssetIn("hf_extract_task_category"),
        # "license_data": AssetIn("hf_extract_license"),
        # "lineage": AssetIn("hf_extract_lineage"),
        # "code_usage": AssetIn("hf_extract_code_usage"),
        # "datasets": AssetIn("hf_extract_datasets"),
        # "ethics_risks": AssetIn("hf_extract_ethics_risks"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_models_normalized(
    models_data: Tuple[str, str],
    basic_properties: str,
) -> Tuple[str, str]:
    """
    Merge partial schemas and create final FAIR4ML MLModel objects.
    
    This asset aggregates all partial property extractions, merges them by model,
    validates against Pydantic schema, and writes the final normalized models.
    
    Args:
        models_data: Tuple of (raw_data_json_path, normalized_folder)
        basic_properties: Path to basic properties partial schema
        
        
    Returns:
        Path to the saved normalized models JSON file
    """
    raw_data_json_path, normalized_folder = models_data
    
    # Load raw models for reference
    logger.info(f"Loading raw models from {raw_data_json_path}")
    with open(raw_data_json_path, 'r', encoding='utf-8') as f:
        raw_models = json.load(f)
    
    logger.info(f"Loaded {len(raw_models)} raw models")
    
    # Load all partial schemas
    logger.info("Loading partial schemas...")
    
    with open(basic_properties, 'r', encoding='utf-8') as f:
        basic_props = json.load(f)
    
    # TODO: Load additional partial schemas as they are implemented
    # with open(keywords_language, 'r', encoding='utf-8') as f:
    #     keywords_lang = json.load(f)
    # with open(task_category, 'r', encoding='utf-8') as f:
    #     task_cat = json.load(f)
    # ... etc
    
    logger.info(f"Loaded {len(basic_props)} basic property schemas")
    
    # Create index mapping for efficient merging
    basic_props_by_index = {item["_index"]: item for item in basic_props}
    # TODO: Create indices for other partial schemas
    
    # Merge partial schemas
    logger.info("Merging partial schemas...")
    merged_schemas: List[Dict[str, Any]] = []
    
    for idx, raw_model in enumerate(raw_models):
        model_id = raw_model.get("modelId", f"unknown_{idx}")
        
        try:
            # Start with basic properties
            merged = basic_props_by_index.get(idx, {}).copy()
            
            # Remove internal fields used for merging
            merged.pop("_model_id", None)
            merged.pop("_index", None)
            merged.pop("_error", None)
            
            # TODO: Merge additional partial schemas
            # Merge keywords & language
            # if idx in keywords_lang_by_index:
            #     kw_data = keywords_lang_by_index[idx]
            #     merged["keywords"] = kw_data.get("keywords", [])
            #     merged["inLanguage"] = kw_data.get("inLanguage", [])
            #     # Merge extraction_metadata
            #     merged["extraction_metadata"].update(kw_data.get("extraction_metadata", {}))
            
            # Add platform-specific metrics
            merged["metrics"] = {
                "downloads": raw_model.get("downloads", 0),
                "likes": raw_model.get("likes", 0),
            }
            
            merged_schemas.append(merged)
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Merged schemas for {idx + 1}/{len(raw_models)} models")
                
        except Exception as e:
            logger.error(f"Error merging schemas for model {model_id}: {e}", exc_info=True)
    
    logger.info(f"Merged {len(merged_schemas)} schemas")
    
    # Validate and create MLModel instances
    logger.info("Validating merged schemas...")
    normalized_models: List[Dict[str, Any]] = []
    validation_errors: List[Dict[str, Any]] = []
    
    for idx, merged_data in enumerate(merged_schemas):
        model_id = merged_data.get("identifier", f"unknown_{idx}")
        
        try:
            # Validate with Pydantic
            
            logger.info(f"Merged data: {merged_data}")
            logger.info(f"Merged data type: {type(merged_data)}")
            
            mlmodel = MLModel(**merged_data)
            
            # Convert to dict for JSON serialization
            normalized_models.append(mlmodel.model_dump(mode='json'))
            
            if (idx + 1) % 100 == 0:
                logger.info(f"Validated {idx + 1}/{len(merged_schemas)} models")
                
        except ValidationError as e:
            logger.error(f"Validation error for model {model_id}: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            validation_errors.append({
                "modelId": model_id,
                "error": str(e),
                "merged_data": merged_data
            })
        except Exception as e:
            logger.error(f"Unexpected error validating model {model_id}: {e}", exc_info=True)
            validation_errors.append({
                "modelId": model_id,
                "error": str(e),
                "error_type": type(e).__name__
            })
    
    logger.info(f"Successfully validated {len(normalized_models)}/{len(merged_schemas)} models")
    
    if validation_errors:
        logger.warning(f"Encountered {len(validation_errors)} validation errors")
    
    # Write normalized models
    output_path = Path(normalized_folder) / "mlmodels.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(normalized_models, f, indent=2, ensure_ascii=False, default=str)
    
    logger.info(f"Wrote {len(normalized_models)} normalized models to {output_path}")
    
    # Write errors if any
    if validation_errors:
        errors_path = Path(normalized_folder) / "transformation_errors.json"
        with open(errors_path, 'w', encoding='utf-8') as f:
            json.dump(validation_errors, f, indent=2, ensure_ascii=False)
        logger.info(f"Wrote {len(validation_errors)} errors to {errors_path}")
    
    return (str(output_path), str(normalized_folder))

