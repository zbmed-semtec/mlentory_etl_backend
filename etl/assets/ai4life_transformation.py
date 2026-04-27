"""
Dagster assets for AI4Life → FAIR4ML transformation.

Pipeline:
1) Read raw AI4Life models from extraction (models.json)
2) Create separate assets for each property group:
    - mlmodels.json       (FAIR4ML MLModel)
    - entity_linking.json (linkage of flow → datasets/license/keywords)
    
"""
from __future__ import annotations

import json
import traceback
import uuid
from datetime import datetime,timezone
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional, Callable
import logging
import pandas as pd
from pydantic import BaseModel, ValidationError
from dagster import asset, AssetIn
from etl_extractors.hf import HFHelper
from etl_extractors.ai4life.ai4life_helper import AI4LifeHelper
from etl_transformers.ai4life.transform_mlmodel import map_ai4life_basic_properties
from schemas.fair4ml import MLModel
from schemas.schemaorg import ScholarlyArticle, CreativeWork, DefinedTerm, Language
from schemas.croissant import CroissantDataset


logger = logging.getLogger(__name__)


def _json_default(o):
    """Non-recursive JSON serializer for known non-serializable types."""
    if isinstance(o, BaseModel):
        return o.model_dump(mode='json', by_alias=True)
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return list(o)
    if isinstance(o, tuple):
        return list(o)
    return str(o)


def _load_json(path: str) -> Any:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Expected JSON file not found: %s", path)
        return None
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
    
def _write_normalization_results(
    entity_label: str,
    normalized_folder: str,
    normalized_records: List[Dict[str, Any]],
    validation_errors: List[Dict[str, Any]],
) -> str:
    """
    Persist normalized entity data and optional validation errors to disk.

    Args:
        entity_label: Lowercase entity name used for filenames and logging.
        normalized_folder: Destination folder for normalized outputs.
        normalized_records: Validated records ready for serialization.
        validation_errors: Validation errors encountered during processing.

    Returns:
        The string path to the primary normalized JSON file.
    """
    folder_path = Path(normalized_folder)
    output_path = folder_path / f"{entity_label}.json"
    with open(output_path, "w", encoding="utf-8") as file_handle:
        json.dump(
            normalized_records,
            file_handle,
            indent=2,
            ensure_ascii=False,
            default=_json_default,
        )

    logger.info("Wrote %s normalized %s to %s", len(normalized_records), entity_label, output_path)

    if validation_errors:
        errors_path = folder_path / f"{entity_label}_transformation_errors.json"
        with open(errors_path, "w", encoding="utf-8") as file_handle:
            json.dump(validation_errors, file_handle, indent=2, ensure_ascii=False)
        logger.info("Wrote %s %s normalization errors to %s", len(validation_errors), entity_label, errors_path)

    return str(output_path)

    
# ---------- normalized folder ----------

@asset(
    group_name="ai4life_transformation",
    ins={"models_data": AssetIn("ai4life_models_raw")},
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_normalized_model_folder(models_data: Tuple[str, str]) -> Tuple[str, str]:
    """
    Create normalized run folder mirroring raw run folder name.
    """
    raw_data_json_path, raw_run_folder = models_data
    
    # Extract timestamp and run_id from raw folder name
    raw_folder_name = Path(raw_run_folder).name  # e.g., "2025-10-30_16-45-38_a510a3c3"
    
    # unique per run
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]

    # Create corresponding normalized folder
    normalized_base = Path("/data/2_normalized/ai4life")
    normalized_run_folder = normalized_base / f"{timestamp}_{run_id}"
    normalized_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created normalized run folder: {normalized_run_folder}")
    return (str(raw_data_json_path), str(normalized_run_folder))

