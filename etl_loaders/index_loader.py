"""
Elasticsearch index loader utilities for normalized FAIR4ML models.

This module defines a reusable Elasticsearch DSL ``ModelDocument`` and helper
functions for indexing models from multiple sources (e.g., HF, AI4Life).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from elasticsearch_dsl import Date, Document, Keyword, Text, connections

from etl_loaders.elasticsearch_store import (
    ElasticsearchConfig,
    create_elasticsearch_client,
    clean_index,
)
from etl_loaders.load_helpers import LoadHelpers

logger = logging.getLogger(__name__)

IDENTIFIER_PREDICATE = "https://schema.org/identifier"
MLENTORY_GRAPH_PREFIX = "https://w3id.org/mlentory/mlentory_graph/"


class ModelDocument(Document):
    """Minimal model document for search indexing."""

    mlentory_id = Keyword()  # single canonical w3id (mlentory graph URI)
    db_identifier = Keyword(multi=True)  # all alternate IDs: DOI, arXiv, w3id, etc.
    name = Text(fields={"raw": Keyword()})
    description = Text()
    shared_by = Keyword()
    license = Keyword()
    ml_tasks = Keyword(multi=True)
    keywords = Keyword(multi=True)
    datasets = Keyword(multi=True)
    source = Keyword()
    url = Keyword(multi=True)
    readme = Keyword()
    datecreated = Date()
    datemodified = Date()
    inLanguage = Keyword(multi=True)
    domain = Keyword()
    model_category = Keyword(multi=True)
    data_splits = Text()
    adaption_techniques = Keyword()
    parameter_count = Keyword()

    class Index:
        # Default name; actual index is configured by caller/env.
        name = "hf_models"
        settings = {"number_of_shards": 1, "number_of_replicas": 0}


def _extract_list(value: Any) -> List[str]:
    """Normalize a value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _resolve_model_identifiers(model: Dict[str, Any]) -> tuple[str, List[str]]:
    """Split identifiers for Elasticsearch indexing.

    Returns:
        mlentory_id: One canonical w3id graph URI (minted if missing from the model).
        db_identifier: Every value from schema.org/identifier — DOI, arXiv, w3id, etc.
    """
    db_identifier = _extract_list(model.get(IDENTIFIER_PREDICATE))

    mlentory_id = next(
        (iri for iri in db_identifier if iri.startswith(MLENTORY_GRAPH_PREFIX)),
        LoadHelpers.mint_subject(model),
    )
    if not db_identifier:
        db_identifier = [mlentory_id]

    return mlentory_id, db_identifier


