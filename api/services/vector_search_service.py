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
from api.schemas.responses import FacetValue, VectorModelListItem
from api.services.faceted_search import FacetedSearchMixin

logger = logging.getLogger(__name__)

# STELLA only ranks page 1, and that page is at most 100 hits.
_VECTOR_RESULT_CAP = 100

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


class _BgeM3Embedder:
    """Query encoder for BGE-M3. Retrieval uses the raw query, with normalized vectors."""

    def __init__(self) -> None:
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers is not available")
        self._model: Optional[Any] = None
        self._cache: Dict[str, List[float]] = {}

    def _load(self) -> Any:
        if self._model is None:
            token = os.getenv("HUGGINGFACE_HUB_TOKEN") or os.getenv("HF_TOKEN")
            self._model = SentenceTransformer(
                "BAAI/bge-m3",
                trust_remote_code=True,
                token=token if token else None,
            )
        return self._model

    def encode(self, text: str) -> List[float]:
        key = (text or "").strip()
        if key in self._cache:
            return self._cache[key]
        emb = self._load().encode([key], show_progress_bar=False, normalize_embeddings=True)[0]
        vec = emb.tolist()
        self._cache[key] = vec
        return vec


_BGE_M3_EMBEDDER: Optional[_BgeM3Embedder] = None


