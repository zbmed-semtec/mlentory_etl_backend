"""
HuggingFace Elasticsearch Index Loader.

This module defines a basic Elasticsearch DSL `Document` for HF models and
utilities to index normalized FAIR4ML HF models into Elasticsearch.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from elasticsearch_dsl import Document, Keyword, Text, connections

from etl_loaders.elasticsearch_store import (
    ElasticsearchConfig,
    create_elasticsearch_client,
    clean_index,
)
from etl_loaders.load_helpers import LoadHelpers

logger = logging.getLogger(__name__)


class HFModelDocument(Document):
    """Minimal HF model document for search indexing."""

    db_identifier = Keyword()
    name = Text(fields={"raw": Keyword()})
    description = Text()
    shared_by = Keyword()
    license = Keyword()
    ml_tasks = Keyword(multi=True)
    keywords = Keyword(multi=True)
    platform = Keyword()

    class Index:
        # Default name; actual index is set from env via HF_MODELS_INDEX
        name = "hf_models"
        settings = {"number_of_shards": 1, "number_of_replicas": 0}


def _extract_list(value: Any) -> List[str]:
    """Normalize a value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def build_hf_model_document(model: Dict[str, Any], index_name: str) -> HFModelDocument:
    """Create `HFModelDocument` from a normalized FAIR4ML model dict."""
    identifier = model.get("https://schema.org/identifier") or LoadHelpers.mint_subject(model)
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

    doc = HFModelDocument(
        db_identifier=str(identifier),
        name=str(name) if name is not None else "",
        description=str(description) if description is not None else "",
        shared_by=str(shared_by) if shared_by is not None else "Unknown",
        license=str(license_value) if license_value is not None else "Unknown",
        ml_tasks=_extract_list(ml_tasks),
        keywords=_extract_list(keywords),
        platform="Hugging Face",
        meta={"id": str(identifier)},
    )

    # Ensure index name is bound correctly
    doc.meta.index = index_name
    return doc


def index_hf_models(
    json_path: str,
    es_config: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Index normalized HF models into Elasticsearch.

    Args:
        json_path: Path to normalized models JSON (mlmodels.json).
        es_config: Optional ElasticsearchConfig. If None, loads from env.

    Returns:
        Statistics about the indexing operation.
    """
    config = es_config or ElasticsearchConfig.from_env()
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized models file not found for ES indexing: {json_path}")

    logger.info("Loading normalized HF models from %s for Elasticsearch indexing", json_path)
    with open(json_file, "r", encoding="utf-8") as f:
        models = json.load(f)

    if not isinstance(models, list):
        raise ValueError(f"Expected list of models, got {type(models)}")

    logger.info("Loaded %s normalized HF models", len(models))

    # Create client and bind it to elasticsearch-dsl connections
    es_client = create_elasticsearch_client(config)
    connections.add_connection("default", es_client)

    # Ensure index and mapping exist
    logger.info("Ensuring HF models index exists: %s", config.hf_models_index)
    HFModelDocument.init(index=config.hf_models_index, using=es_client)

    indexed = 0
    errors = 0

    for idx, model in enumerate(models):
        try:
            doc = build_hf_model_document(model, config.hf_models_index)
            doc.save(using=es_client, refresh=False)
            indexed += 1
        except Exception as exc:
            errors += 1
            identifier = model.get("https://schema.org/identifier", f"unknown_{idx}")
            logger.error(
                "Error indexing HF model %s into Elasticsearch: %s",
                identifier,
                exc,
                exc_info=True,
            )

        if (idx + 1) % 100 == 0:
            logger.info("Indexed %s/%s HF models into Elasticsearch", idx + 1, len(models))

    logger.info(
        "Completed HF Elasticsearch indexing: %s indexed, %s errors, index=%s",
        indexed,
        errors,
        config.hf_models_index,
    )

    return {
        "models_indexed": indexed,
        "errors": errors,
        "index": config.hf_models_index,
        "input_file": str(json_file),
    }


def clean_hf_models_index(
    es_config: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Clean the Hugging Face models Elasticsearch index.

    This removes all documents from the HF models index configured via
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



