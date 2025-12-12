"""
Dagster assets for OpenML → FAIR4ML transformation (flows as models).

Outputs per run (normalized folder /data/2_normalized/openml/<run_id>/):
- datasets.json       (CroissantDataset)
- tasks.json          (DefinedTerm)
- keywords.json       (DefinedTerm)
- runs.json           (run summaries)
- mlmodels.json       (FAIR4ML MLModel)
- entity_linking.json (linkage of flow → datasets/tasks/runs/keywords)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging

from dagster import asset, AssetIn

from etl_transformers.openml import (
    hash_uri,
    make_identifier,
    split_keywords,
    collect_keyword_map,
    normalize_dataset_record,
    normalize_task_record,
    build_keyword_terms,
    normalize_runs,
    build_entity_links,
    normalize_models,
)


logger = logging.getLogger(__name__)


# ---------- helpers ----------


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return list(o)
    return o


def _load_json(path: str) -> Any:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Expected JSON file not found: %s", path)
        return None
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
# ---------- normalized folder ----------


@asset(
    group_name="openml_transformation",
    ins={"runs_data": AssetIn("openml_raw_runs")},
    tags={"pipeline": "openml_etl", "stage": "transform"},
)
def openml_normalized_run_folder(runs_data: Tuple[str, str]) -> Tuple[str, str]:
    """
    Create normalized run folder mirroring raw run folder name.
    """
    runs_json_path, raw_run_folder = runs_data
    folder_name = Path(raw_run_folder).name
    normalized_folder = Path("/data/2_normalized/openml") / folder_name
    normalized_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Created normalized folder %s", normalized_folder)
    return (runs_json_path, str(normalized_folder))


# ---------- datasets ----------


@asset(
    group_name="openml_transformation",
    ins={
        "datasets_json": AssetIn("openml_enriched_datasets"),
        "normalized_folder_data": AssetIn("openml_normalized_run_folder"),
    },
    tags={"pipeline": "openml_etl", "stage": "transform"},
)
def openml_datasets_normalized(
    datasets_json: str,
    normalized_folder_data: Tuple[str, str],
) -> str:
    _, normalized_folder = normalized_folder_data
    records = _load_json(datasets_json) or []

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for record in records:
        try:
            normalized.append(normalize_dataset_record(record))
        except Exception as exc:  # ValidationError or other
            errors.append({"dataset_id": record.get("dataset_id"), "error": str(exc), "raw": record})

    output_path = Path(normalized_folder) / "datasets.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, indent=2, ensure_ascii=False, default=_json_default)
    if errors:
        errors_path = Path(normalized_folder) / "datasets_transformation_errors.json"
        with open(errors_path, "w", encoding="utf-8") as handle:
            json.dump(errors, handle, indent=2, ensure_ascii=False)
        logger.warning("Datasets normalization had %s errors -> %s", len(errors), errors_path)
    logger.info("Wrote %s datasets to %s", len(normalized), output_path)
    return str(output_path)


# ---------- tasks ----------


@asset(
    group_name="openml_transformation",
    ins={
        "tasks_json": AssetIn("openml_enriched_tasks"),
        "normalized_folder_data": AssetIn("openml_normalized_run_folder"),
    },
    tags={"pipeline": "openml_etl", "stage": "transform"},
)
def openml_tasks_normalized(
    tasks_json: str,
    normalized_folder_data: Tuple[str, str],
) -> str:
    _, normalized_folder = normalized_folder_data
    records = _load_json(tasks_json) or []

    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for record in records:
        try:
            normalized.append(normalize_task_record(record))
        except Exception as exc:
            errors.append({"task_id": record.get("task_id"), "error": str(exc), "raw": record})

    output_path = Path(normalized_folder) / "tasks.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, indent=2, ensure_ascii=False, default=_json_default)
    if errors:
        errors_path = Path(normalized_folder) / "tasks_transformation_errors.json"
        with open(errors_path, "w", encoding="utf-8") as handle:
            json.dump(errors, handle, indent=2, ensure_ascii=False)
        logger.warning("Tasks normalization had %s errors -> %s", len(errors), errors_path)
    logger.info("Wrote %s tasks to %s", len(normalized), output_path)
    return str(output_path)


# ---------- keywords ----------


@asset(
    group_name="openml_transformation",
    ins={
        "runs_data": AssetIn("openml_raw_runs"),
        "flows_json": AssetIn("openml_enriched_flows"),
        "normalized_folder_data": AssetIn("openml_normalized_run_folder"),
    },
    tags={"pipeline": "openml_etl", "stage": "transform"},
)
def openml_keywords_normalized(
    runs_data: Tuple[str, str],
    flows_json: str,
    normalized_folder_data: Tuple[str, str],
) -> str:
    runs_json_path, _ = runs_data
    _, normalized_folder = normalized_folder_data

    runs = _load_json(runs_json_path) or []
    flows = _load_json(flows_json) or []

    keyword_map = collect_keyword_map(runs, flows)
    normalized = build_keyword_terms(keyword_map)
    output_path = Path(normalized_folder) / "keywords.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, indent=2, ensure_ascii=False, default=_json_default)
    logger.info("Wrote %s keywords to %s", len(normalized), output_path)
    return str(output_path)


# ---------- runs ----------


@asset(
    group_name="openml_transformation",
    ins={
        "runs_data": AssetIn("openml_raw_runs"),
        "datasets_json": AssetIn("openml_enriched_datasets"),
        "tasks_json": AssetIn("openml_enriched_tasks"),
        "flows_json": AssetIn("openml_enriched_flows"),
        "normalized_folder_data": AssetIn("openml_normalized_run_folder"),
    },
    tags={"pipeline": "openml_etl", "stage": "transform"},
)
def openml_runs_normalized(
    runs_data: Tuple[str, str],
    datasets_json: str,
    tasks_json: str,
    flows_json: str,
    normalized_folder_data: Tuple[str, str],
) -> str:
    runs_json_path, _ = runs_data
    _, normalized_folder = normalized_folder_data

    runs = _load_json(runs_json_path) or []
    datasets = _load_json(datasets_json) or []
    tasks = _load_json(tasks_json) or []
    flows = _load_json(flows_json) or []

    dataset_uri_map = {d.get("dataset_id"): hash_uri("Dataset", d.get("dataset_id")) for d in datasets}
    task_uri_map = {t.get("task_id"): hash_uri("Task", t.get("task_id")) for t in tasks}
    flow_uri_map = {f.get("flow_id"): hash_uri("Flow", f.get("flow_id")) for f in flows}
    keyword_map = collect_keyword_map(runs, flows)

    normalized = normalize_runs(
        runs=runs,
        dataset_uri_map=dataset_uri_map,
        task_uri_map=task_uri_map,
        flow_uri_map=flow_uri_map,
        keyword_map=keyword_map,
    )

    output_path = Path(normalized_folder) / "runs.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, indent=2, ensure_ascii=False, default=_json_default)
    logger.info("Wrote %s runs to %s", len(normalized), output_path)
    return str(output_path)


# ---------- entity linking ----------


@asset(
    group_name="openml_transformation",
    ins={
        "runs_normalized": AssetIn("openml_runs_normalized"),
        "flows_json": AssetIn("openml_enriched_flows"),
        "normalized_folder_data": AssetIn("openml_normalized_run_folder"),
    },
    tags={"pipeline": "openml_etl", "stage": "transform"},
)
def openml_entity_linking(
    runs_normalized: str,
    flows_json: str,
    normalized_folder_data: Tuple[str, str],
) -> str:
    _, normalized_folder = normalized_folder_data
    runs = _load_json(runs_normalized) or []
    flows = _load_json(flows_json) or []

    flow_uri_map = {f.get("flow_id"): hash_uri("Flow", f.get("flow_id")) for f in flows}
    flow_links = build_entity_links(runs, flow_uri_map)

    output_path = Path(normalized_folder) / "entity_linking.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(flow_links, handle, indent=2, ensure_ascii=False, default=_json_default)
    logger.info("Wrote entity linking for %s flows to %s", len(flow_links), output_path)
    return str(output_path)


# ---------- models ----------


@asset(
    group_name="openml_transformation",
    ins={
        "flows_json": AssetIn("openml_enriched_flows"),
        "runs_normalized": AssetIn("openml_runs_normalized"),
        "tasks_json": AssetIn("openml_enriched_tasks"),
        "datasets_json": AssetIn("openml_enriched_datasets"),
        "normalized_folder_data": AssetIn("openml_normalized_run_folder"),
    },
    tags={"pipeline": "openml_etl", "stage": "transform"},
)
def openml_models_normalized(
    flows_json: str,
    runs_normalized: str,
    tasks_json: str,
    datasets_json: str,
    normalized_folder_data: Tuple[str, str],
) -> Tuple[str, str]:
    _, normalized_folder = normalized_folder_data

    flows = _load_json(flows_json) or []
    runs = _load_json(runs_normalized) or []
    tasks = _load_json(tasks_json) or []
    datasets = _load_json(datasets_json) or []

    # Use raw runs to build keyword map (for full tag coverage)
    raw_runs = _load_json(normalized_folder_data[0]) or []
    keyword_map = collect_keyword_map(raw_runs, flows)

    normalized_models = normalize_models(
        flows=flows,
        runs=runs,
        keyword_map=keyword_map,
    )

    output_path = Path(normalized_folder) / "mlmodels.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(normalized_models, handle, indent=2, ensure_ascii=False, default=_json_default)
    logger.info("Wrote %s models to %s", len(normalized_models), output_path)

    return (str(output_path), str(normalized_folder))

