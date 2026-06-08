"""
Map LLM-extracted schema properties onto FAIR4ML MLModel partial dicts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from etl_extractors.hf.hf_llm_schema_extractor import EXTRACTION_METADATA_KEY

LLM_PROPERTY_TO_FIELD: Dict[str, str] = {
    "fair4ml:description": "description",
    "fair4ml:modelArchitecture": "modelCategory",
    "fair4ml:domain": "domain",
    "insilico:dataSplits": "dataSplits",
    "insilico:adaptionTechniques": "adaptionTechniques",
    "fair4ml:mlTask": "mlTask",
}


def _as_metadata_entry(llm_meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "extraction_method": llm_meta.get("extraction_method", "LLM_schema_extraction"),
        "confidence": float(llm_meta.get("confidence", 0.85)),
        "source_field": llm_meta.get("source_field", "card"),
        "notes": llm_meta.get("notes"),
    }


def _append_unique_str(items: List[str], value: Any) -> None:
    text = str(value).strip()
    if text and text not in items:
        items.append(text)


def map_llm_schema_properties(
    llm_record: Dict[str, Any],
    existing_partial: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Overlay LLM schema extraction results onto an existing partial MLModel dict.

    Merge rules:
    - ``description``: LLM value wins when present
    - ``modelCategory``: LLM architecture string appended uniquely to list
    - ``domain``, ``dataSplits``, ``adaptionTechniques``: LLM value wins when present
    - ``mlTask``: keep existing HF pipeline_tag tasks; use LLM only when empty

    Args:
        llm_record: One model entry from ``llm_schema_properties.json``.
        existing_partial: Partial schema accumulated so far for the model.

    Returns:
        Dict of fields and ``extraction_metadata`` updates to merge into the model.
    """
    if not llm_record:
        return {}

    existing_partial = existing_partial or {}
    result: Dict[str, Any] = {}
    extraction_metadata: Dict[str, Any] = dict(existing_partial.get("extraction_metadata", {}))
    llm_meta_by_property = llm_record.get(EXTRACTION_METADATA_KEY, {}) or {}

    description = llm_record.get("fair4ml:description")
    if description:
        result["description"] = description
        if "fair4ml:description" in llm_meta_by_property:
            extraction_metadata["description"] = _as_metadata_entry(
                llm_meta_by_property["fair4ml:description"]
            )

    architecture = llm_record.get("fair4ml:modelArchitecture")
    if architecture:
        categories = list(existing_partial.get("modelCategory") or [])
        if not isinstance(categories, list):
            categories = [str(categories)]
        _append_unique_str(categories, architecture)
        result["modelCategory"] = categories
        if "fair4ml:modelArchitecture" in llm_meta_by_property:
            extraction_metadata["modelCategory"] = _as_metadata_entry(
                llm_meta_by_property["fair4ml:modelArchitecture"]
            )

    for llm_property in ("fair4ml:domain", "insilico:dataSplits", "insilico:adaptionTechniques"):
        value = llm_record.get(llm_property)
        if not value:
            continue
        field_name = LLM_PROPERTY_TO_FIELD[llm_property]
        result[field_name] = value
        if llm_property in llm_meta_by_property:
            extraction_metadata[field_name] = _as_metadata_entry(
                llm_meta_by_property[llm_property]
            )

    existing_tasks = existing_partial.get("mlTask") or []
    if not isinstance(existing_tasks, list):
        existing_tasks = [str(existing_tasks)] if existing_tasks else []
    llm_task = llm_record.get("fair4ml:mlTask")
    if llm_task and not existing_tasks:
        result["mlTask"] = [str(llm_task)]
        if "fair4ml:mlTask" in llm_meta_by_property:
            extraction_metadata["mlTask"] = _as_metadata_entry(
                llm_meta_by_property["fair4ml:mlTask"]
            )

    if extraction_metadata:
        result["extraction_metadata"] = extraction_metadata

    return result
