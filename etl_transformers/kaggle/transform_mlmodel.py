"""
Kaggle to FAIR4ML MLModel transformation functions.

This module provides modular mapping functions that transform raw Kaggle
model metadata into FAIR4ML-compliant MLModel objects.

Each mapping function handles a specific group of related properties and returns
a dictionary with the mapped fields plus extraction metadata for provenance tracking.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import logging

from etl_extractors.kaggle.kaggle_helper import KaggleHelper
from etl_transformers.common.citation_text import (
    parse_creative_work_citations_from_text,
)
from etl_transformers.common.utils import (
    extract_normalized_doi,
    build_identifier,
    build_model_urls,
    validate_optional_url,
)
from schemas.fair4ml import MLModel, ExtractionMetadata


logger = logging.getLogger(__name__)

_METHOD = "Parsed_from_Kaggle_models_json"


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
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            # Try parsing ISO format
            return datetime.fromisoformat(cleaned.replace('Z', '+00:00'))
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
    # If it's already a normal string, return it
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


def _as_str_list(value: Any, fallback: Any = None) -> List[str]:
    """
    Coerce a value into a list of non-empty strings.

    Extraction writes multi-valued fields as JSON arrays; the fallback is the
    joined display string, split on ", " only as a last resort for rows
    written before the array existed.
    """
    items = _safe_json_loads(value, default=None)
    if isinstance(items, list):
        out = [str(v).strip() for v in items if str(v).strip()]
        if out:
            return out

    text = str(fallback or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _split_reference_publication(value: Any) -> List[str]:
    """
    Split Kaggle's provenanceSources block into individual references.

    The field is free text; well-documented models use a newline-separated
    markdown list of links, while others put a sentence there. Bullet markers
    are stripped and blank lines dropped.
    """
    text = str(value or "").strip()
    if not text:
        return []
    out: List[str] = []
    for line in text.splitlines():
        cleaned = line.strip().lstrip("-*").strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _pick_archived_at(raw_archived_at: Any, fallback: str) -> str:
    """
    archivedAt is a JSON array string in the extracted data.
    Pick the first archived URL if present, otherwise fall back to `url`.
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