def _get_bge_m3_embedder() -> _BgeM3Embedder:
    global _BGE_M3_EMBEDDER
    if _BGE_M3_EMBEDDER is None:
        _BGE_M3_EMBEDDER = _BgeM3Embedder()
    return _BGE_M3_EMBEDDER


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
                "page_size": limit,
                "filters": filters or {},
                "facets": {},
                "facet_config": {},
                "error": "sentence-transformers not installed in API container",
            }

        filters = filters or {}
        facet_query = facet_query or {}
        if facets is None:
            facets = ["mlTask", "license", "keywords", "datasets", "platform"]

        # default to HF + AI4Life model indexes unless explicitly overridden
        indices = indices or self._model_search_indices()

        # pagination
        limit = min(max(limit, 1), _VECTOR_RESULT_CAP)
        page = max(page, 1)
        offset = (page - 1) * limit

        # encode query
        query_vector = _get_embedder().encode(query or "")

        # base query: minimum metadata + only docs that actually have vectors
        must_conditions: List[Dict[str, Any]] = [
            self._minimum_metadata_bool_filter(),
            {"exists": {"field": "model_vector"}},
        ]
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
                "source",
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

        models: List[VectorModelListItem] = []
        for hit in hits:
            src = hit.get("_source", {}) or {}
            raw_score = float(hit.get("_score") or 0.0)  # cosineSimilarity+1 ∈ [0,2]
            normalized_score = raw_score / 2.0
            db_identifier = src.get("db_identifier") or []
            if isinstance(db_identifier, str):
                db_identifier = [db_identifier]

            mlentory_id = next(
                (
                    _id
                    for _id in db_identifier
                    if isinstance(_id, str)
                    and _id.startswith("https://w3id.org/mlentory/mlentory_graph/")
                ),
                "-1",
            )

            models.append(
                VectorModelListItem(
                    db_identifier=db_identifier,
                    mlentory_id=str(mlentory_id),
                    name=src.get("name") or "",
                    description=src.get("description"),
                    score=normalized_score,
                    searchable_text=src.get("searchable_text"),
                    sharedBy=src.get("shared_by"),
                    license=src.get("license"),
                    mlTask=src.get("ml_tasks") or [],
                    keywords=src.get("keywords") or [],
                    datasets=src.get("datasets") or [],
                    platform=src.get("source") or "Unknown",
                )
            )

        facet_results: Dict[str, List[FacetValue]] = {}
        aggs_data = resp.get("aggregations") or {}
        for facet in facets:
            key = f"{facet}_facet"
            buckets = (aggs_data.get(key) or {}).get("buckets") or []
            facet_results[facet] = [
                FacetValue(value=str(b.get("key")), count=int(b.get("doc_count", 0))) for b in buckets
            ]

        return {
            "total": total,
            "page": page,
            "page_size": limit,
            "models": models,
            "filters": filters,
            "facets": facet_results,
            "facet_config": {k: v for k, v in facet_config.items() if k in facets},
        }

    def bge_m3_vector_search(
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
        """Cosine search over `bge_m3_vector`. Does not read `model_vector` or `improved_model_vector`."""
        if SentenceTransformer is None:
            return {
                "models": [],
                "total": 0,
                "page": page,
                "page_size": limit,
                "filters": filters or {},
                "facets": {},
                "facet_config": {},
                "error": "sentence-transformers not installed in API container",
            }

        filters = filters or {}
        facet_query = facet_query or {}
        if facets is None:
            facets = ["mlTask", "license", "keywords", "datasets", "platform"]

        indices = indices or self._model_search_indices()
        limit = min(max(limit, 1), _VECTOR_RESULT_CAP)
        page = max(page, 1)
        offset = (page - 1) * limit
        query_vector = _get_bge_m3_embedder().encode(query or "")

        must_conditions: List[Dict[str, Any]] = [
            self._minimum_metadata_bool_filter(),
            {"exists": {"field": "bge_m3_vector"}},
        ]
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
                        "source": "cosineSimilarity(params.query_vector, 'bge_m3_vector') + 1.0",
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
                "source",
                "db_identifier",
                "shared_by",
                "license",
                "datasets",
                "bge_m3_searchable_text",
            ],
        }

        logger.info("BGE-M3 vector search: indices=%s page=%s limit=%s", indices, page, limit)
        resp = self.client.search(
            index=indices,
            body=body,
            params={"ignore_unavailable": "true"},
            request_timeout=60,
        )

        hits = (resp.get("hits") or {}).get("hits", []) or []
        total_raw = (resp.get("hits") or {}).get("total", 0)
        total = int(total_raw.get("value", 0) if isinstance(total_raw, dict) else total_raw)

        models: List[VectorModelListItem] = []
        for hit in hits:
            src = hit.get("_source", {}) or {}
            raw_score = float(hit.get("_score") or 0.0)
            normalized_score = raw_score / 2.0
            db_identifier = src.get("db_identifier") or []
            if isinstance(db_identifier, str):
                db_identifier = [db_identifier]

            mlentory_id = next(
                (
                    _id
                    for _id in db_identifier
                    if isinstance(_id, str)
                    and _id.startswith("https://w3id.org/mlentory/mlentory_graph/")
                ),
                "-1",
            )

            models.append(
                VectorModelListItem(
                    db_identifier=db_identifier,
                    mlentory_id=str(mlentory_id),
                    name=src.get("name") or "",
                    description=src.get("description"),
                    score=normalized_score,
                    searchable_text=src.get("bge_m3_searchable_text"),
                    sharedBy=src.get("shared_by"),
                    license=src.get("license"),
                    mlTask=src.get("ml_tasks") or [],
                    keywords=src.get("keywords") or [],
                    datasets=src.get("datasets") or [],
                    platform=src.get("source") or "Unknown",
                )
            )

        facet_results: Dict[str, List[FacetValue]] = {}
        aggs_data = resp.get("aggregations") or {}
        for facet in facets:
            key = f"{facet}_facet"
            buckets = (aggs_data.get(key) or {}).get("buckets") or []
            facet_results[facet] = [
                FacetValue(value=str(b.get("key")), count=int(b.get("doc_count", 0))) for b in buckets
            ]

        return {
            "total": total,
            "page": page,
            "page_size": limit,
            "models": models,
            "filters": filters,
            "facets": facet_results,
            "facet_config": {k: v for k, v in facet_config.items() if k in facets},
        }


def _hit_to_vector_item(hit: Dict[str, Any], score: float) -> VectorModelListItem:
    src = hit.get("_source") or {}
    db_identifier = src.get("db_identifier") or []
    if isinstance(db_identifier, str):
        db_identifier = [db_identifier]
    mlentory_id = next(
        (
            _id
            for _id in db_identifier
            if isinstance(_id, str) and _id.startswith("https://w3id.org/mlentory/mlentory_graph/")
        ),
        "-1",
    )
    return VectorModelListItem(
        db_identifier=db_identifier,
        mlentory_id=str(mlentory_id),
        name=src.get("name") or "",
        description=src.get("description"),
        score=score,
        searchable_text=src.get("bge_m3_searchable_text"),
        sharedBy=src.get("shared_by"),
        license=src.get("license"),
        mlTask=src.get("ml_tasks") or [],
        keywords=src.get("keywords") or [],
        datasets=src.get("datasets") or [],
        platform=src.get("source") or "Unknown",
    )