@asset(
    group_name="ai4life_transformation",
    ins={"models_data": AssetIn("ai4life_normalized_model_folder")},
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_extract_basic_properties(models_data: Tuple[str, str]) -> str:
    """
    Produces FAIR4ML-style partial_basic_properties.json for AI4Life models.

    Input:  (raw_models_json_path, normalized_folder)
    Output: <normalized_folder>/partial_basic_properties.json
    """
    raw_models_json_path, normalized_folder = models_data

    logger.info("Loading raw models from %s", raw_models_json_path)
    with open(raw_models_json_path, "r", encoding="utf-8") as f:
        raw_payload = json.load(f)

    if isinstance(raw_payload, list):
        raw_models = raw_payload
    elif isinstance(raw_payload, dict):
        raw_models = raw_payload.get("models") or raw_payload.get("data") or raw_payload.get("items") or []
    else:
        raw_models = []

    if not isinstance(raw_models, list):
        raise ValueError(f"Expected list of models, got: {type(raw_models).__name__}")

    logger.info("Loaded %d raw models", len(raw_models))

    out: List[Dict[str, Any]] = []

    for idx, raw_model in enumerate(raw_models):
        model_id = ""
        if isinstance(raw_model, dict):
            model_id = str(raw_model.get("modelId", "")).strip()
        if not model_id:
            model_id = f"unknown_{idx}"

        # If it isn't a dict, emit a minimal record (keeps pipeline robust)
        if not isinstance(raw_model, dict):
            out.append(
                {
                    "identifier": [],
                    "name": model_id,
                    "url": "",
                    "author": "",
                    "sharedBy": "",
                    "modelCategory":"",
                    "referencePublication":"",
                    "intentedUse": "",
                    "dateCreated": "",
                    "dateModified": "",
                    "datePublished": "",
                    "description": "",
                    "discussionUrl": "",
                    "archivedAt": "",
                    "readme": "",
                    "issueTracker": "",
                    "extraction_metadata": {},
                    "_model_id": model_id,
                    "_index": idx,
                    "_error": f"Model is not a dict: {type(raw_model).__name__}",
                }
            )
            continue

        try:
            mapped = map_ai4life_basic_properties(raw_model)

            # Always attach index
            mapped["_index"] = idx

            # Ensure _model_id exists for downstream merging/debug
            mapped["_model_id"] = mapped.get("_model_id") or model_id

            # Ensure extraction_metadata key exists (mapper should provide it)
            if "extraction_metadata" not in mapped or mapped["extraction_metadata"] is None:
                mapped["extraction_metadata"] = {}

            out.append(mapped)

            if (idx + 1) % 200 == 0:
                logger.info("Extracted basic properties for %d/%d models", idx + 1, len(raw_models))

        except Exception as e:
            logger.error("Error extracting basic properties for %s: %s", model_id, e, exc_info=True)

            # Fallback record (no metadata, because mapping failed)
            out.append(
                {
                    "identifier": [
                        str(raw_model.get("url", "")).strip(),
                        str(raw_model.get("mlentory_id", "")).strip(),
                    ],
                    "name": str(raw_model.get("name", "")).strip() or model_id,
                    "url": str(raw_model.get("url", "")).strip(),
                    "author": "",
                    "sharedBy": str(raw_model.get("sharedBy", "")).strip(),
                    "modelCategory": str(raw_model.get("modelArchitecture", "")).strip(),
                    "referencePublication": str(raw_model.get("referencePublication", "")).strip(),
                    "intentedUse": str(raw_model.get("intendedUse", "")).strip(),
                    "dateCreated": str(raw_model.get("dateCreated", "")).strip(),
                    "dateModified": str(raw_model.get("dateModified", "")).strip(),
                    "datePublished": str(raw_model.get("datePublished", "")).strip()
                                   or str(raw_model.get("dateCreated", "")).strip(),
                    "description": str(raw_model.get("intendedUse", "")).strip(),
                    "discussionUrl": str(raw_model.get("discussionUrl", "")).strip(),
                    "archivedAt": str(raw_model.get("url", "")).strip(),
                    "readme": str(raw_model.get("readme_file", "")).strip(),
                    "issueTracker": str(raw_model.get("issueTracker", "")).strip(),
                    "extraction_metadata": {},
                    "_model_id": model_id,
                    "_index": idx,
                    "_error": str(e),
                }
            )

    output_path = Path(normalized_folder) / "partial_basic_properties.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # IMPORTANT: _json_default must serialize pydantic BaseModel (ExtractionMetadata) via model_dump()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=_json_default)

    logger.info("Saved basic properties to %s", output_path)
    return str(output_path)


@asset(
    group_name="ai4life_transformation",
    ins={"run_folder_data": AssetIn("ai4life_normalized_model_folder")},
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_sources_normalized(run_folder_data: Tuple[str, str]) -> str:
    """
    Bring the AI4Life catalog ``WebSite`` from raw extract into this run's
    normalized folder as ``sources.json``.
    """
    raw_models_path, normalized_folder = run_folder_data
    raw_run = Path(raw_models_path).parent
    raw_sources = raw_run / "sources.json"
    out_path = Path(normalized_folder) / "sources.json"

    if raw_sources.exists():
        with open(raw_sources, "r", encoding="utf-8") as f:
            payload = json.load(f)
        logger.info("Loaded AI4Life catalog sources from raw run: %s", raw_sources)
    else:
        logger.warning(
            "Raw sources.json missing at %s; using AI4LifeHelper catalog payload",
            raw_sources,
        )
        payload = AI4LifeHelper.raw_ai4life_catalog_website_records()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=_json_default)

    logger.info("Wrote normalized AI4Life sources to %s", out_path)
    return str(out_path)

@asset(
    group_name="ai4life_transformation",
    ins={
        "datasets_mapping": AssetIn("ai4life_identified_datasets"),
        "keywords_mapping": AssetIn("ai4life_identified_keywords"),
        "licenses_mapping": AssetIn("ai4life_identified_licenses"),
        "tasks_mapping": AssetIn("ai4life_identified_tasks"),
        "sharedby_mapping": AssetIn("ai4life_identified_sharedby"),
        "run_folder_data": AssetIn("ai4life_normalized_model_folder"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "transform"}
)
def ai4life_entity_linking(
    datasets_mapping: Dict[str, List[str]],
    keywords_mapping: Dict[str, List[str]],
    licenses_mapping: Dict[str, List[str]],
    tasks_mapping: Dict[str, List[str]],
    sharedby_mapping: Dict[str, List[str]],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Create entity linking mapping: model_id -> {datasets, keywords, licenses, tasks, sharedby, sources}
    Links identified entities with their enriched metadata.

    Args:
        datasets_mapping: Tuple of ({model_id: [dataset_names]}, run_folder)
        keywords_mapping: Tuple of ({model_id: [keywords]}, run_folder)
        licenses_mapping: Tuple of ({model_id: [license_ids]}, run_folder)
        tasks_mapping: Tuple of ({model_id: [task_ids]}, run_folder)
        sharedby_mapping: Tuple of ({model_id: [sharedby_entities]}, run_folder)
        run_folder_data: Tuple of (models_json_path, normalized_folder)

    Returns:
        Path to saved entity linking JSON file
    """
    _, normalized_folder = run_folder_data
    ai4life_catalog_source_iris: List[str] = []
    for row in AI4LifeHelper.raw_ai4life_catalog_website_records():
        ids = row.get("https://schema.org/identifier") or []
        if not isinstance(ids, list):
            continue
        ai4life_catalog_source_iris = [
            u
            for u in ids
            if isinstance(u, str)
            and u.startswith("https://w3id.org/mlentory/mlentory_graph/")
        ]
        if ai4life_catalog_source_iris:
            break

        # union of ids so you don't KeyError if a model appears in only one mapping
    all_model_ids = (
        set(datasets_mapping.keys())
        | set(keywords_mapping.keys())
        | set(licenses_mapping.keys())
        | set(tasks_mapping.keys())
        | set(sharedby_mapping.keys())
    )

    entity_linking: Dict[str, Dict[str, List[str]]] = {}

    for model_id in all_model_ids:
        datasets = datasets_mapping.get(model_id, []) or []
        keywords = keywords_mapping.get(model_id, []) or []
        licenses = licenses_mapping.get(model_id, []) or []
        tasks = tasks_mapping.get(model_id, []) or []
        sharedby = sharedby_mapping.get(model_id, []) or []

        entity_linking[model_id] = {
            "datasets": [
                AI4LifeHelper.generate_mlentory_entity_hash_id("Dataset", x)
                for x in datasets
            ],
            # "articles": [],  # not available for AI4Life right now
            "keywords": [
                AI4LifeHelper.generate_mlentory_entity_hash_id("Keyword", x)
                for x in keywords
            ],
            "licenses": [
                AI4LifeHelper.generate_mlentory_entity_hash_id("License", x)
                for x in licenses
            ],
            "tasks": [
                AI4LifeHelper.generate_mlentory_entity_hash_id("Task", x)
                for x in tasks
            ],
            "sharedby": [
                AI4LifeHelper.generate_mlentory_entity_hash_id("SharedBy", x)
                for x in sharedby
            ],
            "sources": list(ai4life_catalog_source_iris),
            # "base_models": [],  # not available
            # "languages": [],    # not available
        }

    output_path = Path(normalized_folder) / "entity_linking.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entity_linking, f, indent=2, ensure_ascii=False)

    logger.info("Saved entity linking data for %d models to %s", len(entity_linking), output_path)
    return str(output_path)


@asset(
    group_name="ai4life_transformation",
    ins={
        "datasets_json": AssetIn("ai4life_datasets_normalized"),   # path to datasets.json (normalized)
        "keywords_json": AssetIn("ai4life_keywords_normalized"),   # path to keywords.json (normalized)
        "licenses_json": AssetIn("ai4life_licenses_normalized"),   # path to licenses.json (normalized)
        "tasks_json": AssetIn("ai4life_tasks_normalized"),         # path to tasks.json (normalized)
        "sharedby_json": AssetIn("ai4life_sharedby_normalized"),   # path to sharedby.json (normalized)
        "models_json": AssetIn("ai4life_model_normalized"),        # path to mlmodels.json (normalized)
        "sources_json": AssetIn("ai4life_sources_normalized"),     # path to sources.json (normalized)
        "run_folder_data": AssetIn("ai4life_normalized_model_folder"),  # (raw_models_json_path, normalized_folder)
    },
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)

def ai4life_create_translation_mapping(
    datasets_json: str,
    keywords_json: str,
    licenses_json: str,
    tasks_json: str,
    sharedby_json: str,
    models_json: str,
    sources_json: str,
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Create translation mapping: MLentory URI -> human-readable name.

    Reads normalized AI4Life entity JSON files and extracts:
      - MLentory URI from https://schema.org/identifier (first mlentory_graph URI)
      - Name from https://schema.org/name

    Writes:
      <normalized_folder>/translation_mapping.json
    """
    _, normalized_folder = run_folder_data

    uri_prefix = "https://w3id.org/mlentory/mlentory_graph/"
    out_map: Dict[str, str] = {}

    def _first_non_empty(*values: Any) -> Optional[str]:
        for v in values:
            if v is None:
                continue
            s = str(v).strip()
            if s:
                return s
        return None

    def _load_json_records(path: str) -> List[Dict[str, Any]]:
        if not path:
            return []
        p = Path(path)
        if not p.exists():
            logger.warning("Translation mapping input missing: %s", path)
            return []
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            # if someone wrote a dict keyed by id, convert values to list
            return [v for v in data.values() if isinstance(v, dict)]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        return []

    def _extract_uri(record: Dict[str, Any]) -> Optional[str]:
        ids = record.get("https://schema.org/identifier")
        if not isinstance(ids, list):
            return None
        for cand in ids:
            if isinstance(cand, str) and cand.startswith(uri_prefix):
                return cand.strip()
        return None

    def _extract_name(record: Dict[str, Any]) -> Optional[str]:
        return _first_non_empty(record.get("https://schema.org/name"))

    entity_configs = [
        {"label": "datasets", "path": datasets_json},
        {"label": "keywords", "path": keywords_json},
        {"label": "licenses", "path": licenses_json},
        {"label": "tasks", "path": tasks_json},
        {"label": "sharedby", "path": sharedby_json},
        {"label": "models", "path": models_json},
        {"label": "sources", "path": sources_json},
    ]

    for cfg in entity_configs:
        records = _load_json_records(cfg["path"])
        if not records:
            continue

        for rec in records:
            uri = _extract_uri(rec)
            if not uri:
                continue
            name = _extract_name(rec)
            if not name:
                continue

            out_map[uri] = name

    output_path = Path(normalized_folder) / "translation_mapping.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out_map, f, indent=2, ensure_ascii=False)

    logger.info("Saved translation mapping (%d entries) to %s", len(out_map), output_path)
    return str(output_path)


@asset(
    group_name="ai4life_transformation",
    ins={
        "run_folder_data": AssetIn("ai4life_normalized_model_folder"),
        "basic_properties_path": AssetIn("ai4life_extract_basic_properties"),
        "entity_linking_path": AssetIn("ai4life_entity_linking"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_model_normalized(
    run_folder_data: Tuple[str, str],
    basic_properties_path: str,
    entity_linking_path: str,
) -> str:
    """
    Builds FAIR4ML-validated MLModel objects for AI4Life.

    Inputs:
      - run_folder_data: (raw_models_json_path, normalized_run_folder)
      - basic_properties_path: .../partial_basic_properties.json
      - entity_linking_path: .../entity_linking.json

    Output:
      - .../mlmodels.json in the normalized_run_folder
    """
    raw_models_json_path, normalized_folder = run_folder_data
    normalized_folder_path = Path(normalized_folder)
    normalized_folder_path.mkdir(parents=True, exist_ok=True)

    # --- Load raw models (only to get complete model list / ids) ---
    logger.info("Loading raw models from %s", raw_models_json_path)
    with open(raw_models_json_path, "r", encoding="utf-8") as f:
        raw_payload = json.load(f)

    if isinstance(raw_payload, list):
        raw_models = raw_payload
    elif isinstance(raw_payload, dict):
        raw_models = raw_payload.get("models") or raw_payload.get("data") or raw_payload.get("items") or []
    else:
        raw_models = []

    if not isinstance(raw_models, list):
        raise ValueError(f"Expected list of raw models, got: {type(raw_models).__name__}")

    raw_ids: List[str] = []
    for i, rm in enumerate(raw_models):
        if isinstance(rm, dict):
            mid = str(rm.get("modelId", "")).strip() or f"unknown_{i}"
        else:
            mid = f"unknown_{i}"
        raw_ids.append(mid)

    # --- Load partial basic properties (list) ---
    logger.info("Loading partial basic properties from %s", basic_properties_path)
    with open(basic_properties_path, "r", encoding="utf-8") as f:
        basic_list = json.load(f)

    if not isinstance(basic_list, list):
        raise ValueError(f"Expected list in partial_basic_properties.json, got: {type(basic_list).__name__}")

    basic_by_id: Dict[str, Dict[str, Any]] = {}
    for i, bp in enumerate(basic_list):
        if not isinstance(bp, dict):
            continue
        mid = str(bp.get("_model_id", "")).strip() or f"unknown_{i}"
        basic_by_id[mid] = bp

    # --- Load entity linking (dict) ---
    logger.info("Loading entity linking from %s", entity_linking_path)
    with open(entity_linking_path, "r", encoding="utf-8") as f:
        entity_linking = json.load(f)

    if not isinstance(entity_linking, dict):
        raise ValueError(f"Expected dict in entity_linking.json, got: {type(entity_linking).__name__}")

    # --- Decide which ids to build outputs for ---
    # Usually you want the raw model list to be the “source of truth” for count/order.
    # But include any ids that appear only in partials too (best effort).
    all_ids = list(dict.fromkeys(raw_ids + list(basic_by_id.keys()) + list(entity_linking.keys())))

    # --- Merge + validate ---
    merged_items = merge_ai4life_partial_schemas(
        basic_by_id=basic_by_id,
        entity_linking_data=entity_linking,
        all_model_ids=all_ids,
    )

    normalized_models, validation_errors = validate_ai4life_mlmodels(merged_items)

    if not normalized_models:
        raise RuntimeError("ai4life_model_normalized produced zero valid MLModels. Aborting run.")

    # --- Write outputs ---
    output_path = normalized_folder_path / "mlmodels.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(normalized_models, f, indent=2, ensure_ascii=False, default=str)

    if validation_errors:
        errors_path = normalized_folder_path / "transformation_errors.json"
        with open(errors_path, "w", encoding="utf-8") as f:
            json.dump(validation_errors, f, indent=2, ensure_ascii=False, default=str)
        logger.warning(
            "Wrote %d valid models; %d failed validation. Errors saved to %s",
            len(normalized_models),
            len(validation_errors),
            errors_path,
        )

    logger.info("Saved mlmodels.json to %s", output_path)
    return str(output_path)

def merge_ai4life_partial_schemas(
    basic_by_id: Dict[str, Dict[str, Any]],
    entity_linking_data: Dict[str, Dict[str, Any]],
    all_model_ids: List[str],
) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Merge basic properties + entity linking into a dict compatible with MLModel(**data).

    Returns:
        List of (model_id, merged_dict)
    """
    merged_items: List[Tuple[str, Dict[str, Any]]] = []

    for model_id in all_model_ids:
        bp = basic_by_id.get(model_id) or {}
        links = entity_linking_data.get(model_id) or {}

        # Start from basic properties, remove debug fields if present
        merged_data: Dict[str, Any] = dict(bp)
        merged_data.pop("_model_id", None)
        merged_data.pop("_index", None)
        merged_data.pop("_error", None)

        # Entity linking (AI4Life has datasets/keywords/licenses/tasks/sharedby)
        datasets = links.get("datasets") or []
        keywords = links.get("keywords") or []
        licenses = links.get("licenses") or []
        tasks = links.get("tasks") or []
        sharedby = links.get("sharedby") or []
        sources = links.get("sources") or []

        # Map to FAIR4ML MLModel fields
        if datasets:
            merged_data["trainedOn"] = list(datasets)
            merged_data["testedOn"] = list(datasets)
            merged_data["validatedOn"] = list(datasets)
            merged_data["evaluatedOn"] = list(datasets)

        if keywords:
            existing = merged_data.get("keywords") or []
            if not isinstance(existing, list):
                existing = []
            merged_data["keywords"] = list(dict.fromkeys(existing + list(keywords)))

        if licenses:
            merged_data["license"] = str(licenses[0])  # MLModel.license is a single string
        if tasks:
            merged_data["mlTask"] = list(tasks)
        if sharedby:
            merged_data["sharedBy"] = str(sharedby[0])  # MLModel.sharedBy is a single string
        if sources:
            merged_data["source"] = str(sources[0])  # MLModel.source is a single string

        # Minimal required fields
        if not merged_data.get("name"):
            merged_data["name"] = model_id

        if not isinstance(merged_data.get("identifier"), list):
            merged_data["identifier"] = []

        # --- Coerce fields to match MLModel schema ---

        # modelCategory must be List[str] in schema
        mc = merged_data.get("modelCategory")
        if isinstance(mc, str):
            merged_data["modelCategory"] = [mc] if mc.strip() else []
        elif isinstance(mc, list):
            merged_data["modelCategory"] = [str(x) for x in mc if str(x).strip()]

        # referencePublication is a List[str] in schema
        rp = merged_data.get("referencePublication")
        if isinstance(rp, str):
            merged_data["referencePublication"] = [rp] if rp.strip() else []
        elif isinstance(rp, list):
            merged_data["referencePublication"] = [str(x) for x in rp if str(x).strip()]

        # intendedUse is Optional[str]
        iu = merged_data.get("intendedUse")
        if iu is not None and not isinstance(iu, str):
            merged_data["intendedUse"] = str(iu)

        merged_items.append((model_id, merged_data))

    return merged_items


def validate_ai4life_mlmodels(
    merged_items: List[Tuple[str, Dict[str, Any]]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Validate merged dicts against MLModel and return:
      - normalized models (as dicts)
      - validation errors (as dicts)
    """
    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, (model_id, data) in enumerate(merged_items):
        try:
            obj = MLModel(**data)  # populate_by_name=True in your schema

            # IMPORTANT:
            # - by_alias=True => keys become IRIs (https://schema.org/identifier, etc.)
            # - by_alias=False => keys stay as python names (identifier, name, url, ...)
            normalized.append(obj.model_dump(mode="json", by_alias=True))

        except ValidationError as ve:
            errors.append(
                {
                    "_model_id": model_id,
                    "_index": idx,
                    "_error": "MLModel validation failed",
                    "details": ve.errors(),
                    "merged_data": data,
                }
            )
        except Exception as e:
            errors.append(
                {
                    "_model_id": model_id,
                    "_index": idx,
                    "_error": str(e),
                    "error_type": type(e).__name__,
                    "merged_data": data,
                }
            )

    return normalized, errors


@asset(
    group_name="ai4life_transformation",
    ins={
        # must be the tuple (datasets_json_path, run_folder)
        "datasets_data": AssetIn("ai4life_datasets_raw"),
        # must be the tuple (raw_models_json_path, normalized_folder)
        "run_folder_data": AssetIn("ai4life_normalized_model_folder"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_datasets_normalized(
    datasets_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize AI4Life dataset records into CroissantDataset and write
    <normalized_folder>/datasets.json with IRI keys (by_alias=True).
    """
    datasets_json_path, _raw_run_folder = datasets_data
    _raw_models_json_path, normalized_folder = run_folder_data

    out_path = Path(normalized_folder) / "datasets.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not datasets_json_path:
        logger.info("No datasets_json_path. Writing empty datasets.json")
        out_path.write_text("[]", encoding="utf-8")
        return str(out_path)

    logger.info("Loading AI4Life datasets from %s", datasets_json_path)
    with open(datasets_json_path, "r", encoding="utf-8") as f:
        raw_datasets = json.load(f)

    if not isinstance(raw_datasets, list):
        raise ValueError(f"Expected a list in {datasets_json_path}, got {type(raw_datasets).__name__}")

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_datasets):
        if not isinstance(rec, dict):
            errors.append({"_index": idx, "_error": f"record is not a dict: {type(rec).__name__}"})
            continue

        dataset_id = (rec.get("dataset_id") or rec.get("datasetId") or f"dataset_{idx}")
        dataset_id = str(dataset_id).strip()

        mlentory_id = str(rec.get("mlentory_id", "")).strip() or None
        url = str(rec.get("url", "")).strip() or None

        # Identifier list like your sample: [mlentory_id, url]
        identifiers: List[str] = []
        if mlentory_id:
            identifiers.append(mlentory_id)
        if url:
            identifiers.append(url)

        name = str(rec.get("name", "")).strip() or dataset_id
        description = rec.get("description", None)

        # license can be str or None
        license_value = rec.get("license", None)
        if isinstance(license_value, str) and not license_value.strip():
            license_value = None

        # keywords list
        keywords = rec.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [keywords]
        if not isinstance(keywords, list):
            keywords = []
        keywords = [str(k).strip() for k in keywords if str(k).strip()]

        # creator: your AI4Life records show list[{"name": "..."}]
        creator_value: Optional[str] = None
        creator = rec.get("creator")
        if isinstance(creator, list) and creator:
            c0 = creator[0]
            if isinstance(c0, dict):
                creator_value = str(c0.get("name", "")).strip() or None
            elif isinstance(c0, str):
                creator_value = c0.strip() or None
        elif isinstance(creator, dict):
            creator_value = str(creator.get("name", "")).strip() or None
        elif isinstance(creator, str):
            creator_value = creator.strip() or None

        # citeAs: AI4Life has citation like [{"doi": "...", "text": "..."}]
        cite_as: Optional[str] = None
        citation = rec.get("citation")
        if isinstance(citation, list) and citation:
            c0 = citation[0]
            if isinstance(c0, dict):
                doi = str(c0.get("doi", "")).strip()
                txt = str(c0.get("text", "")).strip()
                cite_as = doi or txt or None
            elif isinstance(c0, str):
                cite_as = c0.strip() or None
        elif isinstance(citation, str):
            cite_as = citation.strip() or None

        # Dates: keep as strings (schema allows Optional[str])
        date_published = rec.get("date_created") or rec.get("datePublished")
        date_modified = rec.get("date_modified") or rec.get("dateModified")

        # sameAs: include empty list if you don’t have alternatives
        same_as = rec.get("sameAs") or []
        if isinstance(same_as, str):
            same_as = [same_as]
        if not isinstance(same_as, list):
            same_as = []
        same_as = [str(s).strip() for s in same_as if str(s).strip()]

        # meta must end up under "https://w3id.org/mlentory/mlentory_graph/meta/"
        extraction_meta = rec.get("extraction_metadata") or rec.get("extractionMeta") or {}
        if extraction_meta is None or not isinstance(extraction_meta, dict):
            extraction_meta = {}

        payload: Dict[str, Any] = {
            "identifier": identifiers,
            "name": name,
            "url": url,
            "sameAs": same_as,
            "description": description,
            "license": license_value,
            "conformsTo": "http://mlcommons.org/croissant/1.0",
            "citeAs": cite_as,
            "keywords": keywords,
            "creator": creator_value,
            "datePublished": date_published,
            "dateModified": date_modified,
            "extraction_metadata": extraction_meta,
        }

        try:
            obj = CroissantDataset(**payload)

            # THIS is what makes keys look like your example
            normalized.append(obj.model_dump(mode="json", by_alias=True))

        except ValidationError as ve:
            errors.append(
                {
                    "dataset_id": dataset_id,
                    "_index": idx,
                    "_error": "CroissantDataset validation failed",
                    "details": ve.errors(),
                }
            )
        except Exception as e:
            errors.append(
                {
                    "dataset_id": dataset_id,
                    "_index": idx,
                    "_error": str(e),
                    "error_type": type(e).__name__,
                }
            )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    if errors:
        err_path = Path(normalized_folder) / "datasets_normalization_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        logger.warning("Normalized %d/%d datasets. Errors: %d (see %s)", len(normalized), len(raw_datasets), len(errors), err_path)
    else:
        logger.info("Normalized %d/%d datasets. No errors.", len(normalized), len(raw_datasets))

    return str(out_path)


@asset(
    group_name="ai4life_transformation",
    ins={
        "keywords_data": AssetIn("ai4life_keywords_raw"),          # (keywords_json_path, run_folder)
        "run_folder_data": AssetIn("ai4life_normalized_model_folder"),  # (raw_models_json_path, normalized_folder)
    },
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_keywords_normalized(
    keywords_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize AI4Life keywords to schema.org DefinedTerm-like format and write
    <normalized_folder>/keywords.json with IRI keys.
    """
    keywords_json_path, _raw_run_folder = keywords_data
    _raw_models_json_path, normalized_folder = run_folder_data

    out_path = Path(normalized_folder) / "keywords.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not keywords_json_path:
        logger.info("No keywords_json_path. Writing empty keywords.json")
        out_path.write_text("[]", encoding="utf-8")
        return str(out_path)

    logger.info("Loading AI4Life keywords from %s", keywords_json_path)
    with open(keywords_json_path, "r", encoding="utf-8") as f:
        raw_keywords = json.load(f)

    if isinstance(raw_keywords, dict):
        # sometimes people accidentally store a single object
        raw_keywords = [raw_keywords]

    if not isinstance(raw_keywords, list):
        raise ValueError(f"Expected list in {keywords_json_path}, got {type(raw_keywords).__name__}")

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_keywords):
        if not isinstance(rec, dict):
            errors.append({"_index": idx, "_error": f"record is not a dict: {type(rec).__name__}"})
            continue

        name = str(rec.get("name", "")).strip() or f"keyword_{idx}"
        mlentory_id = str(rec.get("mlentory_id", "")).strip() or None

        # match your desired output
        identifiers: List[str] = []
        if mlentory_id:
            identifiers.append(mlentory_id)

        # optional fields in the sample
        url: Optional[str] = None
        term_code = name  # in your example: termCode == name
        alternate_name: List[str] = []

        extraction_meta = rec.get("extraction_metadata") or {}
        if not isinstance(extraction_meta, dict):
            extraction_meta = {}

        payload: Dict[str, Any] = {
            "identifier": identifiers,
            "name": name,
            "url": url,
            "term_code":term_code,
            "extraction_metadata": extraction_meta,
        }

        try:
            obj = DefinedTerm(**payload)
            normalized.append(obj.model_dump(mode="json", by_alias=True))
        except ValidationError as ve:
            errors.append(
                {
                    "keyword": name,
                    "_index": idx,
                    "_error": "DefinedTerm validation failed",
                    "details": ve.errors(),
                }
            )
        except Exception as e:
            errors.append(
                {
                    "keyword": name,
                    "_index": idx,
                    "_error": str(e),
                    "error_type": type(e).__name__,
                }
            )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    if errors:
        err_path = Path(normalized_folder) / "keywords_normalization_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        logger.warning("Normalized %d/%d keywords. Errors: %d (see %s)", len(normalized), len(raw_keywords), len(errors), err_path)
    else:
        logger.info("Normalized %d/%d keywords. No errors.", len(normalized), len(raw_keywords))

    return str(out_path)


@asset(
    group_name="ai4life_transformation",
    ins={
        "tasks_data": AssetIn("ai4life_tasks_raw"),                 # (tasks_json_path, run_folder)
        "run_folder_data": AssetIn("ai4life_normalized_model_folder"),  # (raw_models_json_path, normalized_folder)
    },
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_tasks_normalized(
    tasks_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize AI4Life tasks to schema.org DefinedTerm-like format and write
    <normalized_folder>/tasks.json with IRI keys.
    """
    tasks_json_path, _raw_run_folder = tasks_data
    _raw_models_json_path, normalized_folder = run_folder_data

    out_path = Path(normalized_folder) / "tasks.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not tasks_json_path:
        logger.info("No tasks_json_path. Writing empty tasks.json")
        out_path.write_text("[]", encoding="utf-8")
        return str(out_path)

    logger.info("Loading AI4Life tasks from %s", tasks_json_path)
    with open(tasks_json_path, "r", encoding="utf-8") as f:
        raw_tasks = json.load(f)

    if isinstance(raw_tasks, dict):
        raw_tasks = [raw_tasks]

    if not isinstance(raw_tasks, list):
        raise ValueError(f"Expected list in {tasks_json_path}, got {type(raw_tasks).__name__}")

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_tasks):
        if not isinstance(rec, dict):
            errors.append({"_index": idx, "_error": f"record is not a dict: {type(rec).__name__}"})
            continue

        task_name = str(rec.get("name") or rec.get("task") or "").strip() or f"task_{idx}"
        mlentory_id = str(rec.get("mlentory_id", "")).strip() or None

        identifiers: List[str] = []
        if mlentory_id:
            identifiers.append(mlentory_id)
        raw_task_url = rec.get("url")
        if isinstance(raw_task_url, str):
            candidate_url = raw_task_url.strip()
            task_url = candidate_url if candidate_url and candidate_url.lower() != "none" else None
        else:
            task_url = None
        if task_url:
            identifiers.append(task_url)

        extraction_meta = rec.get("extraction_metadata") or {}
        if not isinstance(extraction_meta, dict):
            extraction_meta = {}

        payload: Dict[str, Any] = {
            "identifier": identifiers,
            "name": task_name,
            "url": task_url,
            "term_code": task_name,
            "extraction_metadata": extraction_meta,
        }

        try:
            obj = DefinedTerm(**payload)
            normalized.append(obj.model_dump(mode="json", by_alias=True))
        except ValidationError as ve:
            errors.append(
                {
                    "task": task_name,
                    "_index": idx,
                    "_error": "DefinedTerm validation failed",
                    "details": ve.errors(),
                }
            )
        except Exception as e:
            errors.append(
                {
                    "task": task_name,
                    "_index": idx,
                    "_error": str(e),
                    "error_type": type(e).__name__,
                }
            )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    if errors:
        err_path = Path(normalized_folder) / "tasks_normalization_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        logger.warning(
            "Normalized %d/%d tasks. Errors: %d (see %s)",
            len(normalized),
            len(raw_tasks),
            len(errors),
            err_path,
        )
    else:
        logger.info("Normalized %d/%d tasks. No errors.", len(normalized), len(raw_tasks))

    return str(out_path)


@asset(
    group_name="ai4life_transformation",
    ins={
        "sharedby_data": AssetIn("ai4life_sharedby_raw"),              # (sharedby_json_path, run_folder)
        "run_folder_data": AssetIn("ai4life_normalized_model_folder"), # (raw_models_json_path, normalized_folder)
    },
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_sharedby_normalized(
    sharedby_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize AI4Life sharedBy entities to schema.org DefinedTerm-like format and write
    <normalized_folder>/sharedby.json with IRI keys.
    """
    sharedby_json_path, _raw_run_folder = sharedby_data
    _raw_models_json_path, normalized_folder = run_folder_data

    out_path = Path(normalized_folder) / "sharedby.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not sharedby_json_path:
        logger.info("No sharedby_json_path. Writing empty sharedby.json")
        out_path.write_text("[]", encoding="utf-8")
        return str(out_path)

    logger.info("Loading AI4Life sharedBy entities from %s", sharedby_json_path)
    with open(sharedby_json_path, "r", encoding="utf-8") as f:
        raw_sharedby = json.load(f)

    if isinstance(raw_sharedby, dict):
        raw_sharedby = [raw_sharedby]
    if not isinstance(raw_sharedby, list):
        raise ValueError(f"Expected list in {sharedby_json_path}, got {type(raw_sharedby).__name__}")

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_sharedby):
        if not isinstance(rec, dict):
            errors.append({"_index": idx, "_error": f"record is not a dict: {type(rec).__name__}"})
            continue

        name = str(rec.get("name", "")).strip() or f"sharedby_{idx}"
        mlentory_id = str(rec.get("mlentory_id", "")).strip() or None
        extraction_meta = rec.get("extraction_metadata") or {}
        if not isinstance(extraction_meta, dict):
            extraction_meta = {}

        payload: Dict[str, Any] = {
            "identifier": [mlentory_id] if mlentory_id else [],
            "name": name,
            "url": None,
            "term_code": name,
            "description": "Entity representing who shared/published the model.",
            "in_defined_term_set": ["https://ai4life.eurobioimaging.eu/"],
            "extraction_metadata": extraction_meta,
        }

        try:
            obj = DefinedTerm(**payload)
            normalized.append(obj.model_dump(mode="json", by_alias=True))
        except ValidationError as ve:
            errors.append(
                {
                    "sharedby": name,
                    "_index": idx,
                    "_error": "DefinedTerm validation failed",
                    "details": ve.errors(),
                }
            )
        except Exception as e:
            errors.append(
                {
                    "sharedby": name,
                    "_index": idx,
                    "_error": str(e),
                    "error_type": type(e).__name__,
                }
            )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    if errors:
        err_path = Path(normalized_folder) / "sharedby_normalization_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        logger.warning(
            "Normalized %d/%d sharedBy entities. Errors: %d (see %s)",
            len(normalized),
            len(raw_sharedby),
            len(errors),
            err_path,
        )
    else:
        logger.info("Normalized %d/%d sharedBy entities. No errors.", len(normalized), len(raw_sharedby))

    return str(out_path)


@asset(
    group_name="ai4life_transformation",
    ins={
        "licenses_data": AssetIn("ai4life_licenses_raw"),               # (licenses_json_path, run_folder)
        "run_folder_data": AssetIn("ai4life_normalized_model_folder"),  # (raw_models_json_path, normalized_folder)
    },
    tags={"pipeline": "ai4life_etl", "stage": "transform"},
)
def ai4life_licenses_normalized(
    licenses_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize AI4Life licenses into the schema.org-style output (IRI keys),
    matching the sample license output structure.

    Output file: <normalized_folder>/licenses.json
    """
    licenses_json_path, _raw_run_folder = licenses_data
    _raw_models_json_path, normalized_folder = run_folder_data

    out_path = Path(normalized_folder) / "licenses.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # If upstream produced no licenses file, write empty list
    if not licenses_json_path:
        logger.info("No licenses_json_path provided. Writing empty licenses.json")
        out_path.write_text("[]", encoding="utf-8")
        return str(out_path)

    logger.info("Loading AI4Life licenses from %s", licenses_json_path)
    with open(licenses_json_path, "r", encoding="utf-8") as f:
        raw_licenses = json.load(f)

    # Accept single dict or list
    if isinstance(raw_licenses, dict):
        raw_licenses = [raw_licenses]

    if not isinstance(raw_licenses, list):
        raise ValueError(f"Expected list in {licenses_json_path}, got {type(raw_licenses).__name__}")

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_licenses):
        if not isinstance(rec, dict):
            errors.append({"_index": idx, "_error": f"record is not a dict: {type(rec).__name__}"})
            continue

        name = str(rec.get("name", "")).strip()
        mlentory_id = str(rec.get("mlentory_id", "")).strip()

        if not name or not mlentory_id:
            errors.append(
                {
                    "_index": idx,
                    "_error": "missing required fields",
                    "name": name,
                    "mlentory_id": mlentory_id,
                }
            )
            continue

        em = rec.get("extraction_metadata") or {}
        if not isinstance(em, dict):
            em = {}

        # Build meta to match your sample shape (SPDX has more fields; we default to None)
        meta_out = {
            "extraction_method": em.get("extraction_method"),
            "confidence": em.get("confidence", 1.0),
            "source_identifier": em.get("source_identifier"),
            "source_name": em.get("source_name", name),
            "osi_approved": em.get("osi_approved"),
            "deprecated": em.get("deprecated"),
        }

        normalized.append(
            {
                "https://schema.org/identifier": [mlentory_id],
                "https://schema.org/name": name,
                "https://schema.org/url": None,
                "https://schema.org/sameAs": [],
                "https://schema.org/alternateName": [],
                "https://schema.org/description": None,
                "https://schema.org/abstract": None,
                "https://schema.org/text": None,
                "https://schema.org/license": None,
                "https://schema.org/version": None,
                "https://schema.org/copyrightNotice": None,
                "https://schema.org/legislationJurisdiction": None,
                "https://schema.org/legislationType": None,
                "https://schema.org/dateCreated": None,
                "https://schema.org/dateModified": None,
                "https://schema.org/datePublished": None,
                "https://schema.org/isBasedOn": [],
                "https://schema.org/subjectOf": [],
                "https://w3id.org/mlentory/mlentory_graph/meta/": meta_out,
            }
        )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    if errors:
        err_path = Path(normalized_folder) / "licenses_normalization_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        logger.warning("Normalized %d/%d licenses. Errors written to %s", len(normalized), len(raw_licenses), err_path)
    else:
        logger.info("Normalized %d/%d licenses", len(normalized), len(raw_licenses))

    logger.info("Wrote normalized licenses to %s", out_path)
    return str(out_path)

