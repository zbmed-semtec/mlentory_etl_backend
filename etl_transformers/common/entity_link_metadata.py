"""
Extraction metadata for model fields populated via entity linking.

When enriched entities (license, keywords, tasks, …) are merged onto an MLModel,
the metadata graph needs per-field ``extraction_method`` values. Without them,
``metadata_graph`` falls back to ``unknown``.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


def _entry(
    method: str,
    *,
    source_field: str,
    confidence: float = 1.0,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "extraction_method": method,
        "confidence": confidence,
        "source_field": source_field,
    }
    if notes:
        data["notes"] = notes
    return data


# Field → metadata for Hugging Face entity-linking merge (merge_model_partial_schemas).
HF_ENTITY_LINK_METADATA: Dict[str, Dict[str, Any]] = {
    "license": _entry("SPDX_API", source_field="license"),
    "source": _entry(
        "HF_catalog_website",
        source_field="sources",
        notes="Hugging Face catalog WebSite IRI",
    ),
    "evaluatedOn": _entry("HF_Croissant_endpoint", source_field="datasets"),
    "keywords": _entry(
        "Wikidata API + Semantic Search",
        source_field="keywords",
        notes="Keyword IRIs from HF enrichment (also Curated CSV / Wikidata API per term)",
    ),
    "baseModel": _entry(
        "HF_model_card_tags",
        source_field="tags",
        notes="From base_model: tags in model card",
    ),
    "supportedLanguages": _entry(
        "pycountry",
        source_field="tags",
        notes="Language tags mapped via pycountry",
    ),
    "inLanguage": _entry(
        "lingua-language-detector+pycountry",
        source_field="card",
        notes="Readme language detection",
    ),
    "mlTask": _entry("catalog_csv", source_field="pipeline_tag"),
    "sharedBy": _entry("hf_sharedby_identifier", source_field="sharedBy"),
}

# Field → metadata for AI4Life entity-linking merge (merge_ai4life_partial_schemas).
AI4LIFE_ENTITY_LINK_METADATA: Dict[str, Dict[str, Any]] = {
    "license": _entry("Hypha API", source_field="license"),
    "source": _entry(
        "AI4Life_catalog_website",
        source_field="sources",
        notes="AI4Life catalog WebSite IRI",
    ),
    "evaluatedOn": _entry("Hypha API", source_field="datasets"),
    "keywords": _entry("Hypha API", source_field="keywords"),
    "mlTask": _entry("ai4life_task_identifier", source_field="tasks"),
    "sharedBy": _entry("ai4life_sharedby_identifier", source_field="sharedBy"),
    "inLanguage": _entry(
        "lingua-language-detector+pycountry",
        source_field="documentation_content",
        notes="Readme/documentation language detection",
    ),
}

# Field → metadata for Kaggle entity-linking merge (merge_kaggle_partial_schemas).
# Paste into etl_transformers/common/entity_link_metadata.py alongside the
# HF and AI4Life dicts, then register it in _PLATFORM_METADATA below.
KAGGLE_ENTITY_LINK_METADATA: Dict[str, Dict[str, Any]] = {
    "license": _entry(
        "kaggle_license_identifier",
        source_field="licenses",
        notes="License is declared per model instance, not per model",
    ),
    "source": _entry(
        "Kaggle_catalog_website",
        source_field="sources",
        notes="Kaggle catalog WebSite IRI",
    ),
    "keywords": _entry(
        "Kaggle_models_endpoint",
        source_field="keywords",
        notes="Curated Kaggle tags; sparse coverage across the catalog",
    ),
    "modelCategory": _entry(
        "kaggle_framework_identifier",
        source_field="frameworks",
        notes="Framework names read from instance URLs (PyTorch, Keras, …)",
    ),
}
 
 
# Add "kaggle" to the existing registry:
_PLATFORM_METADATA: Dict[str, Dict[str, Dict[str, Any]]] = {
    "hf": HF_ENTITY_LINK_METADATA,
    "ai4life": AI4LIFE_ENTITY_LINK_METADATA,
    "kaggle": KAGGLE_ENTITY_LINK_METADATA,
}


def _field_has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, str):
        return bool(value.strip())
    return True


def apply_entity_link_extraction_metadata(
    merged: Dict[str, Any],
    platform: str,
    linked_fields: Iterable[str],
) -> None:
    """
    Attach extraction metadata for model fields set from entity linking.

    Mutates ``merged`` in place under the ``extraction_metadata`` key.
    """
    catalog = _PLATFORM_METADATA.get(platform)
    if catalog is None:
        raise ValueError(f"Unknown platform for entity-link metadata: {platform}")

    meta = dict(merged.get("extraction_metadata") or {})
    for field in linked_fields:
        template = catalog.get(field)
        if not template:
            continue
        if not _field_has_value(merged.get(field)):
            continue
        meta[field] = dict(template)

    if meta:
        merged["extraction_metadata"] = meta
