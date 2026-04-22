"""
AI4Life to FAIR4ML MLModel transformation functions.

This module provides modular mapping functions that transform raw HuggingFace
model metadata into FAIR4ML-compliant MLModel objects.

Each mapping function handles a specific group of related properties and returns
a dictionary with the mapped fields plus extraction metadata for provenance tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional
import logging
from etl_extractors.ai4life.ai4life_helper import AI4LifeHelper
import pycountry
import json
from typing import Any, List, Dict
from etl_transformers.common.utils import (
    extract_normalized_doi,
    build_identifier,
    build_model_urls,
)
from schemas.fair4ml import MLModel, ExtractionMetadata


logger = logging.getLogger(__name__)


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
    

def _safe_json_loads(value: Any, default: Any):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        try:
            return json.loads(s)
        except Exception:
            return default
    return default


def _pick_first_author_name(raw_author_field: Any) -> str:
    # If it’s already a normal string, return it
    if isinstance(raw_author_field, str):
        s = raw_author_field.strip()
        # If it looks like JSON, try to parse; otherwise treat it as the author name
        if not s.startswith("[") and not s.startswith("{"):
            return s

    authors = _safe_json_loads(raw_author_field, default=[])

    # Some sources might give dict instead of list
    if isinstance(authors, dict):
        name = str(authors.get("name", "")).strip()
        return name

    if isinstance(authors, list) and authors:
        a0 = authors[0]
        if isinstance(a0, dict):
            return str(a0.get("name", "")).strip()
        if isinstance(a0, str):
            return a0.strip()

    return ""


def _pick_archived_at(raw_archived_at: Any, fallback: str) -> str:
    """
    archivedAt is a JSON array string in your data.
    The HF example uses a single URL string.
    We'll pick the first archived URL if present, otherwise fallback to `url`.
    """
    items = _safe_json_loads(raw_archived_at, default=[])
    if isinstance(items, list):
        for it in items:
            if isinstance(it, str) and it.strip():
                return it.strip()
            if isinstance(it, dict):
                u = it.get("url") or it.get("href")
                if isinstance(u, str) and u.strip():
                    return u.strip()
    return fallback


# def _build_extraction_metadata(
#     source_map: Dict[str, str],
#     method: str = "Parsed_from_AI4Life_models_json",
#     confidence: float = 1.0,
# ) -> Dict[str, Dict[str, Any]]:
#     notes_map = notes_map or {}
#     meta: Dict[str, Dict[str, Any]] = {}
#     for field, source_field in source_map.items():
#         meta[field] = {
#             "extraction_method": method,
#             "confidence": confidence,
#             "source_field": source_field,
#             "notes": None,
#         }
#     return meta


def map_ai4life_basic_properties(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    model_id = str(raw_model.get("modelId", "")).strip()
    url = str(raw_model.get("url", "")).strip()
    mlentory_id = str(raw_model.get("mlentory_id", "")).strip()

    doi = extract_normalized_doi(
        raw_record=raw_model,
        candidate_fields=("doi", "DOI", "referencePublication", "reference_publication"),
    )
    identifier: List[str] = build_identifier(doi=doi, mlentory_id=mlentory_id)
    urls: List[str] = build_model_urls(platform_url=url, mlentory_id=mlentory_id)

    name = str(raw_model.get("name", "")).strip() or model_id
    shared_by = str(raw_model.get("sharedBy", "")).strip()
    author = _pick_first_author_name(raw_model.get("author")) or shared_by
    
    modelCategory = str(raw_model.get("modelArchitecture", "")).strip()
    referencePublication = str(raw_model.get("referencePublication", "")).strip()
    intentedUse = str(raw_model.get("intendedUse", "")).strip()

    date_created = str(raw_model.get("dateCreated", "")).strip()
    date_modified = str(raw_model.get("dateModified", "")).strip()
    date_published = str(raw_model.get("datePublished", "")).strip() or date_created
    
    # Parse dates
    date_created = _parse_datetime(date_created)
    date_modified = _parse_datetime(date_modified)

    description = str(raw_model.get("intendedUse", "")).strip()
    readme = str(raw_model.get("readme_file", "")).strip()
    archived_at = _pick_archived_at(raw_model.get("archivedAt"), fallback=url)

    # Optional fields (often missing in AI4Life)
    discussion_url = str(raw_model.get("discussionUrl", "")).strip()
    issue_tracker = str(raw_model.get("issueTracker", "")).strip()

    # Build the result FIRST
    result: Dict[str, Any] = {
        "identifier": identifier,
        "name": name,
        "url": urls,
        "author": author,
        "sharedBy": shared_by,
        "modelCategory": modelCategory,
        "referencePublication": referencePublication,
        "intendedUse":intentedUse,
        "dateCreated": date_created,
        "dateModified": date_modified,
        "datePublished": date_published,
        "description": description,
        "discussionUrl": discussion_url,
        "archivedAt": archived_at,
        "readme": readme,
        "issueTracker": issue_tracker,
        "_model_id": model_id,
    }

    # Build extraction metadata (AI4Life fields, not HF)
    result["extraction_metadata"] = {
        "identifier": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="doi, referencePublication, mlentory_id",
            notes="Contains only DOI (if present) and mlentory_id",
        ),
        "name": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="name",
            notes="Fallback to modelId if missing",
        ),
        "url": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="url, mlentory_id",
            notes="Contains platform URL and MLentory UI URL",
        ),
        "author": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="author",
            notes="Parsed from JSON string; fallback to sharedBy",
        ),
        "sharedBy": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="sharedBy",
            notes=None,
        ),
        "dateCreated": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="dateCreated",
            notes=None,
        ),
        "dateModified": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="dateModified",
            notes=None,
        ),
        "datePublished": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="datePublished",
            notes="Fallback to dateCreated if missing",
        ),
        "description": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="intendedUse",
            notes=None,
        ),
        "discussionUrl": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="discussionUrl",
            notes="Often missing in AI4Life",
        ),
        "archivedAt": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="archivedAt",
            notes="First archivedAt URL if list; fallback to url",
        ),
        "readme": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="readme_file",
            notes=None,
        ),
        "issueTracker": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="issueTracker",
            notes="Often missing in AI4Life",
        ),
        "modelCategory": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="modelCategory",
            notes="Often missing in AI4Life",
        ),
        "referencePublication": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="referencePublication",
            notes="Often missing in AI4Life",
        ),
        "intendedUse": _create_extraction_metadata(
            method="Parsed_from_AI4Life_models_json",
            confidence=1.0,
            source_field="intentedUse",
            notes="Often missing in AI4Life",
        ),
    }

    return result

def normalize_ai4life_model(raw_model: Dict[str, Any]) -> MLModel:
    """
    Normalize a raw HuggingFace model record into a FAIR4ML MLModel object.
    
    This is the main entry point that orchestrates all mapping functions.
    Currently implements only basic properties; additional mapping functions
    will be added for tags, lineage, datasets, etc.
    
    Args:
        raw_model: Dictionary containing raw HuggingFace model data
        
    Returns:
        Validated MLModel instance
        
    Raises:
        ValidationError: If the mapped data doesn't conform to the schema
    """
    # Start with basic properties
    mapped_data = map_ai4life_basic_properties(raw_model)
    
   
    
    # TODO: Add more mapping functions:
    # - map_keywords_and_language(raw_model) for tags → keywords, inLanguage
    # - map_task_and_category(raw_model) for pipeline_tag, library_name → mlTask, modelCategory
    # - map_license(raw_model) for license extraction
    # - map_lineage(raw_model) for base_model → fineTunedFrom
    # - map_code_and_usage(raw_model) for code snippets and usage instructions
    # - map_datasets(raw_model) for trainedOn, evaluatedOn, etc.
    # - map_ethics_and_risks(raw_model) for limitations, biases, etc.
    
    # Validate and return
    return MLModel(**mapped_data)