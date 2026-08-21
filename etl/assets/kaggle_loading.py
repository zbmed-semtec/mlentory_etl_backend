"""
Dagster assets for Kaggle loading (Neo4j RDF + Elasticsearch).
"""

from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

from dagster import AssetIn, asset

from etl.config import get_general_config
from etl_loaders.elasticsearch_store import ElasticsearchConfig, clean_index
from etl_loaders.index_loader import check_elasticsearch_connection, index_models
from etl_loaders.rdf_loader import (
    build_and_persist_models_rdf,
    build_and_persist_licenses_rdf,
    build_and_persist_sources_rdf,
    build_and_persist_defined_terms_rdf,
)
from etl_loaders.metadata_graph import export_metadata_graph_json
from etl_loaders.rdf_store import (
    Neo4jConfig,
    ensure_default_prefixes,
    get_neo4j_store_config_from_env,
    get_neosemantics_config,
    init_neosemantics,
    reset_database,
)

logger = logging.getLogger(__name__)


def _rdf_run_folder(normalized_folder: str) -> Path:
    """
    Mirror a normalized run folder under ``3_rdf/kaggle``.

    ``/data/2_normalized/kaggle/<run>`` -> ``/data/3_rdf/kaggle/<run>``
    """
    normalized_path = Path(normalized_folder)
    rdf_run_folder = (
        normalized_path.parent.parent.parent / "3_rdf" / "kaggle" / normalized_path.name
    )
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    return rdf_run_folder


def _store_config(store_ready: Dict[str, Any]):
    return get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )


def _write_report(rdf_run_folder: Path, entity_label: str, report: Dict[str, Any]) -> str:
    report_path = rdf_run_folder / f"{entity_label}_load_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return str(report_path)


@asset(
    group_name="kaggle_loading",
    tags={"pipeline": "Kaggle_etl", "stage": "load"}
)
def kaggle_rdf_store_ready() -> Dict[str, Any]:
    """Verify Neo4j RDF store is configured and ready."""
    logger.info("Checking Neo4j RDF store readiness...")

    try:
        env_cfg = Neo4jConfig.from_env()
        _ = get_neo4j_store_config_from_env(
            batching=True,
            batch_size=200,
            multithreading=True,
            max_workers=4,
        )
        reset_flag = get_general_config().n10s_reset_on_config_change
        desired_cfg = {"keepCustomDataTypes": True, "handleVocabUris": "SHORTEN"}

        if get_general_config().clean_neo4j_database:
            logger.warning("Cleaning Neo4j database according to general configuration...")
            reset_database(drop_config=False)
        else:
            logger.info("Keeping Neo4j database according to general configuration...")

        if reset_flag:
            logger.warning(
                "N10S_RESET_ON_CONFIG_CHANGE=true -> resetting database and re-initializing n10s"
            )
            reset_database(drop_config=True)
            init_neosemantics(desired_cfg)
        else:
            current_cfg = get_neosemantics_config()
            if not current_cfg:
                init_neosemantics(desired_cfg)
            else:
                logger.info("n10s has existing configuration; skipping re-init on non-empty graph")
        ensure_default_prefixes()

        logger.info(f"Neo4j RDF store configured: uri={env_cfg.uri}, database={env_cfg.database}")
        return {
            "status": "ready",
            "uri": env_cfg.uri,
            "database": env_cfg.database,
            "batching": True,
            "batch_size": 5000,
            "multithreading": True,
            "max_workers": 4,
        }
    except ValueError as e:
        logger.error(f"Neo4j configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error checking Neo4j store: {e}", exc_info=True)
        raise


