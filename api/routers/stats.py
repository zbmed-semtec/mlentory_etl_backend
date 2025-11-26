"""
Statistics API Router.

Provides aggregated platform-level statistics derived from the indexed models.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, HTTPException

from api.services.elasticsearch_service import elasticsearch_service

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
            - recent_updates: Models updated/created in the last 7 days
    """
    try:
        total_models = _get_total_models()
        categories = _get_category_count()
        integrated_platforms = _get_integrated_platforms()
        recent_updates = _get_recent_updates()

        stats = {
            "total_models": total_models,
            "integrated_platforms": integrated_platforms,
            "categories": categories,
            "recent_updates": recent_updates,
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


def _get_recent_updates() -> int:
    """
    Count models created or updated in the last 7 days.
    """
    try:
        recent_threshold = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        query = {
            "size": 0,
            "query": {
                "range": {
                    "dateCreated": {
                        "gte": recent_threshold,
                    }
                }
            },
        }
        response = elasticsearch_service.client.search(
            index=elasticsearch_service.config.hf_models_index,
            body=query,
        )
        total = response.get("hits", {}).get("total", 0)
        if isinstance(total, dict):
            return int(total.get("value", 0))
        return int(total)
    except Exception as exc:
        logger.warning("Could not determine recent updates: %s", exc)
        return 0

