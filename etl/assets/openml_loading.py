"""
Dagster assets for OpenML → Neo4j RDF loading.

These reuse the shared platform-agnostic RDF loader (`etl_loaders.rdf_loader`)
and point to OpenML-normalized outputs produced by transformation assets.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from dagster import AssetIn, asset

from etl.config import get_general_config
from etl_loaders.rdf_loader import (
    build_and_persist_models_rdf,
    build_and_persist_datasets_rdf,
    build_and_persist_defined_terms_rdf,
    build_and_persist_runs_rdf,
)
from etl_loaders.metadata_graph import ensure_metadata_graph_constraints
from etl_loaders.openml_index_loader import (
    index_openml_models,
    clean_openml_models_index,
    check_elasticsearch_connection,
)
from etl_loaders.rdf_store import (
    get_neo4j_store_config_from_env,
    Neo4jConfig,
    init_neosemantics,
    ensure_default_prefixes,
    get_neosemantics_config,
    reset_database,
)

logger = logging.getLogger(__name__)


@asset(
    group_name="openml_loading",
    tags={"pipeline": "openml_etl", "stage": "load"},
)
def openml_rdf_store_ready() -> Dict[str, Any]:
    """
    Verify Neo4j RDF store is configured and ready for OpenML loads.
    """
    logger.info("Checking Neo4j RDF store readiness for OpenML...")

    env_cfg = Neo4jConfig.from_env()
    store_cfg = get_neo4j_store_config_from_env(
        batching=True,
        batch_size=200,
        multithreading=True,
        max_workers=4,
    )

    reset_flag = os.getenv("N10S_RESET_ON_CONFIG_CHANGE", "false").lower() == "true"
    desired_cfg = {"keepCustomDataTypes": True, "handleVocabUris": "SHORTEN"}

    if get_general_config().clean_neo4j_database:
        logger.warning("Cleaning Neo4j database according to general configuration...")
        reset_database(drop_config=False)
    else:
        logger.info("Keeping Neo4j database according to general configuration...")

    if reset_flag:
        logger.warning("N10S_RESET_ON_CONFIG_CHANGE=true → resetting database and re-initializing n10s")
        reset_database(drop_config=True)
        init_neosemantics(desired_cfg)
    else:
        current_cfg = get_neosemantics_config()
        if not current_cfg:
            init_neosemantics(desired_cfg)
        else:
            logger.info("n10s has existing configuration; skipping re-init on non-empty graph")

    ensure_default_prefixes()
    ensure_metadata_graph_constraints()

    return {
        "status": "ready",
        "uri": env_cfg.uri,
        "database": env_cfg.database,
        "batching": True,
        "batch_size": 5000,
        "multithreading": True,
        "max_workers": 4,
    }


@asset(
    group_name="openml_loading",
    tags={"pipeline": "openml_etl", "stage": "load"},
)
def openml_elasticsearch_ready() -> Dict[str, Any]:
    """
    Verify Elasticsearch connection for OpenML indexing.
    """
    logger.info("Checking Elasticsearch readiness for OpenML...")
    status = check_elasticsearch_connection()

    if get_general_config().clean_elasticsearch_index:
        logger.warning("Cleaning OpenML Elasticsearch index according to general configuration...")
        clean_openml_models_index()

    logger.info("OpenML Elasticsearch status: %s", status)
    return status


@asset(
    group_name="openml_loading",
    ins={
        "store_ready": AssetIn("openml_rdf_store_ready"),
        "models_data": AssetIn("openml_models_normalized"),
        "datasets_loaded": AssetIn("openml_load_datasets_to_neo4j"),
        "tasks_loaded": AssetIn("openml_load_tasks_to_neo4j"),
        "keywords_loaded": AssetIn("openml_load_keywords_to_neo4j"),
        "runs_loaded": AssetIn("openml_load_runs_to_neo4j"),
    },
    tags={"pipeline": "openml_etl", "stage": "load"},
)
def openml_load_models_to_neo4j(
    store_ready: Dict[str, Any],
    models_data: Tuple[str, str],
    datasets_loaded: Tuple[str, str],
    tasks_loaded: Tuple[str, str],
    keywords_loaded: Tuple[str, str],
    runs_loaded: Tuple[str, str],
) -> Tuple[str, str]:
    """
    Build and persist RDF triples for OpenML models (mlmodels.json).
    
    This asset depends on all other entity loaders (datasets, tasks, keywords, runs)
    to ensure referenced entities exist before models create relationships to them.
    """
    models_json_path, normalized_folder = models_data
    if not models_json_path:
        logger.info("No models to load (empty input)")
        return ("", "")

    models_path = Path(models_json_path)
    if not models_path.exists():
        logger.warning("Models JSON not found: %s", models_json_path)
        return ("", "")

    logger.info("Loading RDF from OpenML normalized models: %s", models_json_path)
    logger.info("Neo4j store status: %s", store_ready.get("status", "ready"))

    cfg = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", store_ready.get("store_config", {}).get("batching", True)),
        batch_size=store_ready.get("batch_size", store_ready.get("store_config", {}).get("batch_size", 5000)),
        multithreading=store_ready.get("multithreading", store_ready.get("store_config", {}).get("multithreading", True)),
        max_workers=store_ready.get("max_workers", store_ready.get("store_config", {}).get("max_workers", 4)),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "openml"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    logger.info("OpenML RDF outputs will be saved to: %s", rdf_run_folder)

    ttl_path = rdf_run_folder / "mlmodels.ttl"
    load_stats = build_and_persist_models_rdf(
        json_path=models_json_path,
        config=cfg,
        output_ttl_path=str(ttl_path),
    )
    logger.info(
        "RDF loading complete: %s models, %s triples, %s errors",
        load_stats.get("models_processed"),
        load_stats.get("triples_added"),
        load_stats.get("errors"),
    )

    report = {
        "input_file": models_json_path,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready.get("uri"),
        "neo4j_database": store_ready.get("database"),
        **load_stats,
    }

    rdf_report_path = rdf_run_folder / "mlmodels_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    logger.info("Models load report saved to: %s", rdf_report_path)

    return (str(rdf_report_path), str(normalized_folder))


@asset(
    group_name="openml_loading",
    ins={
        "elasticsearch_ready": AssetIn("openml_elasticsearch_ready"),
        "models_data": AssetIn("openml_models_normalized"),
        "translation_mapping": AssetIn("openml_create_translation_mapping"),
    },
    tags={"pipeline": "openml_etl", "stage": "load"},
)
def openml_index_models(
    elasticsearch_ready: Dict[str, Any],
    models_data: Tuple[str, str],
    translation_mapping: str,
) -> str:
    """
    Index OpenML models into Elasticsearch.
    """
    models_json_path, normalized_folder = models_data
    rdf_base_folder = Path(normalized_folder).parent.parent.parent / "3_rdf" / "openml"
    rdf_run_folder = rdf_base_folder / Path(normalized_folder).name

    logger.info(
        "Indexing OpenML models into Elasticsearch from %s (normalized_folder=%s)",
        models_json_path,
        normalized_folder,
    )

    stats = index_openml_models(
        json_path=models_json_path,
        translation_mapping_path=translation_mapping,
    )
    stats["normalized_folder"] = normalized_folder
    stats["cluster_name"] = elasticsearch_ready.get("cluster_name")
    stats["rdf_run_folder"] = str(rdf_run_folder)

    elasticsearch_report_path = rdf_run_folder / "elasticsearch_report.json"
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    with open(elasticsearch_report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    logger.info("OpenML Elasticsearch report saved to: %s", elasticsearch_report_path)

    return str(elasticsearch_report_path)


@asset(
    group_name="openml_loading",
    ins={
        "store_ready": AssetIn("openml_rdf_store_ready"),
        "datasets_json": AssetIn("openml_datasets_normalized"),
    },
    tags={"pipeline": "openml_etl", "stage": "load"},
)
def openml_load_datasets_to_neo4j(
    store_ready: Dict[str, Any],
    datasets_json: str,
) -> Tuple[str, str]:
    """
    Build and persist RDF triples for OpenML datasets.
    """
    if not datasets_json:
        logger.info("No datasets to load (empty input)")
        return ("", "")

    datasets_path = Path(datasets_json)
    if not datasets_path.exists():
        logger.warning("Datasets JSON not found: %s", datasets_json)
        return ("", "")

    normalized_folder = str(datasets_path.parent)
    logger.info("Loading RDF from OpenML normalized datasets: %s", datasets_json)
    logger.info("Neo4j store status: %s", store_ready.get("status", "ready"))

    cfg = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", store_ready.get("store_config", {}).get("batching", True)),
        batch_size=store_ready.get("batch_size", store_ready.get("store_config", {}).get("batch_size", 5000)),
        multithreading=store_ready.get("multithreading", store_ready.get("store_config", {}).get("multithreading", True)),
        max_workers=store_ready.get("max_workers", store_ready.get("store_config", {}).get("max_workers", 4)),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "openml"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Dataset RDF outputs will be saved to: %s", rdf_run_folder)

    ttl_path = rdf_run_folder / "datasets.ttl"
    load_stats = build_and_persist_datasets_rdf(
        json_path=datasets_json,
        config=cfg,
        output_ttl_path=str(ttl_path),
    )
    logger.info(
        "RDF loading complete: %s datasets, %s triples, %s errors",
        load_stats.get("datasets_processed"),
        load_stats.get("triples_added"),
        load_stats.get("errors"),
    )

    report = {
        "input_file": datasets_json,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready.get("uri"),
        "neo4j_database": store_ready.get("database"),
        **load_stats,
    }

    rdf_report_path = rdf_run_folder / "datasets_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    logger.info("Datasets load report saved to: %s", rdf_report_path)

    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="openml_loading",
    ins={
        "store_ready": AssetIn("openml_rdf_store_ready"),
        "runs_json": AssetIn("openml_runs_normalized"),
    },
    tags={"pipeline": "openml_etl", "stage": "load"},
)
def openml_load_runs_to_neo4j(
    store_ready: Dict[str, Any],
    runs_json: str,
) -> Tuple[str, str]:
    """
    Build and persist RDF triples for OpenML runs (MLModelEvaluation).
    """
    if not runs_json:
        logger.info("No runs to load (empty input)")
        return ("", "")

    runs_path = Path(runs_json)
    if not runs_path.exists():
        logger.warning("Runs JSON not found: %s", runs_json)
        return ("", "")

    normalized_folder = str(runs_path.parent)
    logger.info("Loading RDF from OpenML normalized runs: %s", runs_json)
    logger.info("Neo4j store status: %s", store_ready.get("status", "ready"))

    cfg = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", store_ready.get("store_config", {}).get("batching", True)),
        batch_size=store_ready.get("batch_size", store_ready.get("store_config", {}).get("batch_size", 5000)),
        multithreading=store_ready.get("multithreading", store_ready.get("store_config", {}).get("multithreading", True)),
        max_workers=store_ready.get("max_workers", store_ready.get("store_config", {}).get("max_workers", 4)),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "openml"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Run RDF outputs will be saved to: %s", rdf_run_folder)

    ttl_path = rdf_run_folder / "runs.ttl"
    load_stats = build_and_persist_runs_rdf(
        json_path=runs_json,
        config=cfg,
        output_ttl_path=str(ttl_path),
    )
    logger.info(
        "RDF loading complete: %s runs, %s triples, %s errors",
        load_stats.get("runs_processed"),
        load_stats.get("triples_added"),
        load_stats.get("errors"),
    )

    report = {
        "input_file": runs_json,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready.get("uri"),
        "neo4j_database": store_ready.get("database"),
        **load_stats,
    }

    rdf_report_path = rdf_run_folder / "runs_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    logger.info("Runs load report saved to: %s", rdf_report_path)

    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="openml_loading",
    ins={
        "store_ready": AssetIn("openml_rdf_store_ready"),
        "tasks_json": AssetIn("openml_tasks_normalized"),
    },
    tags={"pipeline": "openml_etl", "stage": "load"},
)
def openml_load_tasks_to_neo4j(
    store_ready: Dict[str, Any],
    tasks_json: str,
) -> Tuple[str, str]:
    """
    Build and persist RDF triples for OpenML tasks (DefinedTerm).
    """
    if not tasks_json:
        logger.info("No tasks to load (empty input)")
        return ("", "")

    tasks_path = Path(tasks_json)
    if not tasks_path.exists():
        logger.warning("Tasks JSON not found: %s", tasks_json)
        return ("", "")

    normalized_folder = str(tasks_path.parent)
    logger.info("Loading RDF from OpenML normalized tasks: %s", tasks_json)
    logger.info("Neo4j store status: %s", store_ready.get("status", "ready"))

    cfg = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", store_ready.get("store_config", {}).get("batching", True)),
        batch_size=store_ready.get("batch_size", store_ready.get("store_config", {}).get("batch_size", 5000)),
        multithreading=store_ready.get("multithreading", store_ready.get("store_config", {}).get("multithreading", True)),
        max_workers=store_ready.get("max_workers", store_ready.get("store_config", {}).get("max_workers", 4)),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "openml"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Task RDF outputs will be saved to: %s", rdf_run_folder)

    ttl_path = rdf_run_folder / "tasks.ttl"
    load_stats = build_and_persist_defined_terms_rdf(
        json_path=tasks_json,
        config=cfg,
        output_ttl_path=str(ttl_path),
        entity_label="tasks",
    )
    logger.info(
        "RDF loading complete: %s tasks, %s triples, %s errors",
        load_stats.get("tasks_processed"),
        load_stats.get("triples_added"),
        load_stats.get("errors"),
    )

    report = {
        "input_file": tasks_json,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready.get("uri"),
        "neo4j_database": store_ready.get("database"),
        **load_stats,
    }

    rdf_report_path = rdf_run_folder / "tasks_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    logger.info("Tasks load report saved to: %s", rdf_report_path)

    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="openml_loading",
    ins={
        "store_ready": AssetIn("openml_rdf_store_ready"),
        "keywords_json": AssetIn("openml_keywords_normalized"),
    },
    tags={"pipeline": "openml_etl", "stage": "load"},
)
def openml_load_keywords_to_neo4j(
    store_ready: Dict[str, Any],
    keywords_json: str,
) -> Tuple[str, str]:
    """
    Build and persist RDF triples for OpenML keywords (DefinedTerm).
    """
    if not keywords_json:
        logger.info("No keywords to load (empty input)")
        return ("", "")

    keywords_path = Path(keywords_json)
    if not keywords_path.exists():
        logger.warning("Keywords JSON not found: %s", keywords_json)
        return ("", "")

    normalized_folder = str(keywords_path.parent)
    logger.info("Loading RDF from OpenML normalized keywords: %s", keywords_json)
    logger.info("Neo4j store status: %s", store_ready.get("status", "ready"))

    cfg = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", store_ready.get("store_config", {}).get("batching", True)),
        batch_size=store_ready.get("batch_size", store_ready.get("store_config", {}).get("batch_size", 5000)),
        multithreading=store_ready.get("multithreading", store_ready.get("store_config", {}).get("multithreading", True)),
        max_workers=store_ready.get("max_workers", store_ready.get("store_config", {}).get("max_workers", 4)),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "openml"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Keyword RDF outputs will be saved to: %s", rdf_run_folder)

    ttl_path = rdf_run_folder / "keywords.ttl"
    load_stats = build_and_persist_defined_terms_rdf(
        json_path=keywords_json,
        config=cfg,
        output_ttl_path=str(ttl_path),
        entity_label="keywords",
    )
    logger.info(
        "RDF loading complete: %s keywords, %s triples, %s errors",
        load_stats.get("keywords_processed"),
        load_stats.get("triples_added"),
        load_stats.get("errors"),
    )

    report = {
        "input_file": keywords_json,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready.get("uri"),
        "neo4j_database": store_ready.get("database"),
        **load_stats,
    }

    rdf_report_path = rdf_run_folder / "keywords_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
    logger.info("Keywords load report saved to: %s", rdf_report_path)

    return (str(rdf_report_path), normalized_folder)

