"""
Elasticsearch Store Configuration and helpers.

This module centralizes configuration and client creation for Elasticsearch
so that loaders can depend on a single, well-typed interface.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)


@dataclass
class ElasticsearchConfig:
    """Configuration for Elasticsearch connection."""

    host: str
    port: int
    scheme: str
    username: Optional[str]
    password: Optional[str]
    hf_models_index: str

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

        logger.info(
            "Loaded Elasticsearch config from env: host=%s, port=%s, scheme=%s, "
            "username=%s, password=%s, hf_models_index=%s",
            host,
            port_raw,
            scheme,
            username,
            password,
            hf_models_index,
        )

        try:
            port = int(port_raw)
        except ValueError:
            raise ValueError(f"Invalid ES_PORT value: {port_raw!r}")

        logger.info(
            "Loaded Elasticsearch config from env: host=%s, port=%s, scheme=%s, "
            "hf_models_index=%s",
            host,
            port,
            scheme,
            hf_models_index,
        )

        return cls(
            host=host,
            port=port,
            scheme=scheme,
            username=username,
            password=password,
            hf_models_index=hf_models_index,
        )


def create_elasticsearch_client(cfg: Optional[ElasticsearchConfig] = None) -> Elasticsearch:
    """Create an Elasticsearch client from configuration.

    Args:
        cfg: Optional ElasticsearchConfig. If None, loads from env.

    Returns:
        Configured Elasticsearch client instance.
    """
    config = cfg or ElasticsearchConfig.from_env()

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
        "Created Elasticsearch client for %s://%s:%s",
        config.scheme,
        config.host,
        config.port,
    )
    return es



