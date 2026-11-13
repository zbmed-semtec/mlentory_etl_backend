"""SPLADE learned-sparse search over ``splade_vector``.

Separate from the dense vector service so the BGE-M3, hybrid, and legacy
vector rankers stay unchanged. The score returned to the client is the
Elasticsearch sparse dot product, not a normalized similarity.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from api.config import get_es_client, get_es_config
from api.schemas.responses import FacetValue, VectorModelListItem
from api.services.faceted_search import FacetedSearchMixin
from etl_loaders.splade_encoder import get_splade_encoder

logger = logging.getLogger(__name__)

_RESULT_CAP = 100


class SpladeSearchService(FacetedSearchMixin):
    """Sparse retrieval over the same three model indexes as BGE-M3 search."""

    def __init__(self) -> None:
        self.client = get_es_client()
        self.config = get_es_config()

    def splade_search(
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
        """Dot-product search over ``splade_vector``. The query is encoded as typed."""
        filters = filters or {}
        facet_query = facet_query or {}
        if facets is None:
            facets = ["mlTask", "license", "keywords", "datasets", "platform"]

        indices = indices or self._model_search_indices()
        limit = min(max(limit, 1), _RESULT_CAP)
        page = max(page, 1)
        offset = (page - 1) * limit
        facet_config = self.get_facets_config()
        empty = {
            "total": 0,
            "page": page,
            "page_size": limit,
            "models": [],
            "filters": filters,
            "facets": {facet: [] for facet in facets},
            "facet_config": {key: value for key, value in facet_config.items() if key in facets},
        }

        query_weights = get_splade_encoder().encode_query(query or "")
        if not query_weights:
            return empty

        must_conditions: List[Dict[str, Any]] = [
            self._minimum_metadata_bool_filter(),
            {"exists": {"field": "splade_vector"}},
        ]
        must_conditions.extend(self._build_filter_conditions(filters))
        aggs = self._build_facet_aggregations(facets, facet_size, facet_query)

        body: Dict[str, Any] = {
            "from": offset,
            "size": limit,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": [
                        {
                            "sparse_vector": {
                                "field": "splade_vector",
                                "query_vector": query_weights,
                            }
                        }
                    ],
                    "filter": must_conditions,
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
                "splade_searchable_text",
            ],
        }

        logger.info("SPLADE search: indices=%s page=%s limit=%s", indices, page, limit)
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
            db_identifier = src.get("db_identifier") or []
            if isinstance(db_identifier, str):
                db_identifier = [db_identifier]
            mlentory_id = next(
                (
                    identifier
                    for identifier in db_identifier
                    if isinstance(identifier, str)
                    and identifier.startswith("https://w3id.org/mlentory/mlentory_graph/")
                ),
                "-1",
            )
            models.append(
                VectorModelListItem(
                    db_identifier=db_identifier,
                    mlentory_id=str(mlentory_id),
                    name=src.get("name") or "",
                    description=src.get("description"),
                    score=float(hit.get("_score") or 0.0),
                    searchable_text=src.get("splade_searchable_text"),
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
            buckets = ((aggs_data.get(f"{facet}_facet") or {}).get("buckets")) or []
            facet_results[facet] = [
                FacetValue(value=str(bucket.get("key")), count=int(bucket.get("doc_count", 0)))
                for bucket in buckets
            ]

        return {
            "total": total,
            "page": page,
            "page_size": limit,
            "models": models,
            "filters": filters,
            "facets": facet_results,
            "facet_config": {key: value for key, value in facet_config.items() if key in facets},
        }


splade_search_service = SpladeSearchService()