def build_model_document(model: Dict[str, Any], index_name: str, translation_mapping: Dict[str, str]) -> ModelDocument:
    """
    Create `ModelDocument` from a normalized FAIR4ML model dict.
    
    Args:
        model: Normalized FAIR4ML model dict.
        index_name: Name of the Elasticsearch index.
        translation_mapping: Dictionary of URIs to human readable names.

    Returns:
        `ModelDocument` object.
    """
    
    mlentory_id, db_identifier = _resolve_model_identifiers(model)
    name = model.get("https://schema.org/name")
    description = model.get("https://schema.org/description")
    shared_by = model.get("https://w3id.org/fair4ml/sharedBy")

    # Prefer FAIR4ML / CodeMeta license, fall back to schema.org if present
    license_value = (
        model.get("https://w3id.org/codemeta/license")
        or model.get("https://schema.org/license")
    )

    ml_tasks = model.get("https://w3id.org/fair4ml/mlTask") or []
    keywords = model.get("https://schema.org/keywords") or []
    source_iri = model.get("https://schema.org/source")
    url = model.get("https://schema.org/url") or []
    readme = model.get("https://w3id.org/codemeta/readme")
    datecreated = model.get("https://schema.org/dateCreated")
    datemodified = model.get("https://schema.org/dateModified")
    in_language = model.get("https://schema.org/inLanguage") or []
    domain = model.get("https://w3id.org/fair4ml/domain")
    model_category = model.get("https://w3id.org/fair4ml/modelCategory") or []
    data_splits = model.get("https://w3id.org/insilico/dataSplits")
    adaption_techniques = model.get("https://w3id.org/insilico/adaptionTechniques")
    parameter_count = model.get("https://w3id.org/fair4ml/parameterCount")

    dataset_fields = [
        "https://w3id.org/fair4ml/trainedOn",
        "https://w3id.org/fair4ml/testedOn",
        "https://w3id.org/fair4ml/validatedOn",
        "https://w3id.org/fair4ml/evaluatedOn",
    ]

    datasets_set = set()
    for field in dataset_fields:
        values = model.get(field)
        if values is None:
            continue
        if isinstance(values, list):
            for v in values:
                if v is not None:
                    datasets_set.add(str(v))
        else:
            if values is not None:
                datasets_set.add(str(values))
    datasets = list(datasets_set)
    
    logger.debug("Resolved model dataset links: %s", datasets)
    
    # Translate entities to human readable names
    datasets = [translation_mapping.get(dataset, dataset) for dataset in datasets]
    ml_tasks = [translation_mapping.get(ml_task, ml_task) for ml_task in ml_tasks]
    keywords = [translation_mapping.get(keyword, keyword) for keyword in keywords]
    license_value = translation_mapping.get(license_value, license_value)
    shared_by = translation_mapping.get(shared_by, shared_by)
    source_name = translation_mapping.get(source_iri, source_iri)
    in_language = [translation_mapping.get(lang, lang) for lang in in_language]
    model_category = [translation_mapping.get(cat, cat) for cat in _extract_list(model_category)]
    source_value = str(source_name) if source_name is not None else "Unknown"
    doc = ModelDocument(
        mlentory_id=mlentory_id,
        db_identifier=db_identifier,
        name=str(name) if name is not None else "",
        description=str(description) if description is not None else "",
        shared_by=str(shared_by) if shared_by is not None else "Unknown",
        license=str(license_value) if license_value is not None else "Unknown",
        ml_tasks=_extract_list(ml_tasks),
        keywords=_extract_list(keywords),
        datasets=_extract_list(datasets),
        source=source_value,
        url=_extract_list(url),
        readme=str(readme) if readme is not None else "",
        datecreated=datecreated,
        datemodified=datemodified,
        inLanguage=_extract_list(in_language),
        domain=str(domain) if domain is not None else None,
        model_category=_extract_list(model_category),
        data_splits=str(data_splits) if data_splits is not None else None,
        adaption_techniques=str(adaption_techniques) if adaption_techniques is not None else None,
        parameter_count=str(parameter_count) if parameter_count is not None else None,
        meta={"id": mlentory_id},
    )

    # Ensure index name is bound correctly
    doc.meta.index = index_name
    return doc


