"""
API Configuration Module.

Reuses ETL loader configurations for consistent database connections.
"""

from __future__ import annotations

import logging
from typing import Optional

from etl_loaders.elasticsearch_store import ElasticsearchConfig, create_elasticsearch_client
from etl_loaders.rdf_store import Neo4jConfig

logger = logging.getLogger(__name__)


class APIConfig:
    """
    Centralized configuration for the API service.
    
    Implements singleton pattern for database configurations and clients.
    All configurations are loaded lazily from environment variables when
    first accessed.
    
    Attributes:
        _es_config: Cached Elasticsearch configuration instance
        _neo4j_config: Cached Neo4j configuration instance
        _es_client: Cached Elasticsearch client instance
    """

    def __init__(self) -> None:
        """
        Initialize API configuration.
        
        Creates empty configuration containers. Actual configurations are
        loaded lazily when properties are accessed.
        """
        self._es_config: Optional[ElasticsearchConfig] = None
        self._neo4j_config: Optional[Neo4jConfig] = None
        self._es_client = None

    @property
    def es_config(self) -> ElasticsearchConfig:
        """
        Get Elasticsearch configuration (lazy-loaded singleton).
        
        Returns:
            ElasticsearchConfig: Configuration loaded from environment variables
        """
        if self._es_config is None:
            self._es_config = ElasticsearchConfig.from_env()
        return self._es_config

    @property
    def neo4j_config(self) -> Neo4jConfig:
        """
        Get Neo4j configuration (lazy-loaded singleton).
        
        Returns:
            Neo4jConfig: Configuration loaded from environment variables
        """
        if self._neo4j_config is None:
            self._neo4j_config = Neo4jConfig.from_env()
        return self._neo4j_config

    @property
    def es_client(self):
        """
        Get Elasticsearch client (lazy-loaded singleton).
        
        Returns:
            Elasticsearch: Connected Elasticsearch client instance
        """
        if self._es_client is None:
            self._es_client = create_elasticsearch_client(self.es_config)
        return self._es_client


# Global configuration instance
api_config = APIConfig()


def get_es_config() -> ElasticsearchConfig:
    """
    Get Elasticsearch configuration from global singleton.
    
    This is a convenience function for dependency injection in FastAPI endpoints.
    
    Returns:
        ElasticsearchConfig: Singleton Elasticsearch configuration instance
    """
    return api_config.es_config


def get_neo4j_config() -> Neo4jConfig:
    """
    Get Neo4j configuration from global singleton.
    
    This is a convenience function for dependency injection in FastAPI endpoints.
    
    Returns:
        Neo4jConfig: Singleton Neo4j configuration instance
    """
    return api_config.neo4j_config


def get_es_client():
    """
    Get Elasticsearch client from global singleton.
    
    This is a convenience function for dependency injection in FastAPI endpoints.
    
    Returns:
        Elasticsearch: Singleton Elasticsearch client instance
    """
    return api_config.es_client
