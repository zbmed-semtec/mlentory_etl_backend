"""
Generic Graph Response Schemas.

This module defines the Pydantic models for the generic graph response structure,
suitable for representing any subgraph from the knowledge graph.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """Represents a node in the graph."""

    id: str = Field(description="Unique identifier for the node (typically URI)")
    labels: List[str] = Field(description="Node labels (e.g., MLModel, License)")
    properties: Dict[str, Any] = Field(description="Node properties", default_factory=dict)


class GraphEdge(BaseModel):
    """Represents an edge/relationship in the graph."""

    id: str = Field(description="Unique identifier for the edge")
    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    type: str = Field(description="Relationship type (e.g., HAS_LICENSE)")
    properties: Dict[str, Any] = Field(description="Edge properties", default_factory=dict)


class GraphResponse(BaseModel):
    """Response model for graph exploration endpoints."""

    nodes: List[GraphNode] = Field(description="List of nodes in the subgraph")
    edges: List[GraphEdge] = Field(description="List of edges in the subgraph")
    metadata: Dict[str, Any] = Field(description="Additional metadata about the graph query", default_factory=dict)