def index_models(
    json_path: str,
    translation_mapping_path: str,
    index_name: str,
    es_config: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Index normalized models into the given Elasticsearch index."""
    config = es_config or ElasticsearchConfig.from_env()
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized models file not found for ES indexing: {json_path}")

    logger.info("Loading normalized models from %s for Elasticsearch indexing", json_path)
    with open(json_file, "r", encoding="utf-8") as f:
        models = json.load(f)

    if not isinstance(models, list):
        raise ValueError(f"Expected list of models, got {type(models)}")

    logger.info("Loaded %s normalized models", len(models))

    logger.info("Loading translation mapping from %s", translation_mapping_path)
    with open(translation_mapping_path, "r", encoding="utf-8") as f:
        translation_mapping = json.load(f)

    if not isinstance(translation_mapping, dict):
        raise ValueError(f"Expected dict of translation mapping, got {type(translation_mapping)}")

    logger.info("Loaded %s translation mapping entries", len(translation_mapping))

    es_client = create_elasticsearch_client(config)
    connections.add_connection("default", es_client)

    logger.info("Ensuring models index exists: %s", index_name)
    ModelDocument.init(index=index_name, using=es_client)

    indexed = 0
    errors = 0

    for idx, model in enumerate(models):
        try:
            doc = build_model_document(model, index_name, translation_mapping)
            doc.save(using=es_client, refresh=False)
            indexed += 1
        except Exception as exc:
            errors += 1
            identifier = model.get("https://schema.org/identifier", f"unknown_{idx}")
            logger.error(
                "Error indexing model %s into Elasticsearch: %s",
                identifier,
                exc,
                exc_info=True,
            )

        if (idx + 1) % 100 == 0:
            logger.info("Indexed %s/%s models into Elasticsearch", idx + 1, len(models))

    logger.info(
        "Completed Elasticsearch indexing: %s indexed, %s errors, index=%s",
        indexed,
        errors,
        index_name,
    )

    return {
        "models_indexed": indexed,
        "errors": errors,
        "index": index_name,
        "input_file": str(json_file),
    }


def index_hf_models(
    json_path: str,
    translation_mapping_path: str,
    es_config: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Index normalized HF models into Elasticsearch."""
    config = es_config or ElasticsearchConfig.from_env()
    return index_models(
        json_path=json_path,
        translation_mapping_path=translation_mapping_path,
        index_name=config.hf_models_index,
        es_config=config,
    )

def _get_names_from_uris(models: List[Dict[str, Any]]) -> Dict[str, str]:
    """ 
    Translate the uris that are find in all the model properties into human readable names. 
    
    Args:
        models: List of normalized models.

    Returns:
        Dict[str, str] Dictionary of URIs to names.
    """
    identified_uris = set()
    
    
    for model in models:
        for prop, value in model.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.startswith("https://w3id.org/mlentory/mlentory_graph/"):
                        identified_uris.add(item)
            elif isinstance(value, str) and value.startswith("https://w3id.org/mlentory/mlentory_graph/"):
                identified_uris.add(value)
    
    identified_uris_list = list(identified_uris)
    
    
    
    

def clean_hf_models_index(
    es_config: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Clean the configured models Elasticsearch index.

    This removes all documents from the models index configured via
    ``ELASTIC_HF_MODELS_INDEX`` while keeping the index and its mappings.
    """
    config = es_config or ElasticsearchConfig.from_env()
    return clean_index(config.hf_models_index, cfg=config)


def check_elasticsearch_connection(
    es_config: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Check Elasticsearch connection and cluster health.

    Args:
        es_config: Optional ElasticsearchConfig. If None, loads from env.

    Returns:
        Dictionary with connection status and cluster info.

    Raises:
        ConnectionError: If Elasticsearch is not reachable.
    """
    config = es_config or ElasticsearchConfig.from_env()
    es_client = create_elasticsearch_client(config)

    try:
        # Ping the cluster
        if not es_client.ping():
            raise ConnectionError(
                f"Cannot ping Elasticsearch at {config.scheme}://{config.host}:{config.port}"
            )

        # Get cluster health
        health = es_client.cluster.health()
        cluster_name = health.get("cluster_name", "unknown")
        status = health.get("status", "unknown")
        num_nodes = health.get("number_of_nodes", 0)

        logger.info(
            "Elasticsearch connection verified: cluster=%s, status=%s, nodes=%s",
            cluster_name,
            status,
            num_nodes,
        )

        return {
            "status": "ready",
            "cluster_name": cluster_name,
            "cluster_status": status,
            "number_of_nodes": num_nodes,
            "host": config.host,
            "port": config.port,
            "scheme": config.scheme,
            "hf_models_index": config.hf_models_index,
        }

    except Exception as exc:
        logger.error(
            "Failed to connect to Elasticsearch at %s://%s:%s: %s",
            config.scheme,
            config.host,
            config.port,
            exc,
            exc_info=True,
        )
        raise ConnectionError(
            f"Elasticsearch connection failed: {exc}"
        ) from exc