def _reciprocal_rank_fusion(
    ranked_lists: List[List[Dict[str, Any]]],
    *,
    rank_constant: int = 60,
) -> List[tuple]:
    """Fuse ranked hit lists. Score is rank-only: sum 1/(rank_constant + rank)."""
    scores: Dict[str, float] = {}
    hits_by_id: Dict[str, Dict[str, Any]] = {}
    for hits in ranked_lists:
        for rank, hit in enumerate(hits, start=1):
            hit_id = str(hit.get("_id"))
            scores[hit_id] = scores.get(hit_id, 0.0) + 1.0 / (rank_constant + rank)
            hits_by_id.setdefault(hit_id, hit)
    max_score = len(ranked_lists) / (rank_constant + 1)
    ordered = sorted(scores, key=lambda hit_id: scores[hit_id], reverse=True)
    return [
        (hits_by_id[hit_id], scores[hit_id] / max_score if max_score else 0.0)
        for hit_id in ordered
    ]


class _HybridSearch(VectorSearchService):
    """Improved keyword search plus BGE-M3 cosine, fused with reciprocal rank fusion."""

    def hybrid_bge_m3_search(
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
        rank_constant: int = 60,
        rank_window_size: int = 100,
    ) -> Dict[str, Any]:
        if SentenceTransformer is None:
            return {
                "models": [],
                "total": 0,
                "page": page,
                "page_size": limit,
                "filters": filters or {},
                "facets": {},
                "facet_config": {},
                "error": "sentence-transformers not installed in API container",
            }

        filters = filters or {}
        facet_query = facet_query or {}
        if facets is None:
            facets = ["mlTask", "license", "keywords", "datasets", "platform"]

        indices = indices or self._model_search_indices()
        limit = min(max(limit, 1), _VECTOR_RESULT_CAP)
        page = max(page, 1)
        offset = (page - 1) * limit
        window = min(max(rank_window_size, offset + limit), _VECTOR_RESULT_CAP)

        pool_filters: List[Dict[str, Any]] = [
            self._minimum_metadata_bool_filter(),
            {"exists": {"field": "bge_m3_vector"}},
        ]
        pool_filters.extend(self._build_filter_conditions(filters))
        keyword_must = list(pool_filters)
        text_query = self._build_improved_text_search_query(query) if query else None
        if text_query:
            keyword_must.append(text_query)

        source_fields = [
            "name",
            "description",
            "ml_tasks",
            "keywords",
            "source",
            "db_identifier",
            "shared_by",
            "license",
            "datasets",
            "bge_m3_searchable_text",
        ]
        keyword_body: Dict[str, Any] = {
            "size": window,
            "query": {"bool": {"must": keyword_must}},
            "_source": source_fields,
        }
        query_vector = _get_bge_m3_embedder().encode(query or "")
        aggs = self._build_facet_aggregations(facets, facet_size, facet_query)
        vector_body: Dict[str, Any] = {
            "size": window,
            "query": {
                "script_score": {
                    "query": {"bool": {"must": pool_filters}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'bge_m3_vector') + 1.0",
                        "params": {"query_vector": query_vector},
                    },
                }
            },
            "aggs": aggs,
            "_source": source_fields,
        }

        logger.info("Hybrid BGE-M3 search: indices=%s page=%s limit=%s window=%s", indices, page, limit, window)
        keyword_resp = self.client.search(
            index=indices,
            body=keyword_body,
            params={"ignore_unavailable": "true"},
            request_timeout=60,
        )
        vector_resp = self.client.search(
            index=indices,
            body=vector_body,
            params={"ignore_unavailable": "true"},
            request_timeout=60,
        )
        fused = _reciprocal_rank_fusion(
            [
                (keyword_resp.get("hits") or {}).get("hits") or [],
                (vector_resp.get("hits") or {}).get("hits") or [],
            ],
            rank_constant=rank_constant,
        )
        page_hits = fused[offset : offset + limit]

        facet_config = self.get_facets_config()
        facet_results: Dict[str, List[FacetValue]] = {}
        aggs_data = vector_resp.get("aggregations") or {}
        for facet in facets:
            buckets = ((aggs_data.get(f"{facet}_facet") or {}).get("buckets")) or []
            facet_results[facet] = [
                FacetValue(value=str(bucket.get("key")), count=int(bucket.get("doc_count", 0)))
                for bucket in buckets
            ]

        return {
            "total": len(fused),
            "page": page,
            "page_size": limit,
            "models": [_hit_to_vector_item(hit, score) for hit, score in page_hits],
            "filters": filters,
            "facets": facet_results,
            "facet_config": {k: v for k, v in facet_config.items() if k in facets},
        }


vector_search_service = _HybridSearch()

