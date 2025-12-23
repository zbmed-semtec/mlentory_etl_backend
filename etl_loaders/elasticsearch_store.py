"""
Elasticsearch Store Configuration and helpers.

This module centralizes configuration and client creation for Elasticsearch
so that loaders can depend on a single, well-typed interface.
"""

from __future__ import annotations

import logging
import os
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

_ES_CLIENT_CACHE: Dict[str, Elasticsearch] = {}


@dataclass
class ElasticsearchConfig:
    """Configuration for Elasticsearch connection."""

    host: str
    port: int
    scheme: str
    username: Optional[str]
    password: Optional[str]
    hf_models_index: str
    openml_models_index: str

    @classmethod
    def from_env(cls) -> "ElasticsearchConfig":
        """Load Elasticsearch configuration from environment variables.

        Env vars:
            ES_HOST: Elasticsearch host (default: "localhost")
            ES_PORT: Elasticsearch port (default: 9200)
            ES_SCHEME: Connection scheme (default: "http")
            ES_USERNAME: Optional basic auth username
            ES_PASSWORD: Optional basic auth password
            HF_MODELS_INDEX: Index name for HF models (default: "hf_models")

        Returns:
            ElasticsearchConfig instance.
        """
        host = os.getenv("ELASTIC_HOST", "mlentory-elasticsearch")
        port_raw = os.getenv("ELASTIC_PORT", "9201")
        scheme = os.getenv("ELASTIC_SCHEME", "http")
        username = os.getenv("ELASTIC_USER", "elastic")
        password = os.getenv("ELASTIC_PASSWORD", "changeme")
        hf_models_index = os.getenv("ELASTIC_HF_MODELS_INDEX", "hf_models")
        openml_models_index = os.getenv("ELASTIC_OPENML_MODELS_INDEX", "openml_models")

        logger.info(
            "Loaded Elasticsearch config from env: host=%s, port=%s, scheme=%s, "
            "username=%s, password=%s, hf_models_index=%s, openml_models_index=%s",
            host,
            port_raw,
            scheme,
            username,
            password,
            hf_models_index,
            openml_models_index,
        )

        try:
            port = int(port_raw)
        except ValueError:
            raise ValueError(f"Invalid ES_PORT value: {port_raw!r}")

        logger.info(
            "Loaded Elasticsearch config from env: host=%s, port=%s, scheme=%s, "
            "hf_models_index=%s, openml_models_index=%s",
            host,
            port,
            scheme,
            hf_models_index,
            openml_models_index,
        )

        return cls(
            host=host,
            port=port,
            scheme=scheme,
            username=username,
            password=password,
            hf_models_index=hf_models_index,
            openml_models_index=openml_models_index,
        )


def _config_cache_key(config: ElasticsearchConfig) -> str:
    """Create a stable cache key for a given Elasticsearch config."""
    materialized = "|".join(
        [
            config.scheme,
            config.host,
            str(config.port),
            config.username or "",
            config.password or "",
            config.hf_models_index,
            config.openml_models_index,
        ]
    )
    return hashlib.sha256(materialized.encode("utf-8")).hexdigest()


def create_elasticsearch_client(cfg: Optional[ElasticsearchConfig] = None) -> Elasticsearch:
    """Create an Elasticsearch client from configuration.

    Args:
        cfg: Optional ElasticsearchConfig. If None, loads from env.

    Returns:
        Configured Elasticsearch client instance.
    """
    config = cfg or ElasticsearchConfig.from_env()
    cache_key = _config_cache_key(config)

    if cache_key in _ES_CLIENT_CACHE:
        logger.debug("Reusing cached Elasticsearch client (key=%s)", cache_key[:8])
        return _ES_CLIENT_CACHE[cache_key]

    es = Elasticsearch(
        [
            {
                "host": config.host,
                "port": config.port,
                "scheme": config.scheme,
            }
        ],
        basic_auth=(config.username, config.password),
    )

    logger.info(
        "Created Elasticsearch client for %s://%s:%s (key=%s)",
        config.scheme,
        config.host,
        config.port,
        cache_key[:8],
    )
    _ES_CLIENT_CACHE[cache_key] = es
    return es


def search(cfg: Optional[ElasticsearchConfig], index_name: str, query: dict) -> List[dict]:
    try:
        es_client = create_elasticsearch_client(cfg)
        result = es_client.search(index=index_name, body=query)
        return result["hits"]["hits"]
    except Exception as e:
        print(f"Error searching index: {str(e)}")
        return []

def clean_index(
    index_name: str,
    cfg: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Remove all documents from an Elasticsearch index.

    This keeps the index and its mappings/settings but deletes all
    documents via a ``delete_by_query`` on ``match_all``.

    Args:
        index_name: Name of the index to clean.
        cfg: Optional ElasticsearchConfig. If None, loads from env.

    Returns:
        A dictionary with basic statistics about the clean operation.
    """
    config = cfg or ElasticsearchConfig.from_env()
    es = create_elasticsearch_client(config)

    if not es.indices.exists(index=index_name):
        logger.warning("Elasticsearch index %s does not exist; nothing to clean", index_name)
        return {
            "index": index_name,
            "deleted": 0,
            "result": "index_not_found",
        }

    logger.info("Cleaning Elasticsearch index: %s", index_name)
    response = es.delete_by_query(
        index=index_name,
        body={"query": {"match_all": {}}},
        refresh=True,
        conflicts="proceed",
    )

    deleted = int(response.get("deleted", 0))
    logger.info("Cleaned Elasticsearch index %s; deleted %s documents", index_name, deleted)

    return {
        "index": index_name,
        "deleted": deleted,
        "result": "ok",
    }

