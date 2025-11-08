"""
RDF Store Configuration for Neo4j.

Provides utilities for configuring and opening RDFLib Graph instances
backed by Neo4j using rdflib-neo4j integration.

Based on Neo4j's RDFLib integration guide:
https://neo4j.com/blog/developer/rdflib-neo4j-rdf-integration-neo4j/
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Any, Dict, List, Union
from urllib.parse import urlparse

import requests

from rdflib import Graph, Namespace
from rdflib_neo4j import Neo4jStoreConfig, Neo4jStore, HANDLE_VOCAB_URI_STRATEGY
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


# Standard namespace prefixes
namespaces = {
    "schema": Namespace("https://schema.org/"),
    "fair4ml": Namespace("https://w3id.org/fair4ml/"),
    "codemeta": Namespace("https://w3id.org/codemeta/"),
    "mlentory": Namespace("https://w3id.org/mlentory/"),
    "cr": Namespace("https://w3id.org/cr/"),
    "rdf": Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    "rdfs": Namespace("http://www.w3.org/2000/01/rdf-schema#"),
    "xsd": Namespace("http://www.w3.org/2001/XMLSchema#"),
}



@dataclass
class Neo4jConfig:
    """Configuration for Neo4j connection."""
    
    uri: str
    user: str
    password: str
    database: str
    
    @classmethod
    def from_env(cls) -> "Neo4jConfig":
        """
        Load Neo4j configuration from environment variables.
        
        Required env vars:
        - NEO4J_URI: Neo4j connection URI (e.g., bolt://localhost:7687)
        - NEO4J_USER: Neo4j username
        - NEO4J_PASSWORD: Neo4j password
        - NEO4J_DATABASE: Neo4j database name (default: neo4j)
        
        Returns:
            Neo4jConfig instance
            
        Raises:
            ValueError: If required env vars are missing
        """
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        password = os.getenv("NEO4J_PASSWORD")
        database = os.getenv("NEO4J_DATABASE", "neo4j")
        
        if not uri:
            raise ValueError("NEO4J_URI environment variable is required")
        if not user:
            raise ValueError("NEO4J_USER environment variable is required")
        if not password:
            raise ValueError("NEO4J_PASSWORD environment variable is required")
        
        logger.info(f"Loaded Neo4j config from env: uri={uri}, database={database}")
        return cls(uri=uri, user=user, password=password, database=database)


def get_neo4j_store_config_from_env(
    batching: bool = True,
    batch_size: int = 5000,
    multithreading: bool = True,
    max_workers: int = 4,
) -> Neo4jStoreConfig:
    """
    Create Neo4jStoreConfig from environment variables.
    
    Args:
        batching: Enable batching for better performance (default: True)
        batch_size: Number of triples per batch (default: 5000)
        multithreading: Enable multithreading for imports (default: True)
        max_workers: Number of worker threads (default: 4)
        
    Returns:
        Neo4jStoreConfig configured with env vars
        
    Raises:
        ValueError: If required env vars are missing
    """
    env_cfg = Neo4jConfig.from_env()
    
    # rdflib-neo4j expects an auth_data dict with specific keys
    auth_data = {
        "uri": env_cfg.uri,
        "database": env_cfg.database,
        "user": env_cfg.user,
        "pwd": env_cfg.password,
    }
    
    store_config = Neo4jStoreConfig(auth_data=auth_data)
    
    # Best-effort: set performance options if supported by this version
    for name, value in (
        ("batching", batching),
        ("batch_size", batch_size),
        ("multithreading", multithreading),
        ("max_workers", max_workers),
    ):
        try:
            if hasattr(store_config, name):
                setattr(store_config, name, value)
        except Exception:
            # Ignore if the attribute is not settable in this version
            pass
    
    # Provide rdflib-neo4j namespace mappings for SHORTEN handling
    store_config.custom_prefixes = namespaces
    store_config.handle_vocab_uri_strategy = HANDLE_VOCAB_URI_STRATEGY.SHORTEN
    
    logger.info(
        f"Created Neo4jStoreConfig for {env_cfg.uri}/{env_cfg.database} "
        f"(batching={batching}, batch_size={batch_size}, multithreading={multithreading}, max_workers={max_workers})"
    )
    
    return store_config


def open_graph(
    config: Optional[Neo4jStoreConfig] = None,
    bind_prefixes: bool = True,
) -> Graph:
    """
    Open an RDFLib Graph backed by Neo4j.
    
    The graph must be explicitly closed with `graph.close(True)` to flush commits.
    
    Args:
        config: Neo4jStoreConfig instance. If None, loads from env
        bind_prefixes: Bind standard namespace prefixes (default: True)
        
    Returns:
        RDFLib Graph instance backed by Neo4jStore
        
    Example:
        >>> config = get_neo4j_store_config_from_env()
        >>> g = open_graph(config)
        >>> # ... add triples ...
        >>> g.close(True)  # Flush commits
    """
    if config is None:
        config = get_neo4j_store_config_from_env()
    
    # Create graph with Neo4j store
    store = Neo4jStore(config=config)
    graph = Graph(store=store)
    
    # Bind standard prefixes
    if bind_prefixes:
        for prefix, namespace in namespaces.items():
            add_prefix(prefix, namespace)
            graph.bind(prefix, namespace)
        logger.info(f"Bound namespace prefixes: {', '.join(namespaces.keys())}")
    
    logger.info("Opened RDFLib Graph with Neo4jStore backend")
    return graph


def create_graph_context(
    config: Optional[Neo4jStoreConfig] = None,
    bind_prefixes: bool = True,
):
    """
    Context manager for safely opening and closing an RDF graph.
    
    Args:
        config: Neo4jStoreConfig instance. If None, loads from env
        bind_prefixes: Bind standard namespace prefixes (default: True)
        
    Yields:
        RDFLib Graph instance backed by Neo4jStore
        
    Example:
        >>> with create_graph_context() as g:
        ...     g.add((subject, predicate, object))
        ...     # Graph is automatically closed on exit
    """
    graph = open_graph(config=config, bind_prefixes=bind_prefixes)
    try:
        yield graph
    finally:
        logger.info("Closing graph and flushing commits...")
        graph.close(True)
        logger.info("Graph closed successfully")


# ============================
# n10s (neosemantics) helpers
# ============================

def _get_driver(cfg: Optional[Neo4jConfig] = None):
    env_cfg = cfg or Neo4jConfig.from_env()
    driver = GraphDatabase.driver(env_cfg.uri, auth=(env_cfg.user, env_cfg.password))
    return driver, env_cfg.database


def _run_cypher(query: str, params: Optional[Dict[str, Any]] = None, cfg: Optional[Neo4jConfig] = None) -> List[Dict[str, Any]]:
    driver, database = _get_driver(cfg)
    with driver.session(database=database) as session:
        result = session.run(query, params or {})
        records = [r.data() for r in result]
    driver.close()
    return records


def init_neosemantics(config: Optional[Dict[str, Any]] = None, cfg: Optional[Neo4jConfig] = None) -> Dict[str, Any]:
    """
    Initialize or override n10s graph configuration.

    If config is None, uses CALL n10s.graphconfig.init().
    Else passes a map to init(map).
    Also ensures the canonical uniqueness constraint used by n10s.
    """
    # Ensure uniqueness constraint exists (Neo4j 5.x syntax)
    _run_cypher(
        """
        CREATE CONSTRAINT n10s_unique_uri IF NOT EXISTS
        FOR (r:Resource) REQUIRE r.uri IS UNIQUE
        """,
        cfg=cfg,
    )

    if config:
        data = _run_cypher("CALL n10s.graphconfig.init($cfg)", {"cfg": config}, cfg=cfg)
    else:
        data = _run_cypher("CALL n10s.graphconfig.init()", cfg=cfg)
    return {"ok": True, "result": data}


def get_neosemantics_config(cfg: Optional[Neo4jConfig] = None) -> Dict[str, Any]:
    """Return current n10s graph configuration (empty dict if none)."""
    try:
        data = _run_cypher("CALL n10s.graphconfig.show", cfg=cfg)
        return data[0] if data else {}
    except Exception as e:
        logger.warning(f"Could not read n10s config: {e}")
        return {}


def reset_database(drop_config: bool = True, cfg: Optional[Neo4jConfig] = None) -> None:
    """
    Reset the database contents to allow reconfiguring n10s.

    This removes all nodes and relationships. Optionally drops n10s config.
    Use with caution in non-production environments.
    """
    logger.warning("Resetting Neo4j database: deleting all nodes and relationships...")
    _run_cypher("MATCH (n) DETACH DELETE n", cfg=cfg)
    if drop_config:
        try:
            _run_cypher("CALL n10s.graphconfig.drop()", cfg=cfg)
        except Exception as e:
            logger.info(f"n10s graphconfig.drop not executed or failed: {e}")


def add_prefix(prefix: str, namespace: str, cfg: Optional[Neo4jConfig] = None) -> Dict[str, str]:
    """
    Add a single namespace prefix mapping to neosemantics.
    """
    if not prefix or not prefix.strip():
        raise ValueError("Prefix cannot be empty")
    if not namespace or not namespace.strip():
        raise ValueError("Namespace cannot be empty")

    results = _run_cypher(
        "CALL n10s.nsprefixes.add($prefix, $namespace)",
        {"prefix": prefix.strip(), "namespace": namespace.strip()},
        cfg=cfg,
    )

    if results:
        result = {
            "prefix": results[0].get("prefix", prefix.strip()),
            "namespace": results[0].get("namespace", namespace.strip()),
        }
        logger.info(f"Added namespace prefix: {result['prefix']} -> {result['namespace']}")
        return result
    raise RuntimeError("Failed to add prefix - no result returned")


def ensure_default_prefixes(cfg: Optional[Neo4jConfig] = None) -> None:
    """Ensure core prefixes exist in n10s prefix store."""
    for prefix, namespace in namespaces.items():
        try:
            add_prefix(prefix, namespace, cfg=cfg)
        except Exception as e:
            # Ignore if already exists; log others
            msg = str(e).lower()
            if "already" in msg or "exists" in msg:
                logger.debug(f"Prefix already exists: {prefix} -> {namespace}")
            else:
                logger.warning(f"Could not add prefix {prefix}: {e}")


# ============================
# n10s (neosemantics) HTTP export
# ============================

def _build_http_base_url(cfg: Optional[Neo4jConfig] = None) -> str:
    """Construct the Neo4j HTTP base URL from environment/config.

    Falls back to http://<host>:<port> using host from NEO4J_URI and port from
    NEO4J_HTTP_PORT (default 7474). You can override the scheme with NEO4J_HTTP_SCHEME.
    """
    env_cfg = cfg or Neo4jConfig.from_env()
    parsed = urlparse(env_cfg.uri)
    host = parsed.hostname or "localhost"
    # Prefer explicit env overrides if provided
    scheme = os.getenv("NEO4J_HTTP_SCHEME", "http")
    port_env = os.getenv("NEO4J_HTTP_PORT")
    try:
        port = int(port_env) if port_env else 7474
    except ValueError:
        port = 7474
    return f"{scheme}://{host}:{port}"


def export_graph_neosemantics(
    file_path: Optional[str] = None,
    format: str = "Turtle",
    cypher_query: Optional[str] = None,
    cfg: Optional[Neo4jConfig] = None,
) -> Union[str, Dict[str, Any]]:
    """
    Export the graph via Neosemantics HTTP endpoint `/rdf/<db>/cypher`.

    Returns RDF string if `file_path` is None, otherwise writes to file and returns
    a small stats dict.
    """
    env_cfg = cfg or Neo4jConfig.from_env()
    if cypher_query is None:
        cypher_query = "MATCH (n)-[r]->(m) RETURN n, r, m"

    base_url = _build_http_base_url(env_cfg)
    endpoint = f"{base_url}/rdf/{env_cfg.database}/cypher"

    payload = {"cypher": cypher_query, "format": format}

    try:
        response = requests.post(
            endpoint,
            json=payload,
            auth=(env_cfg.user, env_cfg.password),
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Neosemantics endpoint returned {response.status_code}: {response.text}"
            )

        rdf_content = response.text
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(rdf_content)
            logger.info(
                f"Exported graph to {file_path} using Neosemantics (format: {format})"
            )
            return {
                "file_path": file_path,
                "format": format,
                "endpoint": endpoint,
                "success": True,
            }
        else:
            return rdf_content
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to connect to Neosemantics endpoint: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to export graph using Neosemantics: {e}")

