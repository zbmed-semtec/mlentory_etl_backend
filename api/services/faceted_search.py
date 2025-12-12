"""
Extended Elasticsearch Service with Faceted Search Support.

This module extends the basic Elasticsearch service with advanced faceted
search capabilities including dynamic facets, filters, and facet value search.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from api.config import get_es_client, get_es_config
from api.schemas.responses import FacetConfig, FacetValue, ModelListItem

logger = logging.getLogger(__name__)


class FacetedSearchMixin:
    """Mixin that adds faceted search capabilities to Elasticsearch service."""

    def get_facets_config(self) -> Dict[str, FacetConfig]:
        """
        Get configuration for all available facets.

        Returns facet metadata including field types, labels, cardinality info,
        and search capabilities. This configuration drives dynamic UI rendering
        and query construction.

        Returns:
            Dict[str, FacetConfig]: Configuration for each facet
        """
        return {
            "mlTask": FacetConfig(
                field="ml_tasks",
                label="ML Tasks",
                type="keyword",
                icon="mdi-brain",
                is_high_cardinality=False,
                default_size=20,
                supports_search=True,
                pinned=True
            ),
            "license": FacetConfig(
                field="license",
                label="Licenses",
                type="keyword",
                icon="mdi-license",
                is_high_cardinality=False,
                default_size=10,
                supports_search=True,
                pinned=True
            ),
            "keywords": FacetConfig(
                field="keywords",
                label="Keywords",
                type="keyword",
                icon="mdi-tag",
                is_high_cardinality=True,
                default_size=20,
                supports_search=True,
                pinned=True
            ),
            "sharedBy": FacetConfig(
                field="shared_by",
                label="Shared By",
                type="keyword",
                icon="mdi-account-group",
                is_high_cardinality=True,
                default_size=10,
                supports_search=True,
                pinned=False
            ),
            "datasets": FacetConfig(
                field="datasets",
                label="Datasets",
                type="keyword",
                icon="mdi-database",
                is_high_cardinality=True,
                default_size=10,
                supports_search=True,
                pinned=False
            ),
            "platform": FacetConfig(
                field="platform",
                label="Platform",
                type="keyword",
                icon="mdi-cloud",
                is_high_cardinality=False,
                default_size=5,
                supports_search=False,
                pinned=True
            )
        }

    def _build_text_search_query(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Build multi-strategy text search query for Elasticsearch.

        Implements multiple matching strategies for high recall:
        - Multi-match across key fields
        - Cross-field matching
        - Partial wildcard matching for keywords and tasks
        - Word-level and phrase-level matching

        Args:
            query: Search query string

        Returns:
            Elasticsearch query dict or None if no query
        """
        if not query:
            return None

        # Split into individual words
        individual_words = re.split(r'[ \-_\.]', query)
        individual_words.extend(re.split(r'[ \-_\.]', query.lower()))

        # Create pairs of consecutive words
        paired_words = []
        for i in range(len(individual_words) - 1):
            paired_words.append(f"{individual_words[i]} {individual_words[i+1]}")

        # Combine words and remove duplicates
        query_words = list(set([word.strip() for word in paired_words + [query] if word.strip()]))

        should_conditions = []

        for word in query_words:
            # Cross-field matching
            should_conditions.append({
                "multi_match": {
                    "query": word,
                    "fields": ["name^2", "keywords^5", "description^2.5", "ml_tasks^1", "shared_by^1"],
                    "type": "cross_fields",
                    "operator": "or"
                }
            })

            # Best fields matching
            should_conditions.append({
                "multi_match": {
                    "query": word,
                    "fields": ["name^2", "keywords^4", "description^2.5", "ml_tasks^1", "shared_by^1"],
                    "type": "best_fields",
                    "operator": "or",
                    "boost": 0.8
                }
            })

            # Partial keyword matching
            if len(word) >= 2:
                should_conditions.append({"wildcard": {"keywords": f"*{word}*"}})
                should_conditions.append({"wildcard": {"ml_tasks": f"*{word}*"}})

        return {
            "bool": {
                "should": should_conditions,
                "minimum_should_match": 1
            }
        }

    def _build_filter_conditions(self, filters: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        """
        Build filter conditions for Elasticsearch query.

        Args:
            filters: Dictionary mapping field names to lists of values

        Returns:
            List of Elasticsearch filter conditions
        """
        must_conditions = []
        if not filters:
            return must_conditions

        facet_config = self.get_facets_config()

        for facet_key, values in filters.items():
            if not values:
                continue

            config = facet_config.get(facet_key)
            if not config:
                continue

            field_name = config.field
            field_type = config.type

            if field_type == "date":
                # Handle date range filters
                for date_filter in values:
                    if "," in str(date_filter):
                        parts = str(date_filter).split(",")
                        from_date = parts[0].strip() or None
                        to_date = parts[1].strip() if len(parts) > 1 else None

                        range_query = {"range": {field_name: {}}}
                        if from_date:
                            range_query["range"][field_name]["gte"] = from_date
                        if to_date:
                            range_query["range"][field_name]["lte"] = to_date
                        must_conditions.append(range_query)
                    else:
                        must_conditions.append({"term": {field_name: str(date_filter)}})
            else:
                # Handle keyword/text filters
                for value in values:
                    must_conditions.append({"term": {field_name: value}})

        return must_conditions

    def _build_facet_aggregations(
        self,
        facets: List[str],
        facet_size: int,
        facet_query: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Build facet aggregations for Elasticsearch query.

        Args:
            facets: List of facet keys to aggregate
            facet_size: Maximum number of values per facet
            facet_query: Search queries for specific facets

        Returns:
            Elasticsearch aggregations dict
        """
        aggs = {}
        facet_config = self.get_facets_config()

        for facet_key in facets:
            config = facet_config.get(facet_key)
            if not config:
                continue

            field_name = config.field
            field_type = config.type

            if field_type == "date":
                aggs[f"{facet_key}_facet"] = {
                    "date_histogram": {
                        "field": field_name,
                        "calendar_interval": "month",
                        "format": "yyyy-MM-dd",
                        "order": {"_key": "desc"}
                    }
                }
            else:
                terms_agg = {
                    "field": field_name,
                    "size": facet_size,
                    "order": {"_count": "desc"}
                }

                # Add include pattern for facet value search
                search_term = facet_query.get(facet_key)
                if search_term:
                    escaped_term = re.escape(search_term.lower())
                    terms_agg["include"] = f".*{escaped_term}.*"

                aggs[f"{facet_key}_facet"] = {"terms": terms_agg}

        return aggs

    def search_models_with_facets(
        self,
        query: str = "",
        filters: Optional[Dict[str, List[str]]] = None,
        page: int = 1,
        page_size: int = 50,
        facets: Optional[List[str]] = None,
        facet_size: int = 20,
        facet_query: Optional[Dict[str, str]] = None
    ) -> Tuple[List[ModelListItem], int, Dict[str, List[FacetValue]]]:
        """
        Search for models with faceted navigation support.

        Implements advanced text search with multiple matching strategies and
        dynamic facet aggregations. Supports filtering by multiple facets and
        searching within facet values.

        Args:
            query: Text search query (supports multi-word phrases)
            filters: Property filters to apply
            page: Page number (1-based)
            page_size: Results per page (max 1000)
            facets: List of facet keys to aggregate
            facet_size: Maximum values per facet
            facet_query: Search queries for specific facets

        Returns:
            Tuple of (models, total_count, facet_results)
        """
        # Ensure page_size is within bounds
        page_size = min(max(page_size, 1), 1000)
        from_offset = (page - 1) * page_size

        # Default facets if none specified
        if facets is None:
            facets = ["mlTask", "license", "keywords", "platform", "datasets"]

        filters = filters or {}
        facet_query = facet_query or {}

        # Build query conditions
        must_conditions = []

        if query:
            text_query = self._build_text_search_query(query)
            if text_query:
                must_conditions.append(text_query)

        if filters:
            must_conditions.extend(self._build_filter_conditions(filters))

        # Build aggregations
        aggs = self._build_facet_aggregations(facets, facet_size, facet_query)

        # Construct Elasticsearch query using low-level client
        search_body = {
            "from": from_offset,
            "size": page_size,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}]
                }
            },
            "aggs": aggs,
            "_source": [
                "name",
                "ml_tasks",
                "shared_by",
                "db_identifier",
                "keywords",
                "license",
                "description",
                "platform",
                "datasets",
            ],
        }

        try:
            # Execute search using raw client
            response = self.client.search(
                index=self.config.hf_models_index,
                body=search_body
            )

            # Extract hits
            hits_data = response.get("hits", {})
            total = hits_data.get("total", 0)
            total_count = total.get("value", 0) if isinstance(total, dict) else total

            # Process models
            models: List[ModelListItem] = []
            for hit in hits_data.get("hits", []):
                source = hit.get("_source", {})
                
                mlentory_id = next(
                    (id for id in source.get("db_identifier", []) if id.startswith("https://w3id.org/mlentory/mlentory_graph/")),
                    -1
                )
                
                model = ModelListItem(
                    db_identifier=source.get("db_identifier", ""),
                    mlentory_id=mlentory_id,
                    name=source.get("name", ""),
                    description=source.get("description"),
                    sharedBy=source.get("shared_by"),
                    license=source.get("license"),
                    mlTask=source.get("ml_tasks", []),
                    keywords=source.get("keywords", []),
                    datasets=source.get("datasets", []) or [],
                    platform=source.get("platform", "Unknown"),
                )
                models.append(model)

            # Process facets
            facet_results = {}
            if "aggregations" in response:
                aggs_data = response["aggregations"]
                for facet_key in facets:
                    agg_key = f"{facet_key}_facet"
                    if agg_key in aggs_data:
                        facet_results[facet_key] = [
                            FacetValue(value=str(bucket["key"]), count=bucket["doc_count"])
                            for bucket in aggs_data[agg_key]["buckets"]
                        ]

            logger.debug(
                f"Faceted search returned {len(models)} models "
                f"(page {page}, size {page_size}, total {total_count})"
            )

            return models, total_count, facet_results

        except Exception as e:
            logger.error(f"Error in faceted search: {e}", exc_info=True)
            return [], 0, {}

    def fetch_facet_values(
        self,
        field: str,
        search_query: str = "",
        after_key: str = "",
        limit: int = 50,
        current_filters: Optional[Dict[str, List[str]]] = None
    ) -> Tuple[List[FacetValue], Optional[str], bool]:
        """
        Fetch values for a specific facet with optional search and pagination.

        Supports high-cardinality facets using composite aggregations for
        pagination and regex includes for facet value search.

        Args:
            field: Facet key to get values for
            search_query: Optional search term to filter facet values
            after_key: Pagination cursor
            limit: Maximum values to return
            current_filters: Current filters for context (excluding self-filter)

        Returns:
            Tuple of (values, next_after_key, has_more)
        """
        facet_config = self.get_facets_config()
        config = facet_config.get(field)

        if not config:
            logger.warning(f"Unknown facet field: {field}")
            return [], None, False

        field_name = config.field
        current_filters = current_filters or {}

        # Build filter conditions (excluding self-filter)
        must_conditions = []
        for facet_key, values in current_filters.items():
            if values and facet_key != field:
                filter_config = facet_config.get(facet_key)
                if filter_config:
                    for value in values:
                        must_conditions.append({"term": {filter_config.field: value}})

        # Build aggregation based on whether search is needed
        if search_query:
            # Use terms aggregation with include for search
            escaped_term = re.escape(search_query.lower())
            agg_config = {
                "terms": {
                    "field": field_name,
                    "size": limit,
                    "order": {"_count": "desc"},
                    "include": f".*{escaped_term}.*"
                }
            }
            use_composite = False
        else:
            # Use composite aggregation for pagination
            composite_agg = {
                "size": limit,
                "sources": [{field: {"terms": {"field": field_name, "order": "asc"}}}]
            }
            if after_key:
                composite_agg["after"] = {field: after_key}

            agg_config = {"composite": composite_agg}
            use_composite = True

        search_body = {
            "size": 0,
            "query": {
                "bool": {
                    "must": must_conditions if must_conditions else [{"match_all": {}}]
                }
            },
            "aggs": {"facet_values": agg_config}
        }

        try:
            response = self.client.search(
                index=self.config.hf_models_index,
                body=search_body
            )

            aggs_data = response.get("aggregations", {})
            facet_data = aggs_data.get("facet_values", {})
            buckets = facet_data.get("buckets", [])

            if use_composite:
                # Composite aggregation response
                values = [
                    FacetValue(value=str(bucket["key"][field]), count=bucket["doc_count"])
                    for bucket in buckets
                ]
                next_after_key = facet_data.get("after_key", {}).get(field)
                has_more = next_after_key is not None
            else:
                # Terms aggregation response
                values = [
                    FacetValue(value=str(bucket["key"]), count=bucket["doc_count"])
                    for bucket in buckets
                ]
                next_after_key = None
                has_more = False

            return values, next_after_key, has_more

        except Exception as e:
            logger.error(f"Error fetching facet values for {field}: {e}", exc_info=True)
            return [], None, False
