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


def _strip_frontmatter(text: str) -> str:
    """
    Remove YAML frontmatter from markdown text.
    
    Args:
        text: Markdown text potentially with frontmatter
        
    Returns:
        Text with frontmatter removed
    """
    if not isinstance(text, str):
        return ""
    
    # Remove --- ... --- frontmatter block
    return re.sub(r'^---.*?---\s*', '', text, count=1, flags=re.DOTALL)


def _extract_model_name(model_id: str) -> str:
    """
    Extract model name from model ID.
    
    Args:
        model_id: Full model ID (e.g., "author/model-name")
        
    Returns:
        Model name (e.g., "model-name")
    """
    if not model_id:
        return ""
    
    # Split on "/" and take the last part
    return model_id.split("/")[-1] if "/" in model_id else model_id


def map_basic_properties(raw_model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map basic identification, temporal, and URL properties from HF to FAIR4ML.
    
    This function handles:
    - Core identification: modelId → identifier, name, url
    - Temporal fields: createdAt, last_modified → dateCreated, dateModified, datePublished
    - Authorship: author → author, sharedBy
    - URLs: Generate HuggingFace-specific URLs for discussions, readme, etc.
    - Description: Strip frontmatter from card
    
    Args:
        raw_model: Dictionary containing raw HuggingFace model data
        
    Returns:
        Dictionary with mapped fields and extraction_metadata
    """
    model_id = raw_model.get("modelId", "")
    mlentory_id = raw_model.get("mlentory_id", "")
    if not mlentory_id:
        mlentory_id = HFHelper.generate_mlentory_entity_hash_id('Model', model_id)
    author = raw_model.get("author", "")
    created_at = raw_model.get("createdAt")
    last_modified = raw_model.get("last_modified")
    card = raw_model.get("card", "")
    
    # Parse dates
    date_created = _parse_datetime(created_at)
    date_modified = _parse_datetime(last_modified)
    
    # Build HuggingFace URLs
    hf_base_url = f"https://huggingface.co/{model_id}" if model_id else None
    discussion_url = f"{hf_base_url}/discussions" if hf_base_url else None
    readme_url = f"{hf_base_url}/blob/main/README.md" if hf_base_url else None
    
    # Extract clean description
    description = _strip_frontmatter(card) if card else None
    
    # Build result with mapped fields
    result = {
        # Core identification
        "identifier": [hf_base_url or model_id, mlentory_id],
        "name": _extract_model_name(model_id),
        "url": hf_base_url or "",
        
        # Authorship
        "author": author,
        "sharedBy": author,  # In HF, the author is typically who shared it
        
        # Temporal
        "dateCreated": date_created,
        "dateModified": date_modified,
        "datePublished": date_created,  # Use creation date as publication date
        
        # Description
        "description": description,
        
        # Additional URLs
        "discussionUrl": discussion_url,
        "archivedAt": hf_base_url,  # HF serves as archive
        "readme": readme_url,
        "issueTracker": discussion_url,  # HF uses discussions for issues
    }
    
    # Build extraction metadata for each field
    extraction_metadata = {
        "identifier": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=1.0,
            source_field="modelId",
            notes="Converted to HuggingFace URL format and mlentory_id"
        ),
        "name": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=1.0,
            source_field="modelId",
            notes="Extracted from modelId (last component after /)"
        ),
        "url": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=1.0,
            source_field="modelId",
            notes="Generated HuggingFace model URL"
        ),
        "author": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=1.0,
            source_field="author"
        ),
        "sharedBy": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=1.0,
            source_field="author",
            notes="Assumed author is the one who shared the model"
        ),
        "dateCreated": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=1.0,
            source_field="createdAt"
        ),
        "dateModified": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=1.0,
            source_field="last_modified"
        ),
        "datePublished": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=1.0,
            source_field="createdAt",
            notes="Using createdAt as publication date"
        ),
        "description": _create_extraction_metadata(
            method="Parsed_from_HF_dataset",
            confidence=0.9,
            source_field="card",
            notes="Extracted from model card with frontmatter removed"
        ),
        "discussionUrl": _create_extraction_metadata(
            method="Generated_from_HF_modelId",
            confidence=1.0,
            source_field="modelId",
            notes="Generated HuggingFace discussions URL"
        ),
        "archivedAt": _create_extraction_metadata(
            method="Generated_from_HF_modelId",
            confidence=1.0,
            source_field="modelId",
            notes="HuggingFace serves as archive location"
        ),
        "readme": _create_extraction_metadata(
            method="Generated_from_HF_modelId",
            confidence=1.0,
            source_field="modelId",
            notes="Generated HuggingFace README URL"
        ),
        "issueTracker": _create_extraction_metadata(
            method="Generated_from_HF_modelId",
            confidence=1.0,
            source_field="modelId",
            notes="HuggingFace uses discussions for issue tracking"
        ),
    }
    
    result["extraction_metadata"] = extraction_metadata
    return result
                

def normalize_hf_model(raw_model: Dict[str, Any]) -> MLModel:
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
    mapped_data = map_basic_properties(raw_model)
    
    # Add platform-specific metrics (non-FAIR extension)
    mapped_data["metrics"] = {
        "downloads": raw_model.get("downloads", 0),
        "likes": raw_model.get("likes", 0),
    }
    
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

def is_language_code(code: str) -> bool:
    """
    Check if a code is a valid language code.
    
    Args:
        code: Language code to check
        
    Returns:
        True if the code is a valid language code, False otherwise
    """
    return (pycountry.languages.get(alpha_2=code) or
            pycountry.languages.get(alpha_3=code)) is not None