@asset(
    group_name="kaggle_loading",
    ins={
        "normalized_models": AssetIn("kaggle_model_normalized"),
        "store_ready": AssetIn("kaggle_rdf_store_ready"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "load"},
)
def kaggle_load_models_to_neo4j(
    normalized_models: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized Kaggle models as RDF triples into Neo4j.

    ``mlmodels.json`` holds both models and their instances - a Kaggle model
    is a container and its instances are the downloadable artifacts, each an
    MLModel in its own right - so one loader covers both.
    """
    mlmodels_json_path = normalized_models
    normalized_folder = str(Path(mlmodels_json_path).parent)

    logger.info(f"Loading RDF from normalized models: {mlmodels_json_path}")
    logger.info(f"Neo4j store status: {store_ready['status']}")

    if not Path(mlmodels_json_path).exists():
        raise FileNotFoundError(f"mlmodels.json not found: {mlmodels_json_path}")

    config = _store_config(store_ready)
    rdf_run_folder = _rdf_run_folder(normalized_folder)

    ttl_path = rdf_run_folder / "mlmodels.ttl"
    load_stats = build_and_persist_models_rdf(
        json_path=mlmodels_json_path,
        config=config,
        output_ttl_path=str(ttl_path),
        batch_size=50,
    )

    report = {
        "input_file": mlmodels_json_path,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready.get("uri"),
        "neo4j_database": store_ready.get("database"),
        **load_stats,
    }
    return (_write_report(rdf_run_folder, "mlmodels", report), normalized_folder)


@asset(
    group_name="kaggle_loading",
    ins={
        "licenses_normalized": AssetIn("kaggle_licenses_normalized"),
        "store_ready": AssetIn("kaggle_rdf_store_ready"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "load"}
)
def kaggle_load_licenses_to_neo4j(
    licenses_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized licenses as RDF triples into Neo4j."""
    if not licenses_normalized or licenses_normalized == "":
        logger.info("No licenses to load (empty input)")
        return ("", "")
    licenses_path = Path(licenses_normalized)
    if not licenses_path.exists():
        logger.warning(f"Licenses JSON not found: {licenses_normalized}")
        return ("", "")

    normalized_folder = str(licenses_path.parent)
    config = _store_config(store_ready)
    rdf_run_folder = _rdf_run_folder(normalized_folder)

    ttl_path = rdf_run_folder / "licenses.ttl"
    load_stats = build_and_persist_licenses_rdf(
        json_path=licenses_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )
    report = {
        "input_file": licenses_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    return (_write_report(rdf_run_folder, "licenses", report), normalized_folder)


@asset(
    group_name="kaggle_loading",
    ins={
        "sources_normalized": AssetIn("kaggle_sources_normalized"),
        "store_ready": AssetIn("kaggle_rdf_store_ready"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "load"},
)
def kaggle_load_sources_to_neo4j(
    sources_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized source websites as RDF triples into Neo4j."""
    if not sources_normalized or sources_normalized == "":
        logger.info("No sources to load (empty input)")
        return ("", "")

    sources_path = Path(sources_normalized)
    if not sources_path.exists():
        logger.warning(f"Sources JSON not found: {sources_normalized}")
        return ("", "")

    normalized_folder = str(sources_path.parent)
    config = _store_config(store_ready)
    rdf_run_folder = _rdf_run_folder(normalized_folder)

    ttl_path = rdf_run_folder / "sources.ttl"
    load_stats = build_and_persist_sources_rdf(
        json_path=sources_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )
    report = {
        "input_file": sources_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    return (_write_report(rdf_run_folder, "sources", report), normalized_folder)


@asset(
    group_name="kaggle_loading",
    ins={
        "keywords_normalized": AssetIn("kaggle_keywords_normalized"),
        "store_ready": AssetIn("kaggle_rdf_store_ready"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "load"}
)
def kaggle_load_keywords_to_neo4j(
    keywords_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized keywords as RDF triples into Neo4j."""
    if not keywords_normalized or keywords_normalized == "":
        logger.info("No keywords to load (empty input)")
        return ("", "")
    keywords_path = Path(keywords_normalized)
    if not keywords_path.exists():
        logger.warning(f"Keywords JSON not found: {keywords_normalized}")
        return ("", "")

    normalized_folder = str(keywords_path.parent)
    config = _store_config(store_ready)
    rdf_run_folder = _rdf_run_folder(normalized_folder)

    ttl_path = rdf_run_folder / "keywords.ttl"
    load_stats = build_and_persist_defined_terms_rdf(
        json_path=keywords_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
        entity_label="keywords",
    )
    report = {
        "input_file": keywords_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    return (_write_report(rdf_run_folder, "keywords", report), normalized_folder)


@asset(
    group_name="kaggle_loading",
    ins={
        "frameworks_normalized": AssetIn("kaggle_frameworks_normalized"),
        "store_ready": AssetIn("kaggle_rdf_store_ready"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "load"}
)
def kaggle_load_frameworks_to_neo4j(
    frameworks_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized frameworks as RDF triples into Neo4j."""
    if not frameworks_normalized or frameworks_normalized == "":
        logger.info("No frameworks to load (empty input)")
        return ("", "")
    frameworks_path = Path(frameworks_normalized)
    if not frameworks_path.exists():
        logger.warning(f"Frameworks JSON not found: {frameworks_normalized}")
        return ("", "")

    normalized_folder = str(frameworks_path.parent)
    config = _store_config(store_ready)
    rdf_run_folder = _rdf_run_folder(normalized_folder)

    ttl_path = rdf_run_folder / "frameworks.ttl"
    load_stats = build_and_persist_defined_terms_rdf(
        json_path=frameworks_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
        entity_label="frameworks",
    )
    report = {
        "input_file": frameworks_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    return (_write_report(rdf_run_folder, "frameworks", report), normalized_folder)


@asset(
    group_name="kaggle_loading",
    ins={
        "models_loaded": AssetIn("kaggle_load_models_to_neo4j"),
        "store_ready": AssetIn("kaggle_rdf_store_ready"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "load"},
)
def kaggle_export_metadata_json(
    models_loaded: Tuple[str, str],
    store_ready: Dict[str, Any],
) -> str:
    """Export metadata graph JSON for Kaggle run."""
    models_report_path, normalized_folder = models_loaded
    rdf_run_folder = _rdf_run_folder(normalized_folder)

    json_path = rdf_run_folder / "metadata.json"
    rdf_report_path = rdf_run_folder / "metadata_export_report.json"

    enabled = bool(get_general_config().save_loaded_extraction_metadata_file)
    if not enabled:
        report = {
            "status": "skipped",
            "reason": "save_loaded_extraction_metadata_file is disabled in general config",
            "models_report_input": models_report_path,
            "rdf_folder": str(rdf_run_folder),
            "json_file": str(json_path),
            "neo4j_uri": store_ready.get("uri"),
            "neo4j_database": store_ready.get("database"),
        }
        with open(rdf_report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        return str(rdf_report_path)

    export_stats = export_metadata_graph_json(output_json_path=str(json_path))
    report = {
        "status": "ok",
        "models_report_input": models_report_path,
        "rdf_folder": str(rdf_run_folder),
        "json_file": str(json_path),
        "neo4j_uri": store_ready.get("uri"),
        "neo4j_database": store_ready.get("database"),
        **export_stats,
    }
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return str(rdf_report_path)


@asset(
    group_name="kaggle_loading",
    tags={"pipeline": "Kaggle_etl", "stage": "index"},
)
def kaggle_elasticsearch_ready() -> Dict[str, Any]:
    """Verify Elasticsearch is configured and ready for Kaggle indexing."""
    status = check_elasticsearch_connection()
    kaggle_index = os.getenv("ELASTIC_KAGGLE_MODELS_INDEX", "kaggle_models")
    status["kaggle_models_index"] = kaggle_index

    if get_general_config().clean_elasticsearch_index:
        cfg = ElasticsearchConfig.from_env()
        clean_index(kaggle_index, cfg=cfg)
    return status


@asset(
    group_name="kaggle_loading",
    ins={
        "normalized_models": AssetIn("kaggle_model_normalized"),
        "translation_mapping": AssetIn("kaggle_create_translation_mapping"),
        "frameworks_normalized": AssetIn("kaggle_frameworks_normalized"),
        "es_ready": AssetIn("kaggle_elasticsearch_ready"),
    },
    tags={"pipeline": "Kaggle_etl", "stage": "index"},
)
def kaggle_index_models_elasticsearch(
    normalized_models: str,
    translation_mapping: str,
    frameworks_normalized: str,
    es_ready: Dict[str, Any],
) -> str:
    """Index Kaggle models into Elasticsearch (reusing HF document builder)."""
    if not frameworks_normalized:
        logger.info("No Kaggle frameworks normalized input provided; continuing with model indexing")

    mlmodels_json_path = normalized_models
    normalized_folder = str(Path(mlmodels_json_path).parent)
    rdf_run_folder = _rdf_run_folder(normalized_folder)

    json_file = Path(mlmodels_json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized models file not found: {mlmodels_json_path}")

    cfg = ElasticsearchConfig.from_env()
    index_name = es_ready.get("kaggle_models_index") or os.getenv(
        "ELASTIC_KAGGLE_MODELS_INDEX", "kaggle_models"
    )

    stats = index_models(
        json_path=mlmodels_json_path,
        translation_mapping_path=translation_mapping,
        index_name=index_name,
        es_config=cfg,
    )
    stats.update(
        {
            "normalized_folder": normalized_folder,
            "cluster_name": es_ready.get("cluster_name"),
            "rdf_run_folder": str(rdf_run_folder),
        }
    )
    elasticsearch_report_path = rdf_run_folder / "elasticsearch_report.json"
    with open(elasticsearch_report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    return str(elasticsearch_report_path)