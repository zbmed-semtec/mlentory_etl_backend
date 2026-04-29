"""
Dagster assets for AI4Life loading (Neo4j RDF + Elasticsearch).
"""

from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, Tuple

from dagster import AssetIn, asset
from elasticsearch_dsl import connections

from etl.config import get_general_config
from etl_loaders.elasticsearch_store import ElasticsearchConfig, create_elasticsearch_client, clean_index
from etl_loaders.index_loader import ModelDocument, build_model_document, check_elasticsearch_connection
from etl_loaders.rdf_loader import (
    build_and_persist_models_rdf,
    build_and_persist_licenses_rdf,
    build_and_persist_sources_rdf,
    build_and_persist_datasets_rdf,
    build_and_persist_defined_terms_rdf,
    build_and_persist_tasks_rdf,
    build_and_persist_languages_rdf,
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


@asset(
    group_name="ai4life_loading",
    tags={"pipeline": "ai4life_etl", "stage": "load"}
)
def ai4life_rdf_store_ready() -> Dict[str, Any]:
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
            logger.warning("N10S_RESET_ON_CONFIG_CHANGE=true -> resetting database and re-initializing n10s")
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
    group_name="ai4life_loading",
    ins={
        "normalized_models": AssetIn("ai4life_model_normalized"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"},
)
def ai4life_load_models_to_neo4j(
    normalized_models: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized AI4Life models as RDF triples into Neo4j."""
    mlmodels_json_path = normalized_models
    normalized_folder = str(Path(mlmodels_json_path).parent)

    logger.info(f"Loading RDF from normalized models: {mlmodels_json_path}")
    logger.info(f"Neo4j store status: {store_ready['status']}")

    if not Path(mlmodels_json_path).exists():
        raise FileNotFoundError(f"mlmodels.json not found: {mlmodels_json_path}")

    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "ai4life"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

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
    rdf_report_path = rdf_run_folder / "mlmodels_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="ai4life_loading",
    ins={
        "licenses_normalized": AssetIn("ai4life_licenses_normalized"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"}
)
def ai4life_load_licenses_to_neo4j(
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
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )

    normalized_path = Path(normalized_folder)
    rdf_run_folder = normalized_path.parent.parent.parent / "3_rdf" / "ai4life" / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
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
    rdf_report_path = rdf_run_folder / "licenses_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="ai4life_loading",
    ins={
        "sources_normalized": AssetIn("ai4life_sources_normalized"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"},
)
def ai4life_load_sources_to_neo4j(
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
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    normalized_path = Path(normalized_folder)
    rdf_run_folder = normalized_path.parent.parent.parent / "3_rdf" / "ai4life" / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
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
    rdf_report_path = rdf_run_folder / "sources_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="ai4life_loading",
    ins={
        "keywords_normalized": AssetIn("ai4life_keywords_normalized"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"}
)
def ai4life_load_keywords_to_neo4j(
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
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    normalized_path = Path(normalized_folder)
    rdf_run_folder = normalized_path.parent.parent.parent / "3_rdf" / "ai4life" / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
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
    rdf_report_path = rdf_run_folder / "keywords_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="ai4life_loading",
    ins={
        "datasets_normalized": AssetIn("ai4life_datasets_normalized"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"}
)
def ai4life_load_datasets_to_neo4j(
    datasets_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized datasets as RDF triples into Neo4j."""
    if not datasets_normalized or datasets_normalized == "":
        logger.info("No datasets to load (empty input)")
        return ("", "")
    datasets_path = Path(datasets_normalized)
    if not datasets_path.exists():
        logger.warning(f"Datasets JSON not found: {datasets_normalized}")
        return ("", "")

    normalized_folder = str(datasets_path.parent)
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    normalized_path = Path(normalized_folder)
    rdf_run_folder = normalized_path.parent.parent.parent / "3_rdf" / "ai4life" / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    ttl_path = rdf_run_folder / "datasets.ttl"
    load_stats = build_and_persist_datasets_rdf(
        json_path=datasets_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )
    report = {
        "input_file": datasets_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    rdf_report_path = rdf_run_folder / "datasets_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="ai4life_loading",
    ins={
        "tasks_normalized": AssetIn("ai4life_tasks_normalized"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"}
)
def ai4life_load_tasks_to_neo4j(
    tasks_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized tasks as RDF triples into Neo4j."""
    if not tasks_normalized or tasks_normalized == "":
        logger.info("No tasks to load (empty input)")
        return ("", "")
    tasks_path = Path(tasks_normalized)
    if not tasks_path.exists():
        logger.warning(f"Tasks JSON not found: {tasks_normalized}")
        return ("", "")

    normalized_folder = str(tasks_path.parent)
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    normalized_path = Path(normalized_folder)
    rdf_run_folder = normalized_path.parent.parent.parent / "3_rdf" / "ai4life" / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    ttl_path = rdf_run_folder / "tasks.ttl"
    load_stats = build_and_persist_tasks_rdf(
        json_path=tasks_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )
    report = {
        "input_file": tasks_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    rdf_report_path = rdf_run_folder / "tasks_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="ai4life_loading",
    ins={
        "languages_normalized": AssetIn("ai4life_languages_normalized"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"}
)
def ai4life_load_languages_to_neo4j(
    languages_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized languages as RDF triples into Neo4j."""
    if not languages_normalized or languages_normalized == "":
        logger.info("No languages to load (empty input)")
        return ("", "")
    languages_path = Path(languages_normalized)
    if not languages_path.exists():
        logger.warning(f"Languages JSON not found: {languages_normalized}")
        return ("", "")

    normalized_folder = str(languages_path.parent)
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    normalized_path = Path(normalized_folder)
    rdf_run_folder = normalized_path.parent.parent.parent / "3_rdf" / "ai4life" / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    ttl_path = rdf_run_folder / "languages.ttl"
    load_stats = build_and_persist_languages_rdf(
        json_path=languages_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )
    report = {
        "input_file": languages_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    rdf_report_path = rdf_run_folder / "languages_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="ai4life_loading",
    ins={
        "sharedby_normalized": AssetIn("ai4life_sharedby_normalized"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"}
)
def ai4life_load_sharedby_to_neo4j(
    sharedby_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """Load normalized sharedBy entities as RDF triples into Neo4j."""
    if not sharedby_normalized or sharedby_normalized == "":
        logger.info("No sharedBy entities to load (empty input)")
        return ("", "")
    sharedby_path = Path(sharedby_normalized)
    if not sharedby_path.exists():
        logger.warning(f"SharedBy JSON not found: {sharedby_normalized}")
        return ("", "")

    normalized_folder = str(sharedby_path.parent)
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    normalized_path = Path(normalized_folder)
    rdf_run_folder = normalized_path.parent.parent.parent / "3_rdf" / "ai4life" / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    ttl_path = rdf_run_folder / "sharedby.ttl"
    load_stats = build_and_persist_defined_terms_rdf(
        json_path=sharedby_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
        entity_label="sharedby",
    )
    report = {
        "input_file": sharedby_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    rdf_report_path = rdf_run_folder / "sharedby_load_report.json"
    with open(rdf_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="ai4life_loading",
    ins={
        "models_loaded": AssetIn("ai4life_load_models_to_neo4j"),
        "store_ready": AssetIn("ai4life_rdf_store_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "load"},
)
def ai4life_export_metadata_json(
    models_loaded: Tuple[str, str],
    store_ready: Dict[str, Any],
) -> str:
    """Export metadata graph JSON for AI4Life run."""
    models_report_path, normalized_folder = models_loaded
    normalized_path = Path(normalized_folder)
    rdf_run_folder = normalized_path.parent.parent.parent / "3_rdf" / "ai4life" / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

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
    group_name="ai4life_loading",
    tags={"pipeline": "ai4life_etl", "stage": "index"},
)
def ai4life_elasticsearch_ready() -> Dict[str, Any]:
    """Verify Elasticsearch is configured and ready for AI4Life indexing."""
    status = check_elasticsearch_connection()
    ai4life_index = os.getenv("ELASTIC_AI4LIFE_MODELS_INDEX", "ai4life_models")
    status["ai4life_models_index"] = ai4life_index

    if get_general_config().clean_elasticsearch_index:
        cfg = ElasticsearchConfig.from_env()
        clean_index(ai4life_index, cfg=cfg)
    return status


@asset(
    group_name="ai4life_loading",
    ins={
        "normalized_models": AssetIn("ai4life_model_normalized"),
        "translation_mapping": AssetIn("ai4life_create_translation_mapping"),
        "tasks_normalized": AssetIn("ai4life_tasks_normalized"),
        "sharedby_normalized": AssetIn("ai4life_sharedby_normalized"),
        "es_ready": AssetIn("ai4life_elasticsearch_ready"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "index"},
)
def ai4life_index_models_elasticsearch(
    normalized_models: str,
    translation_mapping: str,
    tasks_normalized: str,
    sharedby_normalized: str,
    es_ready: Dict[str, Any],
) -> str:
    """Index AI4Life models into Elasticsearch (reusing HF document builder)."""
    if not tasks_normalized:
        logger.info("No AI4Life tasks normalized input provided; continuing with model indexing")
    if not sharedby_normalized:
        logger.info("No AI4Life sharedBy normalized input provided; continuing with model indexing")

    mlmodels_json_path = normalized_models
    normalized_folder = str(Path(mlmodels_json_path).parent)
    rdf_run_folder = Path(normalized_folder).parent.parent.parent / "3_rdf" / "ai4life" / Path(normalized_folder).name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

    json_file = Path(mlmodels_json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized models file not found: {mlmodels_json_path}")

    with open(json_file, "r", encoding="utf-8") as f:
        models = json.load(f)
    if not isinstance(models, list):
        raise ValueError(f"Expected list of models, got {type(models).__name__}")

    with open(translation_mapping, "r", encoding="utf-8") as f:
        translation_map = json.load(f)
    if not isinstance(translation_map, dict):
        raise ValueError(f"Expected dict translation mapping, got {type(translation_map).__name__}")

    cfg = ElasticsearchConfig.from_env()
    es_client = create_elasticsearch_client(cfg)
    connections.add_connection("default", es_client)

    index_name = es_ready.get("ai4life_models_index") or os.getenv("ELASTIC_AI4LIFE_MODELS_INDEX", "ai4life_models")
    ModelDocument.init(index=index_name, using=es_client)

    indexed = 0
    errors = 0
    for idx, model in enumerate(models):
        try:
            doc = build_model_document(model, index_name, translation_map)
            doc.meta.index = index_name
            doc.save(using=es_client, refresh=False)
            indexed += 1
        except Exception as exc:
            errors += 1
            identifier = model.get("https://schema.org/identifier", f"unknown_{idx}")
            logger.error("Error indexing AI4Life model %s: %s", identifier, exc, exc_info=True)

    stats = {
        "models_indexed": indexed,
        "errors": errors,
        "index": index_name,
        "input_file": str(json_file),
        "normalized_folder": normalized_folder,
        "cluster_name": es_ready.get("cluster_name"),
        "rdf_run_folder": str(rdf_run_folder),
    }
    elasticsearch_report_path = rdf_run_folder / "elasticsearch_report.json"
    with open(elasticsearch_report_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    return str(elasticsearch_report_path)
