"""
API Response Schemas.

This module defines Pydantic models for all API responses. It reuses and extends
the existing FAIR4ML schema definitions to ensure consistency between the ETL
pipeline and the API layer.

Field Naming:
    We use camelCase for FAIR4ML-compliant fields (e.g., sharedBy, mlTask)
    to match the FAIR4ML specification and JSON-LD conventions.

Example:
    >>> from api.schemas.responses import ModelDetail
    >>> 
    >>> # Create a model detail response
    >>> model = ModelDetail(
    ...     identifier=["https://w3id.org/mlentory/model/123"],
    ...     name="bert-base-uncased",
    ...     description="BERT base model",
    ...     sharedBy="google",
    ...     mlTask=["fill-mask"],
    ...     keywords=["bert", "nlp"],
    ...     platform="Hugging Face",
    ...     related_entities={
    ...         "schema__license": [{"uri": "...", "name": "Apache-2.0"}]
    ...     }
    ... )
"""

from __future__ import annotations

from typing import Generic, List, Optional, TypeVar, Dict, Any
from pydantic import BaseModel, Field

from schemas.fair4ml.mlmodel import MLModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    count: int = Field(description="Total number of items")
    next: Optional[str] = Field(description="URL to next page", default=None)
    prev: Optional[str] = Field(description="URL to previous page", default=None)
    results: List[T] = Field(description="List of items for this page")


class ModelListItem(BaseModel):
    """Basic model information from Elasticsearch for list views."""

    db_identifier: str = Field(description="Unique identifier/URI for the model")
    name: str = Field(description="Model name")
    description: Optional[str] = Field(description="Model description", default=None)
    sharedBy: Optional[str] = Field(description="Entity that shared the model", default=None)
    license: Optional[str] = Field(description="Model license", default=None)
    mlTask: List[str] = Field(description="Machine learning tasks", default_factory=list)
    keywords: List[str] = Field(description="Model keywords/tags", default_factory=list)
    platform: str = Field(description="Platform where model is hosted (e.g., 'Hugging Face')")


class ModelDetail(MLModel):
    """Extended model information with related entities from Neo4j."""

    # Add platform field (not in FAIR4ML schema)
    platform: Optional[str] = Field(
        description="Platform where model is hosted (e.g., 'Hugging Face')",
        default=None
    )

    # Related entities from Neo4j knowledge graph
    related_entities: Dict[str, List[Dict[str, Any]]] = Field(
        description="Related entities grouped by relationship type",
        default_factory=dict
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Service status")
    version: str = Field(description="API version")
    elasticsearch: bool = Field(description="Elasticsearch connection status")
    neo4j: bool = Field(description="Neo4j connection status")


class FacetValue(BaseModel):
    """A single facet value with count."""

    value: str = Field(description="Facet value")
    count: int = Field(description="Number of models with this value")


class FacetConfig(BaseModel):
    """Configuration for a single facet."""

    field: str = Field(description="Elasticsearch field name")
    label: str = Field(description="Human-readable label")
    type: str = Field(description="Data type (keyword, boolean, number, date)")
    icon: Optional[str] = Field(description="UI icon identifier", default=None)
    is_high_cardinality: bool = Field(description="Whether facet has many values", default=False)
    default_size: int = Field(description="Default number of values to fetch", default=20)
    supports_search: bool = Field(description="Whether facet supports search within values", default=True)
    pinned: bool = Field(description="Whether facet should be visible by default", default=False)


class FacetedSearchResponse(BaseModel):
    """Response for faceted search with models, total count, and facets."""

    models: List[ModelListItem] = Field(description="List of models for current page")
    total: int = Field(description="Total number of matching models")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Number of results per page")
    filters: Dict[str, List[str]] = Field(description="Applied filters", default_factory=dict)
    facets: Dict[str, List[FacetValue]] = Field(description="Facet aggregations with counts", default_factory=dict)
    facet_config: Dict[str, FacetConfig] = Field(description="Configuration for requested facets", default_factory=dict)


class FacetValuesResponse(BaseModel):
    """Response for fetching values of a specific facet."""

    values: List[FacetValue] = Field(description="List of facet values with counts")
    after_key: Optional[str] = Field(description="Next pagination cursor", default=None)
    has_more: bool = Field(description="Whether more values are available", default=False)
