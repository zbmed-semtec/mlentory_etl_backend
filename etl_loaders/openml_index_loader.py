"""
OpenML Elasticsearch Index Loader.

Indexes OpenML normalized models into Elasticsearch using the shared
platform-agnostic FAIR4ML representation.
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
from etl_loaders.hf_index_loader import check_elasticsearch_connection  # reuse health check

logger = logging.getLogger(__name__)


class OpenMLModelDocument(Document):
    """Minimal OpenML model document for search indexing."""

    db_identifier = Keyword(multi=True)
    name = Text(fields={"raw": Keyword()})
    description = Text()
    shared_by = Keyword()
    license = Keyword()
    ml_tasks = Keyword(multi=True)
    keywords = Keyword(multi=True)
    datasets = Keyword(multi=True)
    platform = Keyword()

    class Index:
        # Default name; actual index is set from env via ELASTIC_OPENML_MODELS_INDEX
        name = "openml_models"
        settings = {"number_of_shards": 1, "number_of_replicas": 0}


def _extract_list(value: Any) -> List[str]:
    """Normalize a value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def build_openml_model_document(
    model: Dict[str, Any], index_name: str, translation_mapping: Dict[str, str]
) -> OpenMLModelDocument:
    """
    Create `OpenMLModelDocument` from a normalized FAIR4ML model dict.

    Args:
        model: Normalized FAIR4ML model dict.
        index_name: Name of the Elasticsearch index.
        translation_mapping: Dictionary of URIs to human readable names.

    Returns:
        `OpenMLModelDocument` object.
    """

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

    # Translate entities to human readable names
    datasets = [translation_mapping.get(dataset, dataset) for dataset in datasets]
    ml_tasks = [translation_mapping.get(ml_task, ml_task) for ml_task in ml_tasks]
    keywords = [translation_mapping.get(keyword, keyword) for keyword in keywords]
    license_value = translation_mapping.get(license_value, license_value)

    doc = OpenMLModelDocument(
        db_identifier=[str(id) for id in identifier],
        name=str(name) if name is not None else "",
        description=str(description) if description is not None else "",
        shared_by=str(shared_by) if shared_by is not None else "Unknown",
        license=str(license_value) if license_value is not None else "Unknown",
        ml_tasks=_extract_list(ml_tasks),
        keywords=_extract_list(keywords),
        datasets=_extract_list(datasets),
        platform="OpenML",
        meta={"id": [str(id) for id in identifier]},
    )

    # Ensure index name is bound correctly
    doc.meta.index = index_name
    return doc


def index_openml_models(
    json_path: str,
    translation_mapping_path: str,
    es_config: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Index normalized OpenML models into Elasticsearch.

    Args:
        json_path: Path to normalized models JSON (mlmodels.json).
        translation_mapping_path: Path to translation mapping JSON file. Maps URIs to human readable names.
        es_config: Optional ElasticsearchConfig. If None, loads from env.

    Returns:
        Statistics about the indexing operation.
    """
    config = es_config or ElasticsearchConfig.from_env()
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized models file not found for ES indexing: {json_path}")

    logger.info("Loading normalized OpenML models from %s for Elasticsearch indexing", json_path)
    with open(json_file, "r", encoding="utf-8") as f:
        models = json.load(f)

    if not isinstance(models, list):
        raise ValueError(f"Expected list of models, got {type(models)}")

    logger.info("Loaded %s normalized OpenML models", len(models))

    logger.info("Loading translation mapping from %s", translation_mapping_path)
    with open(translation_mapping_path, "r", encoding="utf-8") as f:
        translation_mapping = json.load(f)

    if not isinstance(translation_mapping, dict):
        raise ValueError(f"Expected dict of translation mapping, got {type(translation_mapping)}")

    logger.info("Loaded %s translation mapping entries", len(translation_mapping))

    # Create client and bind it to elasticsearch-dsl connections
    es_client = create_elasticsearch_client(config)
    connections.add_connection("default", es_client)

    # Ensure index and mapping exist
    logger.info("Ensuring OpenML models index exists: %s", config.openml_models_index)
    OpenMLModelDocument.init(index=config.openml_models_index, using=es_client)

    indexed = 0
    errors = 0

    for idx, model in enumerate(models):
        try:
            doc = build_openml_model_document(model, config.openml_models_index, translation_mapping)
            doc.save(using=es_client, refresh=False)
            indexed += 1
        except Exception as exc:
            errors += 1
            identifier = model.get("https://schema.org/identifier", f"unknown_{idx}")
            logger.error(
                "Error indexing OpenML model %s into Elasticsearch: %s",
                identifier,
                exc,
                exc_info=True,
            )

        if (idx + 1) % 100 == 0:
            logger.info("Indexed %s/%s OpenML models into Elasticsearch", idx + 1, len(models))

    logger.info(
        "Completed OpenML Elasticsearch indexing: %s indexed, %s errors, index=%s",
        indexed,
        errors,
        config.openml_models_index,
    )

    return {
        "models_indexed": indexed,
        "errors": errors,
        "index": config.openml_models_index,
        "input_file": str(json_file),
    }


def clean_openml_models_index(
    es_config: Optional[ElasticsearchConfig] = None,
) -> Dict[str, Any]:
    """Clean the OpenML models Elasticsearch index."""
    config = es_config or ElasticsearchConfig.from_env()
    return clean_index(config.openml_models_index, cfg=config)


__all__ = [
    "OpenMLModelDocument",
    "build_openml_model_document",
    "index_openml_models",
    "clean_openml_models_index",
    "check_elasticsearch_connection",
]

