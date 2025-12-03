"""
Entity Batch Request/Response Schemas.

This module defines the Pydantic models for batch entity property retrieval.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class EntityBatchRequest(BaseModel):
    """Request body for fetching properties of multiple entities."""

    entity_ids: List[str] = Field(
        description="List of entity IDs (URIs) to fetch. Can include angle brackets.",
        min_length=1
    )
    properties: Optional[List[str]] = Field(
        default=None,
        description="List of specific properties to retrieve. If empty/null, fetches all properties."
    )


class CacheStats(BaseModel):
    """Dummy cache statistics matching the frontend interface."""

    hits: int = Field(default=0, description="Number of cache hits")
    misses: int = Field(default=0, description="Number of cache misses")
    hit_rate: float = Field(default=0.0, description="Cache hit rate (0.0 to 1.0)")


class EntityBatchResponse(BaseModel):
    """Response model for batch entity retrieval."""

    count: int = Field(description="Total number of entities returned")
    cache_stats: CacheStats = Field(
        default_factory=CacheStats,
        description="Cache performance statistics"
    )
    entities: Dict[str, Dict[str, List[str]]] = Field(
        description="Map of Entity URI -> { Property Name -> List[Values] }",
        default_factory=dict
    )


class RelatedEntitiesResponse(BaseModel):
    """Response model for related entities by prefix lookup."""

    count: int = Field(description="Total number of related entities found")
    related_entities: Dict[str, Dict[str, List[str]]] = Field(
        description="Map of Entity URI -> { Property/Relationship Name -> List[Values] }",
        default_factory=dict
    )

