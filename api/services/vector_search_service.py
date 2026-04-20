"""
Vector search service for MLentory API.

Mirrors the behavior of mlentory_backend's /models/search_with_vector endpoint:
- encodes the user query into a vector embedding
- runs cosine similarity against the indexed `model_vector` dense_vector field
- supports filters + facet aggregations
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from api.config import get_es_client, get_es_config
from api.services.faceted_search import FacetedSearchMixin

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None


class _Embedder:
    def __init__(self, model_name: str) -> None:
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers is not available")
        self._model_name = model_name
        self._model: Optional[Any] = None
        self._cache: Dict[str, List[float]] = {}

    def _load(self) -> Any:
        if self._model is None:
            token = os.getenv("HUGGINGFACE_HUB_TOKEN") or os.getenv("HF_TOKEN")
            self._model = SentenceTransformer(
                self._model_name,
                trust_remote_code=True,
                token=token if token else None,
            )
        return self._model

    def encode(self, text: str) -> List[float]:
        key = (text or "").strip()
        if key in self._cache:
            return self._cache[key]
        model = self._load()
        emb = model.encode([key], show_progress_bar=False, normalize_embeddings=False)[0]
        vec = emb.tolist()
        self._cache[key] = vec
        return vec


_EMBEDDER: Optional[_Embedder] = None


def _get_embedder() -> _Embedder:
    global _EMBEDDER
    if _EMBEDDER is None:
        model_name = os.getenv(
            "VECTOR_SEARCH_EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"
        )
        _EMBEDDER = _Embedder(model_name=model_name)
    return _EMBEDDER


class VectorSearchService(FacetedSearchMixin):
    """
    Vector search service that queries Elasticsearch using cosine similarity against `model_vector`.
    """

    def __init__(self) -> None:
        self.client = get_es_client()
        self.config = get_es_config()

    def vector_search(
        self,
        *,
        query: str = "",
        filters: Optional[Dict[str, List[str]]] = None,
        limit: int = 50,
        page: int = 1,
        facets: Optional[List[str]] = None,
        facet_size: int = 20,
        facet_query: Optional[Dict[str, str]] = None,
        indices: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if SentenceTransformer is None:
            return {
                "models": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "facets": {},
                "facet_config": {},
                "error": "sentence-transformers not installed in API container",
            }

        filters = filters or {}
        facet_query = facet_query or {}
        if facets is None:
            facets = ["mlTask", "license", "keywords", "datasets", "platform"]

        # default to the API's HF index unless explicitly overridden
        indices = indices or [self.config.hf_models_index]

        # pagination
        limit = min(max(limit, 1), 1000)
        page = max(page, 1)
        offset = (page - 1) * limit

        # encode query
        query_vector = _get_embedder().encode(query or "")

        # base query: only docs that actually have vectors
        must_conditions: List[Dict[str, Any]] = [{"exists": {"field": "model_vector"}}]
        must_conditions.extend(self._build_filter_conditions(filters))

        base_query: Dict[str, Any] = {"bool": {"must": must_conditions}} if must_conditions else {"match_all": {}}

        aggs = self._build_facet_aggregations(facets, facet_size, facet_query)
        facet_config = self.get_facets_config()

        body: Dict[str, Any] = {
            "from": offset,
            "size": limit,
            "track_total_hits": True,
            "query": {
                "script_score": {
                    "query": base_query,
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'model_vector') + 1.0",
                        "params": {"query_vector": query_vector},
                    },
                }
            },
            "aggs": aggs,
            "_source": [
                "name",
                "description",
                "ml_tasks",
                "keywords",
                "platform",
                "db_identifier",
                "shared_by",
                "license",
                "datasets",
                "searchable_text",
            ],
        }

        logger.info("Vector search: indices=%s page=%s limit=%s", indices, page, limit)
        resp = self.client.search(
            index=indices,
            body=body,
            params={"ignore_unavailable": "true"},
            request_timeout=60,
        )

        hits = (resp.get("hits") or {}).get("hits", []) or []
        total_raw = (resp.get("hits") or {}).get("total", 0)
        total = int(total_raw.get("value", 0) if isinstance(total_raw, dict) else total_raw)

        models: List[Dict[str, Any]] = []
        for hit in hits:
            src = hit.get("_source", {}) or {}
            raw_score = float(hit.get("_score") or 0.0)  # cosineSimilarity+1 ∈ [0,2]
            src["score"] = raw_score / 2.0
            models.append(src)

        facet_results: Dict[str, List[Dict[str, Any]]] = {}
        aggs_data = resp.get("aggregations") or {}
        for facet in facets:
            key = f"{facet}_facet"
            buckets = (aggs_data.get(key) or {}).get("buckets") or []
            facet_results[facet] = [{"value": str(b.get("key")), "count": int(b.get("doc_count", 0))} for b in buckets]

        return {
            "query": query,
            "page": page,
            "limit": limit,
            "models": models,
            "total": total,
            "facets": facet_results,
            "facet_config": {k: v for k, v in facet_config.items() if k in facets},
        }


vector_search_service = VectorSearchService()

