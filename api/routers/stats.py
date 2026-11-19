"""
Statistics API Router.

Provides aggregated platform-level statistics derived from the indexed models.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException

from api.config import get_neo4j_config
from api.services.elasticsearch_service import elasticsearch_service
from etl_loaders.rdf_store import _run_cypher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stats", tags=["statistics"])


@router.get("/platform")
async def get_platform_stats() -> dict:
    """
    Retrieve high-level statistics about the MLentory platform.

    Returns:
        Dict with keys:
            - total_models: Total number of indexed models
            - integrated_platforms: Number of active platform indexes
            - categories: Number of unique ML task categories
            - last_updated: Newest date a platform load saved a model field
    """
    try:
        total_models = _get_total_models()
        categories = _get_category_count()
        integrated_platforms = _get_integrated_platforms()
        last_updated = _get_last_updated()

        stats = {
            "total_models": total_models,
            "integrated_platforms": integrated_platforms,
            "categories": categories,
            "last_updated": last_updated,
        }

        logger.info("Platform statistics retrieved successfully: %s", stats)
        return stats

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Unexpected error getting platform statistics: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error while getting platform statistics: {str(exc)}",
        )


def _get_total_models() -> int:
    """Use the faceted search helper to retrieve the total model count."""
    try:
        _models, total_count, _ = elasticsearch_service.search_models_with_facets(
            query="",
            filters={},
            page=1,
            page_size=1,
            facets=["mlTask"],
            facet_size=1,
            facet_query={},
        )
        return int(total_count)
    except Exception as exc:
        logger.warning("Could not determine total models: %s", exc)
        return 0


def _get_category_count() -> int:
    """
    Count unique ML tasks by inspecting the mlTask facet.

    Returns:
        Number of ML task categories (best-effort).
    """
    try:
        values, _after_key, _has_more = elasticsearch_service.fetch_facet_values(
            field="mlTask",
            search_query="",
            after_key="",
            limit=500,
            current_filters={},
        )
        return len(values)
    except Exception as exc:
        logger.warning("Could not determine category count: %s", exc)
        # Fallback to a conservative default
        return 0


def _get_integrated_platforms() -> int:
    """
    Estimate the number of integrated platforms by counting *_models indexes.
    """
    try:
        indices_info = elasticsearch_service.client.cat.indices(format="json")
        index_names: List[str] = [entry.get("index", "") for entry in indices_info]
        model_indexes = [
            name
            for name in index_names
            if name.endswith("_models")
            and not name.endswith("vector_models")
            and not name.startswith("vector_")
        ]
        if model_indexes:
            return len(model_indexes)
        return 1  # At least one platform is active
    except Exception as exc:
        logger.warning("Could not determine integrated platforms: %s", exc)
        return 1


def _get_last_updated() -> Optional[str]:
    """Newest time a model field was saved, across every platform."""
    try:
        rows = _run_cypher(
            """
            MATCH ()-[r:HAS_PROPERTY_SNAPSHOT]->()
            WHERE r.valid_from IS NOT NULL
            RETURN max(r.valid_from) AS last_updated
            """,
            {},
            cfg=get_neo4j_config(),
        )
        if not rows or rows[0].get("last_updated") is None:
            return None
        return _format_last_updated(rows[0]["last_updated"])
    except Exception as exc:
        logger.warning("Could not determine last updated: %s", exc)
        return None


def _format_last_updated(value: object) -> str:
    """Format a Neo4j datetime as '23 Oct 2026'."""
    if hasattr(value, "to_native"):
        when = value.to_native()
    else:
        text = str(value).replace("Z", "+00:00")
        if "." in text:
            head, tail = text.split(".", 1)
            fraction = "".join(ch for ch in tail if ch.isdigit())[:6]
            tz = tail[len("".join(ch for ch in tail if ch.isdigit())) :]
            text = f"{head}.{fraction}{tz}" if fraction else f"{head}{tz}"
        when = datetime.fromisoformat(text)
    return f"{when.day} {when.strftime('%b %Y')}"

