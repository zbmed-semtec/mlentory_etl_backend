"""
Dagster assets for Kaggle -> FAIR4ML transformation.

Pipeline:
1) Read raw Kaggle models from extraction (models.json)
2) Create separate assets for each property group:
    - mlmodels.json       (FAIR4ML MLModel)
    - mlinstances.json    (FAIR4ML MLModel, one per downloadable instance)
    - entity_linking.json (linkage of model -> keywords/licenses/frameworks)

Instances are written to their own file rather than mlmodels.json. A Kaggle
model is a container and its instances are the downloadable artifacts, so
folding them in would turn ~43k models into ~60k+ search results that are
mostly the same model repackaged. The relationships survive either way -
``parent_mlentory_id`` links an instance to its model and ``baseModel`` links
a fine-tune to what it was derived from - so the graph can still answer
"show me every variation of Gemma" and "show me models built on Gemma".
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional
import logging

from pydantic import BaseModel, ValidationError
from dagster import asset, AssetIn

from etl_extractors.kaggle.kaggle_helper import KaggleHelper
from etl_transformers.kaggle.transform_mlmodel import map_kaggle_basic_properties
from etl_transformers.common.entity_link_metadata import (
    apply_entity_link_extraction_metadata,
)
from schemas.fair4ml import MLModel
from schemas.schemaorg import DefinedTerm


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


def _load_json_records(path: str) -> List[Dict[str, Any]]:
    """Load a JSON file that should hold a list of records."""
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Expected JSON file not found: %s", path)
        return []
    with open(file_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        return [v for v in data.values() if isinstance(v, dict)]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _clean_framework(framework: str) -> str:
    """
    Turn Kaggle's framework field into the display form used in instance URLs.

    ``MODEL_FRAMEWORK_TENSOR_FLOW_2`` and ``pyTorch`` both become the form the
    instance ids are built from, so base-model references resolve to the same
    hash as the instance they point at.
    """
    if not framework:
        return ""
    name = framework
    if name.startswith("MODEL_FRAMEWORK_"):
        name = name[len("MODEL_FRAMEWORK_"):]
    if name and name[0].islower() and "_" not in name:
        # pyTorch -> PyTorch, keras -> Keras, scikitLearn -> ScikitLearn
        return name[0].upper() + name[1:]
    parts = [p for p in name.split("_") if p]
    return "".join(p.capitalize() for p in parts)



def _adaption_technique(record: Dict[str, Any]) -> Optional[str]:
    """
    Return ``"fineTuned"`` when the instance carries Kaggle's ``fineTunable``
    flag, else ``None``.

    Note this is Kaggle's own field and it is set on most instances, so most
    records will come out as fineTuned.
    """
    if record.get("fineTunable"):
        return "fineTuned"
    return None


def normalize_kaggle_instance(rec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map one Kaggle model instance onto the MLModel field set.

    An instance is a downloadable artifact of a model - one per framework and
    variation - and is emitted as an MLModel in its own right, alongside the
    models themselves. Only the fields it genuinely owns are mapped: its own
    name, overview, usage snippet, license, size and URL.

    ``baseModel`` carries two kinds of link, real lineage first: the model an
    instance was derived from (from ``baseModelInstanceInformation``), then
    the parent model it belongs to. Both become ``fair4ml:baseModel`` edges,
    which gives the graph a parent node with its variations as children.
    """
    instance_id = str(rec.get("instanceId", "")).strip()
    mlentory_id = str(rec.get("mlentory_id", "")).strip()
    parent_id = str(rec.get("parent_mlentory_id", "")).strip()
    url = str(rec.get("url", "")).strip()

    identifiers = [x for x in (mlentory_id,) if x]
    urls = [x for x in (url,) if x]
    if mlentory_id.startswith("https://w3id.org/mlentory/"):
        urls.append(
            mlentory_id.replace(
                "https://w3id.org/mlentory/", "https://mlentory.zbmed.de/", 1
            )
        )

    # Real lineage: base model reconstructed from the nested
    # baseModelInstanceInformation object. The framework there uses the field
    # spelling ("pyTorch"), so it is normalized to the URL form the instance
    # ids are built from, or the hash would not match.
    base_models: List[str] = []
    base_info = rec.get("baseModelInstanceInformation")
    if isinstance(base_info, str) and base_info.strip():
        try:
            base_info = json.loads(base_info)
        except (ValueError, TypeError):
            base_info = None
    if isinstance(base_info, dict):
        owner = base_info.get("owner")
        owner_slug = ""
        if isinstance(owner, dict):
            owner_slug = str(owner.get("slug", "")).strip()
        model_slug = str(base_info.get("modelSlug", "")).strip()
        instance_slug = str(base_info.get("instanceSlug", "")).strip()
        framework = _clean_framework(str(base_info.get("framework", "")).strip())
        parts = [p for p in (owner_slug, model_slug, framework, instance_slug) if p]
        if len(parts) == 4:
            base_models.append(
                KaggleHelper.generate_mlentory_entity_hash_id(
                    "ModelInstance", "/".join(parts), platform="Kaggle"
                )
            )

    external_base = str(rec.get("externalBaseModelUrl", "")).strip()
    if external_base and external_base not in base_models:
        base_models.append(external_base)

    # The parent model this instance belongs to. Added last so real lineage
    # stays at index 0 for anything that needs to tell the two apart.
    if parent_id and parent_id not in base_models:
        base_models.append(parent_id)

    # The instance's own documentation. `overview` is the short summary Kaggle
    # shows on the variation page; `usage` is the long form and is often
    # richer than the parent model card. abstract holds both, matching what it
    # means at model level: the complete original text for this record.
    overview = str(rec.get("description", "")).strip()
    usage = str(rec.get("usage", "")).strip()
    full_card = "\n\n".join(part for part in (overview, usage) if part)

    meta = {
        "extraction_method": "Parsed_from_Kaggle_instances_json",
        "confidence": 1.0,
    }

    return {
        "identifier": identifiers,
        "name": str(rec.get("name", "")).strip() or instance_id,
        "url": list(dict.fromkeys(urls)),
        "author": str(rec.get("sharedBy", "")).strip() or None,
        "sharedBy": str(rec.get("sharedBy", "")).strip() or None,
        "description": overview or None,
        "abstract": full_card or None,
        "license": str(rec.get("license", "")).strip() or None,
        "modelCategory": [
            x for x in (str(rec.get("frameworkName", "")).strip(),) if x
        ],
        "baseModel": base_models,
        "adaptionTechniques": _adaption_technique(rec),
        "usageInstructions": usage or None,
        "memoryRequirements": str(rec.get("contentSize", "")).strip() or None,
        "archivedAt": url or None,
        "extraction_metadata": {
            "identifier": {**meta, "source_field": "mlentory_id"},
            "name": {**meta, "source_field": "slug"},
            "sharedBy": {
                **meta,
                "source_field": "sharedBy",
                "notes": "Owner carried down from the parent model",
            },
            "description": {**meta, "source_field": "overview"},
            "abstract": {
                **meta,
                "source_field": "overview, usage",
                "notes": "Full instance documentation before summarization",
            },
            "license": {**meta, "source_field": "licenseName"},
            "modelCategory": {
                **meta,
                "source_field": "frameworkName",
                "notes": "Framework read from the instance URL",
            },
            "baseModel": {
                **meta,
                "source_field": (
                    "baseModelInstanceInformation, externalBaseModelUrl, "
                    "parent_mlentory_id"
                ),
                "notes": "Real lineage first, then the parent model",
            },
            "adaptionTechniques": {
                **meta,
                "source_field": "fineTunable",
            },
            "usageInstructions": {**meta, "source_field": "usage"},
            "memoryRequirements": {**meta, "source_field": "totalUncompressedBytes"},
        },
        "_model_id": instance_id,
    }


