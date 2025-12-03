"""
Entity Batch Request/Response Schemas.

This module defines the Pydantic models for batch entity property retrieval.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Any

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

class EntityURIResponse(BaseModel):
    """Response model for entity name to URI lookup."""
    
    uri: str = Field(description="Entity URI")
    name: Optional[str] = Field(default=None, description="Entity name")
    entity_types: List[str] = Field(default_factory=list, description="Entity type labels")


class RelatedModelsResponse(BaseModel):
    """Response model for models related to an entity."""
    
    entity_uri: str = Field(description="The entity URI that was queried")
    models: List[Dict[str, Any]] = Field(
        description="List of related models with their properties and relationship types",
        default_factory=list
    )
    count: int = Field(description="Total number of related models")

class ListEntitiesResponse(BaseModel):
    """Response model for listing entities grouped by relationship type."""
    
    facets: Dict[str, List[str]] = Field(
        description="Dictionary mapping normalized relationship keys (e.g., 'keywords', 'mlTask', 'license', 'sharedBy', 'datasets') -> list of entity names",
        default_factory=dict
    )
    count: int = Field(description="Total number of unique entities across all relationship types")