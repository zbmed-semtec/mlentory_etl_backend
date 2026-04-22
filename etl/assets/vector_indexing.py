"""
Dagster assets for vector embedding backfill into Elasticsearch.

These assets do NOT create separate indices. They add dense-vector fields and
embedding payloads directly onto existing model documents in the source index
(e.g. ``hf_models`` / ``ai4life_models``).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dagster import AssetIn, asset

from etl_loaders.vector_index_manager import run_vector_index_update

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default=%s", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _write_report(report_path: Path, payload: Dict[str, Any]) -> str:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return str(report_path)


@asset(
    group_name="vector_indexing",
    ins={
        "es_ready": AssetIn("hf_elasticsearch_ready"),
        "indexed_report": AssetIn("hf_index_models_elasticsearch"),
    },
    tags={"pipeline": "hf_etl", "stage": "vector_index"},
)
def hf_vector_backfill(
    es_ready: Dict[str, Any],
    indexed_report: str,
) -> str:
    """Backfill vector fields into the HF Elasticsearch models index."""
    index_name = es_ready.get("hf_models_index") or os.getenv("ELASTIC_HF_MODELS_INDEX", "hf_models")
    batch_size = _env_int("VECTOR_INDEX_BATCH_SIZE", 50)
    skip_existing = _env_bool("VECTOR_INDEX_SKIP_EXISTING", True)

    logger.info(
        "Running HF vector backfill: index=%s batch_size=%s skip_existing=%s",
        index_name,
        batch_size,
        skip_existing,
    )

    stats = run_vector_index_update(
        index_name=index_name,
        es_ready=es_ready,
        batch_size=batch_size,
        skip_existing=skip_existing,
        logger_instance=logger,
    )


    report_path: Optional[Path] = None
    try:
        report_path = Path(indexed_report).with_name("vector_index_report.json")
    except Exception:
        report_path = None

    if not report_path:
        report_path = Path("data") / "reports" / "hf" / "vector_index_report.json"

    payload = {
        "source_index_report": indexed_report,
        **stats,
    }
    return _write_report(report_path, payload)


@asset(
    group_name="vector_indexing",
    ins={
        "es_ready": AssetIn("ai4life_elasticsearch_ready"),
        "indexed_report": AssetIn("ai4life_index_models_elasticsearch"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "vector_index"},
)
def ai4life_vector_backfill(
    es_ready: Dict[str, Any],
    indexed_report: str,
) -> str:
    """Backfill vector fields into the AI4Life Elasticsearch models index."""
    index_name = es_ready.get("ai4life_models_index") or os.getenv("ELASTIC_AI4LIFE_MODELS_INDEX", "ai4life_models")
    batch_size = _env_int("VECTOR_INDEX_BATCH_SIZE", 50)
    skip_existing = _env_bool("VECTOR_INDEX_SKIP_EXISTING", True)

    logger.info(
        "Running AI4Life vector backfill: index=%s batch_size=%s skip_existing=%s",
        index_name,
        batch_size,
        skip_existing,
    )

    stats = run_vector_index_update(
        index_name=index_name,
        es_ready=es_ready,
        batch_size=batch_size,
        skip_existing=skip_existing,
        logger_instance=logger,
    )

    report_path: Optional[Path] = None
    try:
        report_path = Path(indexed_report).with_name("vector_index_report.json")
    except Exception:
        report_path = None

    if not report_path:
        report_path = Path("data") / "reports" / "ai4life" / "vector_index_report.json"

    payload = {
        "source_index_report": indexed_report,
        **stats,
    }
    return _write_report(report_path, payload)

