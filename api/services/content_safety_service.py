"""Set a model's contentSafety mark.

Writes the durable review notebook, then updates the live search document
so the model is hidden or shown without waiting for an index rebuild.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Dict, List, Optional

from fastapi import Header, HTTPException

from etl_loaders.content_safety_store import ALLOWED, record_decision
from etl_loaders.index_loader import MLENTORY_GRAPH_PREFIX

CONTENT_SAFETY_HEADER = "X-Content-Safety-Token"


def require_content_safety_token(
    x_content_safety_token: str = Header(default="", alias=CONTENT_SAFETY_HEADER),
) -> None:
    """Reject callers who do not have the review token. Closed when unset."""
    expected = os.getenv("CONTENT_SAFETY_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Content safety updates are not configured")
    provided = x_content_safety_token or ""
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Not authorized")


def _normalize_model_uri(model_id: str) -> str:
    if model_id.startswith("https://") or model_id.startswith("http://"):
        return model_id
    return f"{MLENTORY_GRAPH_PREFIX}{model_id}"


def _canonical_id(hit: Dict[str, Any], requested_uri: str) -> str:
    source = hit.get("_source") or {}
    mlentory_id = source.get("mlentory_id")
    if isinstance(mlentory_id, str) and mlentory_id.startswith(MLENTORY_GRAPH_PREFIX):
        return mlentory_id
    for identifier in source.get("db_identifier") or []:
        if isinstance(identifier, str) and identifier.startswith(MLENTORY_GRAPH_PREFIX):
            return identifier
    return requested_uri


def find_model_documents(client: Any, indices: List[str], model_id: str) -> List[Dict[str, Any]]:
    """Find index documents for a model, including ones already marked inappropriate."""
    model_uri = _normalize_model_uri(model_id)
    response = client.search(
        index=indices,
        body={
            "size": 10,
            "query": {"match": {"db_identifier": model_uri}},
        },
        params={"ignore_unavailable": "true"},
    )
    return response["hits"]["hits"]


def apply_content_safety(
    client: Any,
    indices: List[str],
    model_id: str,
    value: str,
    store_path: Optional[Any] = None,
) -> Dict[str, str]:
    """Save one review decision and copy it onto the live search documents."""
    if value not in ALLOWED:
        raise ValueError(f"contentSafety must be one of {sorted(ALLOWED)}")

    requested_uri = _normalize_model_uri(model_id)
    hits = find_model_documents(client, indices, model_id)
    if not hits:
        raise LookupError(requested_uri)

    canonical_id = _canonical_id(hits[0], requested_uri)
    record_decision(canonical_id, value, store_path)
    for hit in hits:
        client.update(
            index=hit["_index"],
            id=hit["_id"],
            doc={"contentSafety": value},
            refresh="wait_for",
        )
    return {"model_id": canonical_id, "contentSafety": value}
