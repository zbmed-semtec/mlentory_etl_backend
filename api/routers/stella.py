"""
STELLA evaluation integration.

Proxies faceted search through the STELLA App and forwards ranking feedback.
STELLA system containers should call this API's faceted search at ``/api/v1/models/search``
(use ``limit`` as the ``page_size`` query parameter, or adapt the ranker URL accordingly).
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Body, HTTPException, Query

from api.schemas.responses import FacetedSearchResponse
from api.services.elasticsearch_service import elasticsearch_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _keyword_results(
    query: str,
    filter_dict: Dict[str, Any],
    page: int,
    limit: int,
    facets_list: list,
    facet_size: int,
    facet_query_dict: Dict[str, Any],
) -> FacetedSearchResponse:
    """Keyword ranking used when STELLA drops or fails to return the hits."""
    models, total_count, facet_results = elasticsearch_service.search_models_with_improved_keyword(
        query=query,
        filters=filter_dict,
        page=page,
        page_size=limit,
        facets=facets_list,
        facet_size=facet_size,
        facet_query=facet_query_dict,
    )
    all_facet_config = elasticsearch_service.get_facets_config()
    return FacetedSearchResponse(
        models=models,
        total=total_count,
        page=page,
        page_size=limit,
        filters=filter_dict,
        facets=facet_results,
        facet_config={key: value for key, value in all_facet_config.items() if key in facets_list},
    )


@router.get("/stella/search_with_stella")
async def search_models_with_stella(
    query: str = Query("", description="Optional text search query"),
    filters: str = Query("{}", description="JSON string of property filters"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of results per page"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    extended: bool = Query(False, description="Passed through to ranker systems"),
    facets: str = Query(
        '["mlTask", "license", "keywords"]',
        description="JSON array of facet field names",
    ),
    facet_size: int = Query(20, ge=1, le=100, description="Maximum number of values per facet"),
    facet_query: str = Query("{}", description="JSON object for searching within facets"),
    base_url: Optional[str] = Query(
        None,
        description=(
            "Host/path for STELLA proxy (e.g. 'mlentory-api:8000/api/v1/models'). "
            "Default: BACKEND_BASE_URL env."
        ),
    ),
    session_id: Optional[str] = Query(None, description="Optional STELLA session id (stella-sid)"),
) -> Any:
    """
    Forward faceted search to the STELLA App proxy for interleaved A/B ranking.

    STELLA forwards the same query parameters to your ranker containers; those containers
    should invoke ``GET .../api/v1/models/search`` (this API), mapping ``limit`` ↔ ``page_size``.
    """
    if os.environ.get("USE_STELLA", "true").lower() != "true":
        raise HTTPException(status_code=503, detail="STELLA integration is disabled")

    try:
        filter_dict = json.loads(filters) if filters else {}
        facets_list = json.loads(facets) if facets else ["mlTask", "license", "keywords"]
        facet_query_dict = json.loads(facet_query) if facet_query else {}
    except json.JSONDecodeError as je:
        raise HTTPException(status_code=400, detail=f"Invalid JSON format: {str(je)}")

    stella_proxy_base = os.getenv("STELLA_PROXY_API", "http://stella-app:8005/proxy").rstrip("/")
    default_base = os.getenv("BACKEND_BASE_URL", "mlentory-api:8000/api/v1/models")
    backend_base = (base_url or default_base).strip().strip("/")
    stella_proxy_url = f"{stella_proxy_base}/{backend_base}"

    stella_params: Dict[str, Any] = {
        "query": query,
        "filters": json.dumps(filter_dict),
        "extended": extended,
        "limit": limit,
        # Keyword ranker reads page_size; vector ranker reads limit.
        "page_size": limit,
        "page": page,
        "facets": json.dumps(facets_list),
        "facet_size": facet_size,
        "facet_query": json.dumps(facet_query_dict),
        # STELLA interleaves with rpp = min(baseline hits, experiment hits)
        # when this is omitted. A ranker with zero hits then replaces the
        # other ranker's models with an empty list while leaving total intact.
        "stella-rpp": limit,
    }
    if session_id:
        stella_params["stella-sid"] = session_id
    if page:
        stella_params["stella-page"] = page

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(stella_proxy_url, params=stella_params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.warning("STELLA proxy failed (%s); returning keyword results", e)
        return _keyword_results(
            query, filter_dict, page, limit, facets_list, facet_size, facet_query_dict
        )
    except Exception as e:
        logger.error("search_with_stella failed: %s", e, exc_info=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")

    models = payload.get("models") if isinstance(payload, dict) else None
    total = payload.get("total") if isinstance(payload, dict) else 0
    if isinstance(payload, dict) and not models and total:
        logger.warning(
            "STELLA returned total=%s with no models; returning keyword results", total
        )
        return _keyword_results(
            query, filter_dict, page, limit, facets_list, facet_size, facet_query_dict
        )
    return payload


@router.post("/stella/stella_feedback")
async def stella_feedback(data: Dict[str, Any] = Body(...)) -> Any:
    """Forward click feedback to STELLA App (``/stella/api/v1/ranking/.../feedback``)."""
    if os.environ.get("USE_STELLA", "true").lower() != "true":
        raise HTTPException(status_code=503, detail="STELLA integration is disabled")

    stella_app_api = os.getenv(
        "STELLA_APP_API", "http://stella-app:8005/stella/api/v1"
    ).rstrip("/")
    ranking_id = data.get("ranking_id")
    payload = data.get("payload", {})

    if not ranking_id:
        raise HTTPException(status_code=400, detail="Missing ranking_id in request body")

    url = f"{stella_app_api}/ranking/{ranking_id}/feedback"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload)
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"STELLA feedback error: {e.response.text[:500]}",
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Failed to send feedback to STELLA: {e}")