# ---------- normalized folder ----------

@asset(
    group_name="kaggle_transformation",
    ins={"models_data": AssetIn("kaggle_models_raw")},
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_normalized_model_folder(models_data: Tuple[str, str]) -> Tuple[str, str]:
    """
    Create normalized run folder mirroring raw run folder name.
    """
    raw_data_json_path, raw_run_folder = models_data

    # unique per run
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]

    normalized_base = Path("/data/2_normalized/kaggle")
    normalized_run_folder = normalized_base / f"{timestamp}_{run_id}"
    normalized_run_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Created normalized run folder: {normalized_run_folder}")
    return (str(raw_data_json_path), str(normalized_run_folder))


@asset(
    group_name="kaggle_transformation",
    ins={"models_data": AssetIn("kaggle_normalized_model_folder")},
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_extract_basic_properties(models_data: Tuple[str, str]) -> str:
    """
    Produces FAIR4ML-style partial_basic_properties.json for Kaggle models.

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
        raw_models = (
            raw_payload.get("models")
            or raw_payload.get("data")
            or raw_payload.get("items")
            or []
        )
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

        if not isinstance(raw_model, dict):
            out.append(
                {
                    "identifier": [],
                    "name": model_id,
                    "url": [],
                    "author": "",
                    "sharedBy": "",
                    "modelCategory": [],
                    "citation": [],
                    "intendedUse": "",
                    "dateCreated": "",
                    "dateModified": "",
                    "datePublished": "",
                    "description": "",
                    "abstract": "",
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
            mapped = map_kaggle_basic_properties(raw_model)

            mapped["_index"] = idx
            mapped["_model_id"] = mapped.get("_model_id") or model_id

            if "extraction_metadata" not in mapped or mapped["extraction_metadata"] is None:
                mapped["extraction_metadata"] = {}

            out.append(mapped)

            if (idx + 1) % 200 == 0:
                logger.info("Extracted basic properties for %d/%d models", idx + 1, len(raw_models))

        except Exception as e:
            logger.error("Error extracting basic properties for %s: %s", model_id, e, exc_info=True)

            out.append(
                {
                    "identifier": [str(raw_model.get("mlentory_id", "")).strip()],
                    "name": str(raw_model.get("name", "")).strip() or model_id,
                    "url": [str(raw_model.get("url", "")).strip()],
                    "author": "",
                    "sharedBy": str(raw_model.get("sharedBy", "")).strip(),
                    "modelCategory": [],
                    "citation": [],
                    "intendedUse": str(raw_model.get("intendedUse", "")).strip(),
                    "dateCreated": str(raw_model.get("dateCreated", "")).strip(),
                    "dateModified": str(raw_model.get("dateModified", "")).strip(),
                    "datePublished": str(raw_model.get("datePublished", "")).strip()
                                   or str(raw_model.get("dateModified", "")).strip(),
                    "description": str(raw_model.get("intendedUse", "")).strip(),
                    "abstract": str(raw_model.get("intendedUse", "")).strip(),
                    "discussionUrl": "",
                    "archivedAt": str(raw_model.get("url", "")).strip(),
                    "readme": "",
                    "issueTracker": "",
                    "extraction_metadata": {},
                    "_model_id": model_id,
                    "_index": idx,
                    "_error": str(e),
                }
            )

    output_path = Path(normalized_folder) / "partial_basic_properties.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False, default=_json_default)

    logger.info("Saved basic properties to %s", output_path)
    return str(output_path)


@asset(
    group_name="kaggle_transformation",
    ins={"run_folder_data": AssetIn("kaggle_normalized_model_folder")},
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_sources_normalized(run_folder_data: Tuple[str, str]) -> str:
    """
    Bring the Kaggle catalog ``WebSite`` from raw extract into this run's
    normalized folder as ``sources.json``.
    """
    raw_models_path, normalized_folder = run_folder_data
    raw_run = Path(raw_models_path).parent
    raw_sources = raw_run / "sources.json"
    out_path = Path(normalized_folder) / "sources.json"

    if raw_sources.exists():
        with open(raw_sources, "r", encoding="utf-8") as f:
            payload = json.load(f)
        logger.info("Loaded Kaggle catalog sources from raw run: %s", raw_sources)
    else:
        logger.warning(
            "Raw sources.json missing at %s; using KaggleHelper catalog payload",
            raw_sources,
        )
        payload = KaggleHelper.raw_kaggle_catalog_website_records()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=_json_default)

    logger.info("Wrote normalized Kaggle sources to %s", out_path)
    return str(out_path)


@asset(
    group_name="kaggle_transformation",
    ins={
        "keywords_mapping": AssetIn("kaggle_identified_keywords"),
        "licenses_mapping": AssetIn("kaggle_identified_licenses"),
        "frameworks_mapping": AssetIn("kaggle_identified_frameworks"),
        "sharedby_mapping": AssetIn("kaggle_identified_sharedby"),
        "run_folder_data": AssetIn("kaggle_normalized_model_folder"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_entity_linking(
    keywords_mapping: Dict[str, List[str]],
    licenses_mapping: Dict[str, List[str]],
    frameworks_mapping: Dict[str, List[str]],
    sharedby_mapping: Dict[str, List[str]],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Create entity linking mapping: model_id -> {keywords, licenses, frameworks, sources}
    Links identified entities with their enriched metadata.

    Args:
        keywords_mapping: {model_id: [keyword_refs]}
        licenses_mapping: {model_id: [license_names]}
        frameworks_mapping: {model_id: [framework_names]}
        run_folder_data: Tuple of (raw_models_json_path, normalized_folder)

    Returns:
        Path to saved entity linking JSON file
    """
    _, normalized_folder = run_folder_data

    kaggle_catalog_source_iris: List[str] = []
    for row in KaggleHelper.raw_kaggle_catalog_website_records():
        ids = row.get("https://schema.org/identifier") or []
        if not isinstance(ids, list):
            continue
        kaggle_catalog_source_iris = [
            u
            for u in ids
            if isinstance(u, str)
            and u.startswith("https://w3id.org/mlentory/mlentory_graph/")
        ]
        if kaggle_catalog_source_iris:
            break

    # union of ids so you don't KeyError if a model appears in only one mapping
    all_model_ids = (
        set(keywords_mapping.keys())
        | set(licenses_mapping.keys())
        | set(frameworks_mapping.keys())
        | set(sharedby_mapping.keys())
    )

    entity_linking: Dict[str, Dict[str, List[str]]] = {}

    for model_id in all_model_ids:
        keywords = keywords_mapping.get(model_id, []) or []
        licenses = licenses_mapping.get(model_id, []) or []
        frameworks = frameworks_mapping.get(model_id, []) or []
        sharedby = sharedby_mapping.get(model_id, []) or []

        entity_linking[model_id] = {
            "keywords": [
                KaggleHelper.generate_mlentory_entity_hash_id("Keyword", x, platform="Kaggle")
                for x in keywords
            ],
            "licenses": [
                KaggleHelper.generate_mlentory_entity_hash_id("License", x, platform="Kaggle")
                for x in licenses
            ],
            "frameworks": [
                KaggleHelper.generate_mlentory_entity_hash_id("Framework", x, platform="Kaggle")
                for x in frameworks
            ],
            "sharedby": [
                KaggleHelper.generate_mlentory_entity_hash_id("SharedBy", x, platform="Kaggle")
                for x in sharedby
            ],
            "sources": list(kaggle_catalog_source_iris),
        }

    output_path = Path(normalized_folder) / "entity_linking.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entity_linking, f, indent=2, ensure_ascii=False)

    logger.info("Saved entity linking data for %d models to %s", len(entity_linking), output_path)
    return str(output_path)


def merge_kaggle_partial_schemas(
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

        merged_data: Dict[str, Any] = dict(bp)
        merged_data.pop("_model_id", None)
        merged_data.pop("_index", None)
        merged_data.pop("_error", None)

        keywords = links.get("keywords") or []
        licenses = links.get("licenses") or []
        frameworks = links.get("frameworks") or []
        sharedby = links.get("sharedby") or []
        sources = links.get("sources") or []
        linked_fields: List[str] = []

        if keywords:
            existing = merged_data.get("keywords") or []
            if not isinstance(existing, list):
                existing = []
            merged_data["keywords"] = list(dict.fromkeys(existing + list(keywords)))
            linked_fields.append("keywords")

        if licenses:
            merged_data["license"] = str(licenses[0])  # MLModel.license is a single string
            linked_fields.append("license")

        if frameworks:
            # Frameworks replace the raw modelCategory strings with their IRIs
            merged_data["modelCategory"] = list(frameworks)
            linked_fields.append("modelCategory")

        if sharedby:
            merged_data["sharedBy"] = str(sharedby[0])  # MLModel.sharedBy is a single string
            linked_fields.append("sharedBy")

        if sources:
            merged_data["source"] = str(sources[0])  # MLModel.source is a single string
            linked_fields.append("source")

        apply_entity_link_extraction_metadata(merged_data, "kaggle", linked_fields)

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

        cit = merged_data.get("citation")
        if cit is None or not isinstance(cit, list):
            merged_data["citation"] = []

        iu = merged_data.get("intendedUse")
        if iu is not None and not isinstance(iu, str):
            merged_data["intendedUse"] = str(iu)

        # Kaggle records lineage per instance, never on the model itself, so a
        # parent model has no evidence it was adapted from anything.
        merged_data.setdefault("adaptionTechniques", None)

        merged_items.append((model_id, merged_data))

    return merged_items


def validate_kaggle_mlmodels(
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
            obj = MLModel(**data)
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
    group_name="kaggle_transformation",
    ins={
        "run_folder_data": AssetIn("kaggle_normalized_model_folder"),
        "basic_properties_path": AssetIn("kaggle_extract_basic_properties"),
        "entity_linking_path": AssetIn("kaggle_entity_linking"),
        "instances_data": AssetIn("kaggle_instances_raw"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_model_normalized(
    run_folder_data: Tuple[str, str],
    basic_properties_path: str,
    entity_linking_path: str,
    instances_data: Tuple[str, str],
) -> str:
    """
    Builds FAIR4ML-validated MLModel objects for Kaggle.

    Both models and their instances land in ``mlmodels.json``. A Kaggle model
    is a container and its instances are the downloadable artifacts - one per
    framework and variation - and each is an MLModel in its own right. They
    are distinguishable by ``baseModel``, which on an instance points at the
    model it belongs to, and by ``adaptionTechniques``.

    Inputs:
      - run_folder_data: (raw_models_json_path, normalized_run_folder)
      - basic_properties_path: .../partial_basic_properties.json
      - entity_linking_path: .../entity_linking.json
      - instances_data: (instances_json_path, raw_run_folder)

    Output:
      - .../mlmodels.json in the normalized_run_folder
    """
    raw_models_json_path, normalized_folder = run_folder_data
    normalized_folder_path = Path(normalized_folder)
    normalized_folder_path.mkdir(parents=True, exist_ok=True)

    logger.info("Loading raw models from %s", raw_models_json_path)
    with open(raw_models_json_path, "r", encoding="utf-8") as f:
        raw_payload = json.load(f)

    if isinstance(raw_payload, list):
        raw_models = raw_payload
    elif isinstance(raw_payload, dict):
        raw_models = (
            raw_payload.get("models")
            or raw_payload.get("data")
            or raw_payload.get("items")
            or []
        )
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

    logger.info("Loading partial basic properties from %s", basic_properties_path)
    with open(basic_properties_path, "r", encoding="utf-8") as f:
        basic_list = json.load(f)

    if not isinstance(basic_list, list):
        raise ValueError(
            f"Expected list in partial_basic_properties.json, got: {type(basic_list).__name__}"
        )

    basic_by_id: Dict[str, Dict[str, Any]] = {}
    for i, bp in enumerate(basic_list):
        if not isinstance(bp, dict):
            continue
        mid = str(bp.get("_model_id", "")).strip() or f"unknown_{i}"
        basic_by_id[mid] = bp

    logger.info("Loading entity linking from %s", entity_linking_path)
    with open(entity_linking_path, "r", encoding="utf-8") as f:
        entity_linking = json.load(f)

    if not isinstance(entity_linking, dict):
        raise ValueError(
            f"Expected dict in entity_linking.json, got: {type(entity_linking).__name__}"
        )

    all_ids = list(
        dict.fromkeys(raw_ids + list(basic_by_id.keys()) + list(entity_linking.keys()))
    )

    merged_items = merge_kaggle_partial_schemas(
        basic_by_id=basic_by_id,
        entity_linking_data=entity_linking,
        all_model_ids=all_ids,
    )

    # Instances are MLModels too, so they are validated and written into the
    # same file rather than a separate one.
    instances_json_path, _raw_run_folder = instances_data
    raw_instances = _load_json_records(instances_json_path) if instances_json_path else []
    logger.info("Loading %d Kaggle instances from %s", len(raw_instances), instances_json_path)

    instance_items: List[Tuple[str, Dict[str, Any]]] = []
    for rec in raw_instances:
        mapped = normalize_kaggle_instance(rec)
        instance_id = mapped.pop("_model_id", "") or f"instance_{len(instance_items)}"

        # Entity linking only covers models.json, so an instance's sharedBy is
        # still a plain name here. Mint the same IRI the models get, so both
        # point at one shared node rather than a name and an IRI.
        shared_by_name = str(mapped.get("sharedBy", "") or "").strip()
        if shared_by_name:
            mapped["sharedBy"] = KaggleHelper.generate_mlentory_entity_hash_id(
                "SharedBy", shared_by_name, platform="Kaggle"
            )

        instance_items.append((instance_id, mapped))

    merged_items.extend(instance_items)

    normalized_models, validation_errors = validate_kaggle_mlmodels(merged_items)

    if not normalized_models:
        raise RuntimeError("kaggle_model_normalized produced zero valid MLModels. Aborting run.")

    logger.info(
        "Normalized %d records (%d models + %d instances)",
        len(normalized_models), len(all_ids), len(instance_items),
    )

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


@asset(
    group_name="kaggle_transformation",
    ins={
        "keywords_data": AssetIn("kaggle_keywords_raw"),
        "run_folder_data": AssetIn("kaggle_normalized_model_folder"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_keywords_normalized(
    keywords_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize Kaggle keywords to schema.org DefinedTerm-like format and write
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

    raw_keywords = _load_json_records(keywords_json_path)
    logger.info("Loading Kaggle keywords from %s (%d records)", keywords_json_path, len(raw_keywords))

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_keywords):
        name = str(rec.get("name", "")).strip() or f"keyword_{idx}"
        mlentory_id = str(rec.get("mlentory_id", "")).strip() or None

        identifiers: List[str] = []
        if mlentory_id:
            identifiers.append(mlentory_id)

        extraction_meta = rec.get("extraction_metadata") or {}
        if not isinstance(extraction_meta, dict):
            extraction_meta = {}

        # Kaggle groups its tags under a category prefix in fullPath
        # ("analysis > nlp"), which is the vocabulary the term belongs to.
        category = str(rec.get("category", "")).strip()

        payload: Dict[str, Any] = {
            "identifier": identifiers,
            "name": name,
            "url": None,
            "term_code": name,
            "description": str(rec.get("description", "")).strip() or None,
            "extraction_metadata": extraction_meta,
        }
        if category:
            payload["in_defined_term_set"] = [category]

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
        logger.warning(
            "Normalized %d/%d keywords. Errors: %d (see %s)",
            len(normalized), len(raw_keywords), len(errors), err_path,
        )
    else:
        logger.info("Normalized %d/%d keywords. No errors.", len(normalized), len(raw_keywords))

    return str(out_path)


@asset(
    group_name="kaggle_transformation",
    ins={
        "frameworks_data": AssetIn("kaggle_frameworks_raw"),
        "run_folder_data": AssetIn("kaggle_normalized_model_folder"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_frameworks_normalized(
    frameworks_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize Kaggle frameworks to schema.org DefinedTerm-like format and write
    <normalized_folder>/frameworks.json with IRI keys.
    """
    frameworks_json_path, _raw_run_folder = frameworks_data
    _raw_models_json_path, normalized_folder = run_folder_data

    out_path = Path(normalized_folder) / "frameworks.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not frameworks_json_path:
        logger.info("No frameworks_json_path. Writing empty frameworks.json")
        out_path.write_text("[]", encoding="utf-8")
        return str(out_path)

    raw_frameworks = _load_json_records(frameworks_json_path)
    logger.info(
        "Loading Kaggle frameworks from %s (%d records)", frameworks_json_path, len(raw_frameworks)
    )

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_frameworks):
        name = str(rec.get("name", "")).strip() or f"framework_{idx}"
        mlentory_id = str(rec.get("mlentory_id", "")).strip() or None

        extraction_meta = rec.get("extraction_metadata") or {}
        if not isinstance(extraction_meta, dict):
            extraction_meta = {}

        payload: Dict[str, Any] = {
            "identifier": [mlentory_id] if mlentory_id else [],
            "name": name,
            "url": None,
            "term_code": name,
            "description": "Framework a Kaggle model instance ships in.",
            "in_defined_term_set": ["https://www.kaggle.com/models"],
            "extraction_metadata": extraction_meta,
        }

        try:
            obj = DefinedTerm(**payload)
            normalized.append(obj.model_dump(mode="json", by_alias=True))
        except ValidationError as ve:
            errors.append(
                {
                    "framework": name,
                    "_index": idx,
                    "_error": "DefinedTerm validation failed",
                    "details": ve.errors(),
                }
            )
        except Exception as e:
            errors.append(
                {
                    "framework": name,
                    "_index": idx,
                    "_error": str(e),
                    "error_type": type(e).__name__,
                }
            )

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)

    if errors:
        err_path = Path(normalized_folder) / "frameworks_normalization_errors.json"
        with open(err_path, "w", encoding="utf-8") as f:
            json.dump(errors, f, indent=2, ensure_ascii=False)
        logger.warning(
            "Normalized %d/%d frameworks. Errors: %d (see %s)",
            len(normalized), len(raw_frameworks), len(errors), err_path,
        )
    else:
        logger.info("Normalized %d/%d frameworks. No errors.", len(normalized), len(raw_frameworks))

    return str(out_path)


@asset(
    group_name="kaggle_transformation",
    ins={
        "licenses_data": AssetIn("kaggle_licenses_raw"),
        "run_folder_data": AssetIn("kaggle_normalized_model_folder"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_licenses_normalized(
    licenses_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize Kaggle licenses into the schema.org-style output (IRI keys).

    Output file: <normalized_folder>/licenses.json
    """
    licenses_json_path, _raw_run_folder = licenses_data
    _raw_models_json_path, normalized_folder = run_folder_data

    out_path = Path(normalized_folder) / "licenses.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not licenses_json_path:
        logger.info("No licenses_json_path provided. Writing empty licenses.json")
        out_path.write_text("[]", encoding="utf-8")
        return str(out_path)

    raw_licenses = _load_json_records(licenses_json_path)
    logger.info("Loading Kaggle licenses from %s (%d records)", licenses_json_path, len(raw_licenses))

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_licenses):
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

        # Kaggle reports a bare license name with no SPDX identifier or url,
        # so the SPDX-shaped fields stay None.
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
        logger.warning(
            "Normalized %d/%d licenses. Errors written to %s",
            len(normalized), len(raw_licenses), err_path,
        )
    else:
        logger.info("Normalized %d/%d licenses", len(normalized), len(raw_licenses))

    logger.info("Wrote normalized licenses to %s", out_path)
    return str(out_path)


@asset(
    group_name="kaggle_transformation",
    ins={
        "keywords_json": AssetIn("kaggle_keywords_normalized"),
        "licenses_json": AssetIn("kaggle_licenses_normalized"),
        "frameworks_json": AssetIn("kaggle_frameworks_normalized"),
        "sharedby_json": AssetIn("kaggle_sharedby_normalized"),
        "models_json": AssetIn("kaggle_model_normalized"),
        "sources_json": AssetIn("kaggle_sources_normalized"),
        "run_folder_data": AssetIn("kaggle_normalized_model_folder"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_create_translation_mapping(
    keywords_json: str,
    licenses_json: str,
    frameworks_json: str,
    sharedby_json: str,
    models_json: str,
    sources_json: str,
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Create translation mapping: MLentory URI -> human-readable name.

    Reads normalized Kaggle entity JSON files and extracts:
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
        {"label": "keywords", "path": keywords_json},
        {"label": "licenses", "path": licenses_json},
        {"label": "frameworks", "path": frameworks_json},
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
    group_name="kaggle_transformation",
    ins={
        "sharedby_data": AssetIn("kaggle_sharedby_raw"),
        "run_folder_data": AssetIn("kaggle_normalized_model_folder"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "transform"},
)
def kaggle_sharedby_normalized(
    sharedby_data: Tuple[str, str],
    run_folder_data: Tuple[str, str],
) -> str:
    """
    Normalize Kaggle sharedBy entities to schema.org DefinedTerm-like format
    and write <normalized_folder>/sharedby.json with IRI keys.
    """
    sharedby_json_path, _raw_run_folder = sharedby_data
    _raw_models_json_path, normalized_folder = run_folder_data

    out_path = Path(normalized_folder) / "sharedby.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not sharedby_json_path:
        logger.info("No sharedby_json_path. Writing empty sharedby.json")
        out_path.write_text("[]", encoding="utf-8")
        return str(out_path)

    raw_sharedby = _load_json_records(sharedby_json_path)
    logger.info(
        "Loading Kaggle sharedBy entities from %s (%d records)",
        sharedby_json_path, len(raw_sharedby),
    )

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, rec in enumerate(raw_sharedby):
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
            "in_defined_term_set": ["https://www.kaggle.com/models"],
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
            len(normalized), len(raw_sharedby), len(errors), err_path,
        )
    else:
        logger.info(
            "Normalized %d/%d sharedBy entities. No errors.",
            len(normalized), len(raw_sharedby),
        )

    return str(out_path)