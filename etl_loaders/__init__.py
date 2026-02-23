"""
MLentory ETL Loaders.

This package contains loaders for persisting normalized FAIR4ML data
into Neo4j (as RDF graphs) and Elasticsearch (for search indexing).
"""

__all__ = [
    "rdf_store",
    "rdf_loader",
    "elasticsearch_store",
    "hf_index_loader",
    "openml_index_loader",
]
