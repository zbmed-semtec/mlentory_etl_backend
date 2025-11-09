"""
Schema.org ScholarlyArticle schema definition.

Based on Schema.org ScholarlyArticle specification:
https://schema.org/ScholarlyArticle

This module defines Pydantic models for the schema:ScholarlyArticle entity, using
field names aligned with Schema.org property names (with full IRI aliases) to
facilitate RDF conversion.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field
from pydantic import ConfigDict


class ScholarlyArticle(BaseModel):
    """
    Schema.org ScholarlyArticle entity.
    
    Represents a scholarly article with metadata aligned to the Schema.org
    ScholarlyArticle specification. Field names use Schema.org local names
    with full IRI aliases for RDF conversion.
    """
    
    # ========== Core Identification (schema.org) ==========
    identifier: List[str] = Field(
        default_factory=list,
        description="Unique identifier(s) for the article (arXiv ID, MLentory ID, DOI, etc.)",
        alias="https://schema.org/identifier"
    )
    name: str = Field(
        description="Title of the article", 
        alias="https://schema.org/name"
    )
    url: str = Field(
        description="Primary URL where the article can be accessed (e.g., arXiv abstract page)",
        alias="https://schema.org/url"
    )
    sameAs: List[str] = Field(
        default_factory=list,
        description="Alternative URLs for the same article (DOI, PDF, etc.)",
        alias="https://schema.org/sameAs"
    )
    
    # ========== Description & Content (schema.org) ==========
    description: Optional[str] = Field(
        default=None,
        description="Abstract or summary of the article (schema:description)",
        alias="https://schema.org/description"
    )
    about: List[str] = Field(
        default_factory=list,
        description="Subject categories or topics the article is about (schema:about)",
        alias="https://schema.org/about"
    )
    
    # ========== Authorship (schema.org) ==========
    author: List[str] = Field(
        default_factory=list,
        description="Author(s) of the article (schema:author)",
        alias="https://schema.org/author"
    )
    
    # ========== Temporal Information (schema.org) ==========
    datePublished: Optional[datetime] = Field(
        default=None,
        description="Date the article was published (schema:datePublished)",
        alias="https://schema.org/datePublished"
    )
    dateModified: Optional[datetime] = Field(
        default=None,
        description="Date the article was last modified (schema:dateModified)",
        alias="https://schema.org/dateModified"
    )
    
    # ========== Publication Context (schema.org) ==========
    isPartOf: Optional[str] = Field(
        default=None,
        description="Publication, journal, or collection this article is part of (schema:isPartOf)",
        alias="https://schema.org/isPartOf"
    )
    
    # ========== Additional Metadata (schema.org) ==========
    comment: Optional[str] = Field(
        default=None,
        description="Additional comments about the article (schema:comment)",
        alias="https://schema.org/comment"
    )
    
    # ========== Extraction Metadata (non-standard extension) ==========
    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about how this article was extracted - non-standard extension for provenance",
        alias="https://w3id.org/mlentory/mlentory_graph/meta/"
    )

    # Allow populating fields by their Python names even when aliases are defined
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "identifier": [
                    "https://w3id.org/mlentory/mlentory_graph/abc123",
                    "https://arxiv.org/abs/2106.09685",
                    "arXiv:2106.09685"
                ],
                "name": "Attention Is All You Need",
                "url": "https://arxiv.org/abs/1706.03762",
                "sameAs": [
                    "https://arxiv.org/pdf/1706.03762.pdf",
                    "https://doi.org/10.48550/arXiv.1706.03762"
                ],
                "description": "The dominant sequence transduction models...",
                "author": ["Vaswani, Ashish", "Shazeer, Noam"],
                "datePublished": "2017-06-12T00:00:00",
                "about": ["cs.CL", "cs.LG"],
                "isPartOf": "arXiv preprint"
            }
        },
    )

