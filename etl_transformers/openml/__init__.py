"""
OpenML transformation helpers.

This package contains pure transformation functions for mapping OpenML entities
to FAIR4ML-compatible schemas. Dagster assets import these helpers so logic is
shared and testable, mirroring the Hugging Face transformer layout.
"""

from .transform_mlmodel import (
    hash_uri,
    make_identifier,
    split_keywords,
    collect_keyword_map,
    normalize_dataset_record,
    normalize_task_record,
    build_keyword_terms,
    normalize_runs,
    build_entity_links,
    normalize_models,
    map_basic_properties,
)

__all__ = [
    "hash_uri",
    "make_identifier",
    "split_keywords",
    "collect_keyword_map",
    "normalize_dataset_record",
    "normalize_task_record",
    "build_keyword_terms",
    "normalize_runs",
    "build_entity_links",
    "normalize_models",
    "map_basic_properties",
]

