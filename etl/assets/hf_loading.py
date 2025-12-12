"""
Dagster assets for HuggingFace → Neo4j RDF loading.

This module defines assets for persisting normalized HF FAIR4ML models
as RDF triples into Neo4j using rdflib-neo4j.

Pipeline:
1. hf_rdf_store_ready: Ensure Neo4j store is configured and ready
2. hf_load_models_rdf: Build and persist RDF triples from normalized models
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Tuple

from dagster import AssetIn, asset

from etl.config import get_general_config

from etl_loaders.hf_rdf_loader import (
    build_and_persist_models_rdf,
    build_and_persist_articles_rdf,
    build_and_persist_licenses_rdf,
    build_and_persist_datasets_rdf,
    build_and_persist_tasks_rdf,
    build_and_persist_languages_rdf,
    build_and_persist_defined_terms_rdf,
)
from etl_loaders.hf_index_loader import (
    index_hf_models, 
    check_elasticsearch_connection, 
    clean_hf_models_index,
)
from etl_loaders.metadata_graph import (
    ensure_metadata_graph_constraints,
    cleanup_metadata_graph,
    export_metadata_graph_json,
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
    group_name="hf_loading",
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_rdf_store_ready() -> Dict[str, Any]:
    """
    Verify Neo4j RDF store is configured and ready.
    
    Loads configuration from environment variables and validates connectivity.
    Returns a config marker that downstream assets can depend on.
    
    Returns:
        Dict with store readiness status and config info
        
    Raises:
        ValueError: If required env vars are missing
        ConnectionError: If Neo4j is not reachable
    """
    logger.info("Checking Neo4j RDF store readiness...")
    
    try:
        # Read env for reporting
        env_cfg = Neo4jConfig.from_env()
        # Build store config (may not expose uri/database attributes)
        _ = get_neo4j_store_config_from_env(
            batching=True,
            batch_size=200,
            multithreading=True,
            max_workers=4,
        )
        # Initialize/ensure n10s according to environment flag
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
    group_name="hf_loading",
    ins={
        "normalized_models": AssetIn("hf_models_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_models_to_neo4j(
    normalized_models: Tuple[str, str],
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized HF models as RDF triples into Neo4j.
    
    Builds RDF triples from FAIR4ML models and persists them to Neo4j
    using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        normalized_models: Tuple of (mlmodels_json_path, normalized_folder)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder)
        
    Raises:
        FileNotFoundError: If normalized models file not found
        Exception: If loading fails
    """
    mlmodels_json_path, normalized_folder = normalized_models
    
    logger.info(f"Loading RDF from normalized models: {mlmodels_json_path}")
    logger.info(f"Neo4j store status: {store_ready['status']}")
    
    # Get Neo4j store config
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    
    # Create RDF output directory parallel to normalized
    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent  / "3_rdf" / "hf"  # /data/3_rdf/hf
    rdf_run_folder = rdf_base / normalized_path.name  # Same run ID as normalized
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"RDF outputs will be saved to: {rdf_run_folder}")
    
    # Output Turtle file path
    ttl_path = rdf_run_folder / "mlmodels.ttl"
    
    # Build and persist RDF
    logger.info("Building and persisting RDF triples...")
    load_stats = build_and_persist_models_rdf(
        json_path=mlmodels_json_path,
        config=config,
        output_ttl_path=str(ttl_path),
        batch_size=50,
    )
    
    logger.info(
        f"RDF loading complete: {load_stats['models_processed']} models, "
        f"{load_stats['triples_added']} triples, {load_stats['errors']} errors"
    )
    
    # Write load report to both normalized and RDF folders
    report = {
        "input_file": mlmodels_json_path,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    
    # Save report to RDF folder as well
    rdf_report_path = rdf_run_folder / "mlmodels_load_report.json"
    with open(rdf_report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"Models load report also saved to: {rdf_report_path}")
    
    return (str(rdf_report_path), normalized_folder)

@asset(
    group_name="hf_loading",
    tags={"pipeline": "hf_etl", "stage": "index"}
)
def hf_elasticsearch_ready() -> Dict[str, Any]:
    """
    Verify Elasticsearch is configured and ready.
    
    Checks Elasticsearch connection and cluster health.
    Returns connection status and cluster info that downstream assets can depend on.
    
    Returns:
        Dict with connection status, cluster info, and index configuration.
        
    Raises:
        ConnectionError: If Elasticsearch is not reachable.
    """
    logger.info("Checking Elasticsearch readiness...")
    
    try:
        status = check_elasticsearch_connection()
        
        if get_general_config().clean_elasticsearch_index:
            logger.warning("Cleaning Elasticsearch index according to general configuration...")
            clean_hf_models_index()
        
        logger.info(
            "Elasticsearch ready: cluster=%s, status=%s, nodes=%s, index=%s",
            status["cluster_name"],
            status["cluster_status"],
            status["number_of_nodes"],
            status["hf_models_index"],
        )
        return status
    except ConnectionError as e:
        logger.error(f"Elasticsearch connection failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error checking Elasticsearch: {e}", exc_info=True)
        raise

@asset(
    group_name="hf_loading",
    ins={
        "normalized_models": AssetIn("hf_models_normalized"),
        "translation_mapping": AssetIn("hf_create_translation_mapping"),
        "es_ready": AssetIn("hf_elasticsearch_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "index"},
)
def hf_index_models_elasticsearch(
    normalized_models: Tuple[str, str],
    translation_mapping: str,
    es_ready: Dict[str, Any],
) -> str:
    """Index normalized HF models into Elasticsearch for search.

    This asset reads the normalized HF FAIR4ML models JSON (`mlmodels.json`)
    and indexes a subset of properties into an Elasticsearch index using
    the `HFModelDocument` defined in `etl_loaders.hf_index_loader`.

    The target index name and connection details are configured via env vars
    (see `ElasticsearchConfig.from_env`).

    Args:
        normalized_models: Tuple of (mlmodels_json_path, normalized_folder)
        translation_mapping: Path to translation mapping JSON file
        es_ready: Elasticsearch readiness status from hf_elasticsearch_ready

    Returns:
        Dictionary of indexing statistics (models_indexed, errors, index, input_file).
    """
    mlmodels_json_path, normalized_folder = normalized_models
    rdf_base_folder = Path(normalized_folder).parent.parent.parent / "3_rdf" / "hf"
    rdf_run_folder = rdf_base_folder / Path(normalized_folder).name
    translation_mapping_path = translation_mapping
    
    logger.info(
        "Indexing normalized HF models into Elasticsearch from %s "
        "(normalized_folder=%s)",
        mlmodels_json_path,
        normalized_folder,
    )

    stats = index_hf_models(json_path=mlmodels_json_path, translation_mapping_path=translation_mapping_path)
    stats["normalized_folder"] = normalized_folder
    stats["cluster_name"] = es_ready.get("cluster_name")
    stats["rdf_run_folder"] = str(rdf_run_folder)
    
    elasticsearch_report_path = rdf_run_folder / "elasticsearch_report.json"
    with open(elasticsearch_report_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    logger.info(f"Elasticsearch report saved to: {elasticsearch_report_path}")
    
    return str(elasticsearch_report_path)
    

@asset(
    group_name="hf_loading",
    ins={
        "models_loaded": AssetIn("hf_load_models_to_neo4j"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_export_metadata_json(
    models_loaded: Tuple[str, str],
    store_ready: Dict[str, Any],
) -> str:
    """
    Export the MLModel metadata property graph as Neo4j JSON via APOC.

    Uses apoc.export.json.query to export the MLModel–HAS_PROPERTY_SNAPSHOT–
    MLModelPropertySnapshot subgraph to a JSON file on the Neo4j server.

    Args:
        models_loaded: Tuple from hf_load_models_to_neo4j (report_path, normalized_folder)
        store_ready: Store readiness status from hf_rdf_store_ready

    Returns:
        Path to the metadata JSON export report

    Raises:
        Exception: If metadata export fails
    """
    models_report_path, normalized_folder = models_loaded

    logger.info(f"Exporting metadata JSON from models loaded in: {models_report_path}")
    logger.info(f"Neo4j store status: {store_ready['status']}")

    # Create RDF output directory parallel to normalized
    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "hf"
    rdf_run_folder = rdf_base / normalized_path.name  # Same run ID as normalized
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Metadata JSON outputs will be saved to: {rdf_run_folder}")

    # Output JSON file path
    json_path = rdf_run_folder / "metadata.json"

    # Export metadata as JSON
    logger.info("Exporting metadata property graph as Neo4j JSON...")
    export_stats = export_metadata_graph_json(
        output_json_path=str(json_path)
    )

    logger.info(
        f"Metadata JSON export complete: {export_stats['relationships']} relationships"
    )

    # Write export report
    report = {
        "models_report_input": models_report_path,
        "rdf_folder": str(rdf_run_folder),
        "json_file": str(json_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **export_stats,
    }

    # Save report to RDF folder
    rdf_report_path = rdf_run_folder / "metadata_export_report.json"
    with open(rdf_report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"Metadata export report saved to: {rdf_report_path}")

    return str(rdf_report_path)


@asset(
    group_name="hf_loading",
    ins={
        "articles_normalized": AssetIn("hf_articles_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_articles_to_neo4j(
    articles_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized articles as RDF triples into Neo4j.
    
    Builds RDF triples from Schema.org ScholarlyArticle entities and persists them
    to Neo4j using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        articles_normalized: Path to normalized articles JSON (articles.json)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder) or ("", "") if no articles
        
    Raises:
        FileNotFoundError: If normalized articles file not found
        Exception: If loading fails
    """
    # Handle empty articles case
    if not articles_normalized or articles_normalized == "":
        logger.info("No articles to load (empty input)")
        return ("", "")
    
    articles_path = Path(articles_normalized)
    if not articles_path.exists():
        logger.warning(f"Articles JSON not found: {articles_normalized}")
        return ("", "")
    
    normalized_folder = str(articles_path.parent)
    
    logger.info(f"Loading RDF from normalized articles: {articles_normalized}")
    logger.info(f"Neo4j store status: {store_ready['status']}")
    
    # Get Neo4j store config
    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )
    
    # Create RDF output directory parallel to normalized
    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "hf"  # /data/3_rdf/hf
    rdf_run_folder = rdf_base / normalized_path.name  # Same run ID as normalized
    rdf_run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"RDF outputs will be saved to: {rdf_run_folder}")
    
    # Output Turtle file path
    ttl_path = rdf_run_folder / "articles.ttl"
    
    # Build and persist RDF
    logger.info("Building and persisting RDF triples for articles...")
    load_stats = build_and_persist_articles_rdf(
        json_path=articles_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )
    
    logger.info(
        f"RDF loading complete: {load_stats['articles_processed']} articles, "
        f"{load_stats['triples_added']} triples, {load_stats['errors']} errors"
    )
    
    # Write load report to both normalized and RDF folders
    report = {
        "input_file": articles_normalized,
        "rdf_folder": str(rdf_run_folder),
        "ttl_file": str(ttl_path),
        "neo4j_uri": store_ready["uri"],
        "neo4j_database": store_ready["database"],
        **load_stats,
    }
    
    # Save report to RDF folder as well
    rdf_report_path = rdf_run_folder / "articles_load_report.json"
    with open(rdf_report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"Load report also saved to: {rdf_report_path}")
    
    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="hf_loading",
    ins={
        "licenses_normalized": AssetIn("hf_licenses_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_licenses_to_neo4j(
    licenses_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized licenses as RDF triples into Neo4j.
    
    Builds RDF triples from Schema.org CreativeWork entities and persists them
    to Neo4j using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        licenses_normalized: Path to normalized licenses JSON (licenses.json)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder) or ("", "") if no licenses
    """
    if not licenses_normalized or licenses_normalized == "":
        logger.info("No licenses to load (empty input)")
        return ("", "")

    licenses_path = Path(licenses_normalized)
    if not licenses_path.exists():
        logger.warning(f"Licenses JSON not found: {licenses_normalized}")
        return ("", "")

    normalized_folder = str(licenses_path.parent)

    logger.info(f"Loading RDF from normalized licenses: {licenses_normalized}")
    logger.info(f"Neo4j store status: {store_ready['status']}")

    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "hf"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"License RDF outputs will be saved to: {rdf_run_folder}")

    ttl_path = rdf_run_folder / "licenses.ttl"

    logger.info("Building and persisting RDF triples for licenses...")
    load_stats = build_and_persist_licenses_rdf(
        json_path=licenses_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )

    logger.info(
        "RDF loading complete: %s licenses, %s triples, %s errors",
        load_stats["licenses_processed"],
        load_stats["triples_added"],
        load_stats["errors"],
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
    logger.info(f"Licenses load report also saved to: {rdf_report_path}")

    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="hf_loading",
    ins={
        "datasets_normalized": AssetIn("hf_datasets_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_datasets_to_neo4j(
    datasets_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized Croissant datasets as RDF triples into Neo4j.
    
    Builds RDF triples from Croissant Dataset entities (schema:Dataset) and persists
    them to Neo4j using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        datasets_normalized: Path to normalized datasets JSON (datasets.json)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder) or ("", "") if no datasets
    """
    if not datasets_normalized or datasets_normalized == "":
        logger.info("No datasets to load (empty input)")
        return ("", "")

    datasets_path = Path(datasets_normalized)
    if not datasets_path.exists():
        logger.warning(f"Datasets JSON not found: {datasets_normalized}")
        return ("", "")

    normalized_folder = str(datasets_path.parent)

    logger.info(f"Loading RDF from normalized datasets: {datasets_normalized}")
    logger.info(f"Neo4j store status: {store_ready['status']}")

    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "hf"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Dataset RDF outputs will be saved to: {rdf_run_folder}")

    ttl_path = rdf_run_folder / "datasets.ttl"

    logger.info("Building and persisting RDF triples for datasets...")
    load_stats = build_and_persist_datasets_rdf(
        json_path=datasets_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )

    logger.info(
        "RDF loading complete: %s datasets, %s triples, %s errors",
        load_stats["datasets_processed"],
        load_stats["triples_added"],
        load_stats["errors"],
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
    logger.info(f"Datasets load report also saved to: {rdf_report_path}")

    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="hf_loading",
    ins={
        "tasks_normalized": AssetIn("hf_tasks_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_tasks_to_neo4j(
    tasks_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized DefinedTerm tasks as RDF triples into Neo4j.
    
    Builds RDF triples from Schema.org DefinedTerm entities and persists
    them to Neo4j using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        tasks_normalized: Path to normalized tasks JSON (tasks.json)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder) or ("", "") if no tasks
    """
    if not tasks_normalized or tasks_normalized == "":
        logger.info("No tasks to load (empty input)")
        return ("", "")

    tasks_path = Path(tasks_normalized)
    if not tasks_path.exists():
        logger.warning(f"Tasks JSON not found: {tasks_normalized}")
        return ("", "")

    normalized_folder = str(tasks_path.parent)

    logger.info(f"Loading RDF from normalized tasks: {tasks_normalized}")
    logger.info(f"Neo4j store status: {store_ready['status']}")

    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "hf"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Task RDF outputs will be saved to: {rdf_run_folder}")

    ttl_path = rdf_run_folder / "tasks.ttl"

    logger.info("Building and persisting RDF triples for tasks...")
    load_stats = build_and_persist_tasks_rdf(
        json_path=tasks_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )

    logger.info(
        "RDF loading complete: %s tasks, %s triples, %s errors",
        load_stats["tasks_processed"],
        load_stats["triples_added"],
        load_stats["errors"],
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
    logger.info(f"Tasks load report also saved to: {rdf_report_path}")

    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="hf_loading",
    ins={
        "languages_normalized": AssetIn("hf_languages_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_languages_to_neo4j(
    languages_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized Language entities as RDF triples into Neo4j.
    
    Builds RDF triples from Schema.org Language entities and persists
    them to Neo4j using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        languages_normalized: Path to normalized languages JSON (languages.json)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder) or ("", "") if no languages
    """
    if not languages_normalized or languages_normalized == "":
        logger.info("No languages to load (empty input)")
        return ("", "")

    languages_path = Path(languages_normalized)
    if not languages_path.exists():
        logger.warning(f"Languages JSON not found: {languages_normalized}")
        return ("", "")

    normalized_folder = str(languages_path.parent)

    logger.info(f"Loading RDF from normalized languages: {languages_normalized}")
    logger.info(f"Neo4j store status: {store_ready['status']}")

    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "hf"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Language RDF outputs will be saved to: {rdf_run_folder}")

    ttl_path = rdf_run_folder / "languages.ttl"

    logger.info("Building and persisting RDF triples for languages...")
    load_stats = build_and_persist_languages_rdf(
        json_path=languages_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
    )

    logger.info(
        "RDF loading complete: %s languages, %s triples, %s errors",
        load_stats["languages_processed"],
        load_stats["triples_added"],
        load_stats["errors"],
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
    logger.info(f"Languages load report also saved to: {rdf_report_path}")

    return (str(rdf_report_path), normalized_folder)


@asset(
    group_name="hf_loading",
    ins={
        "keywords_normalized": AssetIn("hf_keywords_normalized"),
        "store_ready": AssetIn("hf_rdf_store_ready"),
    },
    tags={"pipeline": "hf_etl", "stage": "load"}
)
def hf_load_keywords_to_neo4j(
    keywords_normalized: str,
    store_ready: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Load normalized DefinedTerm keywords as RDF triples into Neo4j.
    
    Builds RDF triples from Schema.org DefinedTerm entities (keywords) and persists
    them to Neo4j using rdflib-neo4j. Also saves a Turtle (.ttl) file for reference.
    
    Args:
        keywords_normalized: Path to normalized keywords JSON (keywords.json)
        store_ready: Store readiness status from hf_rdf_store_ready
        
    Returns:
        Tuple of (load_report_path, normalized_folder) or ("", "") if no keywords
    """
    if not keywords_normalized or keywords_normalized == "":
        logger.info("No keywords to load (empty input)")
        return ("", "")

    keywords_path = Path(keywords_normalized)
    if not keywords_path.exists():
        logger.warning(f"Keywords JSON not found: {keywords_normalized}")
        return ("", "")

    normalized_folder = str(keywords_path.parent)

    logger.info(f"Loading RDF from normalized keywords: {keywords_normalized}")
    logger.info(f"Neo4j store status: {store_ready['status']}")

    config = get_neo4j_store_config_from_env(
        batching=store_ready.get("batching", True),
        batch_size=store_ready.get("batch_size", 5000),
        multithreading=store_ready.get("multithreading", True),
        max_workers=store_ready.get("max_workers", 4),
    )

    normalized_path = Path(normalized_folder)
    rdf_base = normalized_path.parent.parent.parent / "3_rdf" / "hf"
    rdf_run_folder = rdf_base / normalized_path.name
    rdf_run_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Keyword RDF outputs will be saved to: {rdf_run_folder}")

    ttl_path = rdf_run_folder / "keywords.ttl"

    logger.info("Building and persisting RDF triples for keywords...")
    load_stats = build_and_persist_defined_terms_rdf(
        json_path=keywords_normalized,
        config=config,
        output_ttl_path=str(ttl_path),
        entity_label="keywords",
    )

    logger.info(
        "RDF loading complete: %s keywords, %s triples, %s errors",
        load_stats["keywords_processed"],
        load_stats["triples_added"],
        load_stats["errors"],
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
    logger.info(f"Keywords load report also saved to: {rdf_report_path}")

    return (str(rdf_report_path), normalized_folder)