def normalize_citations_from_kaggle_raw(raw_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build schema.org citation dicts from a Kaggle model record.

    Kaggle has no citation field. ``provenanceSources`` is a free-text block -
    for well-documented models a newline-separated list of paper and repository
    links - and the model card itself often carries a BibTeX entry. Both are
    scanned; the shared parser only emits a CreativeWork when it finds a
    resolvable DOI, so records without one yield an empty list rather than a
    citation with no ``@id``.
    """
    parts = [
        str(raw_model.get("referencePublication", "") or "").strip(),
        str(raw_model.get("citation", "") or "").strip(),
        str(raw_model.get("intendedUse", "") or "").strip(),
    ]
    text = "\n\n".join(part for part in parts if part)
    if not text:
        return []

    return parse_creative_work_citations_from_text(
        text,
        max_works=5,
        log_context=str(raw_model.get("modelId", "")).strip() or None,
    )


def map_kaggle_basic_properties(raw_model: Dict[str, Any]) -> Dict[str, Any]:
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

    # modelCategory is List[str] in the schema. Kaggle reports the instance
    # framework here, so the structured `frameworks` array is preferred over
    # the joined `modelArchitecture` display string.
    modelCategory = _as_str_list(
        raw_model.get("frameworks"), fallback=raw_model.get("modelArchitecture")
    )
    intentedUse = str(raw_model.get("intendedUse", "")).strip()
    citation = normalize_citations_from_kaggle_raw(raw_model)

    # provenanceSources is a free-text block, often a newline-separated list
    # of paper and repository links.
    reference_publication = _split_reference_publication(
        raw_model.get("referencePublication")
    )

    date_created = str(raw_model.get("dateCreated", "")).strip()
    date_modified = str(raw_model.get("dateModified", "")).strip()
    # Kaggle returns publishTime on only a minority of records, so dateCreated
    # is usually empty while dateModified (from updateTime) is reliable. Fall
    # back to dateModified rather than leaving datePublished unset.
    date_published = (
        str(raw_model.get("datePublished", "")).strip()
        or date_created
        or date_modified
    )

    # Parse dates
    date_created = _parse_datetime(date_created)
    date_modified = _parse_datetime(date_modified)

    description = str(raw_model.get("intendedUse", "")).strip()
    readme = validate_optional_url(raw_model.get("readme_file"))
    # No network call: Kaggle serves the model card inline as the description,
    # which extraction already persisted.
    abstract = KaggleHelper.resolve_abstract_content(raw_model)
    archived_at = _pick_archived_at(raw_model.get("archivedAt"), fallback=url)

    # Optional fields (not present in the Kaggle models endpoint)
    discussion_url = str(raw_model.get("discussionUrl", "")).strip()
    issue_tracker = str(raw_model.get("issueTracker", "")).strip()

    # Total uncompressed bytes summed across the model's instances.
    memory_requirements = str(raw_model.get("contentSize", "")).strip()

    # Platform-specific counters, kept out of the FAIR fields proper.
    metrics: Dict[str, Any] = {}
    for source_key, target_key in (
        ("voteCount", "votes"),
        ("downloadCount", "downloads"),
        ("num_instances", "instances"),
    ):
        value = raw_model.get(source_key)
        if isinstance(value, (int, float)):
            metrics[target_key] = value
        elif isinstance(value, str) and value.strip().isdigit():
            metrics[target_key] = int(value.strip())

    # Build the result FIRST
    result: Dict[str, Any] = {
        "identifier": identifier,
        "name": name,
        "url": urls,
        "author": author,
        "sharedBy": shared_by,
        "modelCategory": modelCategory,
        "referencePublication": reference_publication,
        "citation": citation,
        "intendedUse": intentedUse,
        "dateCreated": date_created,
        "dateModified": date_modified,
        "datePublished": date_published,
        "description": description,
        "abstract": abstract,
        "discussionUrl": discussion_url,
        "archivedAt": archived_at,
        "readme": readme,
        "issueTracker": issue_tracker,
        "memoryRequirements": memory_requirements,
        "metrics": metrics,
        "_model_id": model_id,
    }

    # Build extraction metadata (Kaggle fields)
    result["extraction_metadata"] = {
        "identifier": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="doi, referencePublication, mlentory_id",
            notes="Contains only DOI (if present) and mlentory_id",
        ),
        "name": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="name",
            notes="Kaggle model title; fallback to modelId if missing",
        ),
        "url": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="url, mlentory_id",
            notes="Contains platform URL and MLentory UI URL",
        ),
        "author": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="author",
            notes="Parsed from JSON string; fallback to sharedBy",
        ),
        "sharedBy": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="sharedBy",
            notes="Kaggle model owner (user or organization)",
        ),
        "dateCreated": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="dateCreated",
            notes="From publishTime; absent on most Kaggle records",
        ),
        "dateModified": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="dateModified",
            notes="From updateTime",
        ),
        "datePublished": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="datePublished",
            notes="Fallback to dateCreated, then dateModified",
        ),
        "description": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="intendedUse",
            notes=None,
        ),
        "abstract": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="description",
            notes="Model card served inline by Kaggle; no separate fetch",
        ),
        "discussionUrl": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="discussionUrl",
            notes="Not returned by the Kaggle models endpoint",
        ),
        "archivedAt": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="archivedAt",
            notes="First archivedAt URL if list; fallback to url",
        ),
        "readme": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="readme_file",
            notes="Kaggle has no separate readme URL; card is inline",
        ),
        "issueTracker": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="issueTracker",
            notes="Not returned by the Kaggle models endpoint",
        ),
        "modelCategory": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="frameworks, modelArchitecture",
            notes="Kaggle reports the instance framework, not an architecture",
        ),
        "referencePublication": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="referencePublication",
            notes="Split from the provenanceSources free-text block",
        ),
        "memoryRequirements": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="contentSize",
            notes="Uncompressed bytes summed across all model instances",
        ),
        "metrics": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="voteCount, downloadCount, num_instances",
            notes="Platform-specific counters; non-FAIR extension",
        ),
        "citation": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="referencePublication, citation, intendedUse",
            notes=(
                "Parsed from provenanceSources and model card text; only DOIs "
                "yield a CreativeWork, so most Kaggle records produce none"
            ),
        ),
        "intendedUse": _create_extraction_metadata(
            method=_METHOD,
            confidence=1.0,
            source_field="intendedUse",
            notes="Kaggle model card description",
        ),
    }

    return result


def normalize_kaggle_model(raw_model: Dict[str, Any]) -> MLModel:
    """
    Normalize a raw Kaggle model record into a FAIR4ML MLModel object.

    This is the main entry point that orchestrates all mapping functions.
    Currently implements only basic properties; additional mapping functions
    will be added for keywords, licenses, frameworks, instances, etc.

    Args:
        raw_model: Dictionary containing raw Kaggle model data

    Returns:
        Validated MLModel instance

    Raises:
        ValidationError: If the mapped data doesn't conform to the schema
    """
    # Start with basic properties
    mapped_data = map_kaggle_basic_properties(raw_model)

    # TODO: Add more mapping functions:
    # - map_keywords(raw_model) for tags -> keywords
    # - map_license(raw_model) for licenses -> license
    # - map_frameworks(raw_model) for frameworks -> mlTask / softwareRequirements
    # - map_instances(raw_model) for instance entities
    # - map_lineage(raw_model) for baseModelInstanceInformation -> baseModel
    # - map_datasets(raw_model) for trainedOn -> trainingData

    # Validate and return
    return MLModel(**mapped_data)