"""
Schema.org CreativeWork schema definition.

Based on Schema.org CreativeWork specification:
https://schema.org/CreativeWork

This module defines a Pydantic model for the schema:CreativeWork entity using
full IRI aliases for ease of RDF conversion.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic import ConfigDict


class CreativeWork(BaseModel):
    """Schema.org CreativeWork entity."""

    # Identification
    identifier: List[str] = Field(
        default_factory=list,
        description="Unique identifier(s) for the work (URL, mlentory ID, SPDX, etc.)",
        alias="https://schema.org/identifier",
    )
    name: str = Field(
        description="Human-readable name of the creative work",
        alias="https://schema.org/name",
    )
    url: Optional[str] = Field(
        default=None,
        description="Primary URL for the work",
        alias="https://schema.org/url",
    )
    sameAs: List[str] = Field(
        default_factory=list,
        description="URLs that refer to the same creative work",
        alias="https://schema.org/sameAs",
    )
    alternateName: List[str] = Field(
        default_factory=list,
        description="Alternate names or short codes (e.g., SPDX identifiers)",
        alias="https://schema.org/alternateName",
    )

    # Description
    description: Optional[str] = Field(
        default=None,
        description="Description or summary of the creative work",
        alias="https://schema.org/description",
    )
    abstract: Optional[str] = Field(
        default=None,
        description="Abstract or extended summary",
        alias="https://schema.org/abstract",
    )
    text: Optional[str] = Field(
        default=None,
        description="Full textual content of the creative work",
        alias="https://schema.org/text",
    )

    # Licensing / legal metadata
    license: Optional[str] = Field(
        default=None,
        description="Reference to another license when applicable",
        alias="https://schema.org/license",
    )
    version: Optional[str] = Field(
        default=None,
        description="Version identifier for the creative work",
        alias="https://schema.org/version",
    )
    copyrightNotice: Optional[str] = Field(
        default=None,
        description="Copyright notice text",
        alias="https://schema.org/copyrightNotice",
    )
    legislationJurisdiction: Optional[str] = Field(
        default=None,
        description="Jurisdiction where the license/creative work applies",
        alias="https://schema.org/legislationJurisdiction",
    )
    legislationType: Optional[str] = Field(
        default=None,
        description="Type of legislation or legal instrument",
        alias="https://schema.org/legislationType",
    )

    # Temporal metadata
    dateCreated: Optional[datetime] = Field(
        default=None,
        description="Creation date of the creative work",
        alias="https://schema.org/dateCreated",
    )
    dateModified: Optional[datetime] = Field(
        default=None,
        description="Last modification date",
        alias="https://schema.org/dateModified",
    )
    datePublished: Optional[datetime] = Field(
        default=None,
        description="Publication date of the work",
        alias="https://schema.org/datePublished",
    )

    # Provenance / metadata
    isBasedOn: List[str] = Field(
        default_factory=list,
        description="Other works this work is based on",
        alias="https://schema.org/isBasedOn",
    )
    subjectOf: List[str] = Field(
        default_factory=list,
        description="Resources for which this work is a subject",
        alias="https://schema.org/subjectOf",
    )

    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Non-standard metadata about extraction and provenance",
        alias="https://w3id.org/mlentory/mlentory_graph/meta/",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "identifier": [
                    "https://w3id.org/mlentory/mlentory_graph/license/apache-2.0",
                    "https://spdx.org/licenses/Apache-2.0.html",
                    "Apache-2.0",
                ],
                "name": "Apache License 2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0",
                "sameAs": [
                    "https://spdx.org/licenses/Apache-2.0",
                    "https://opensource.org/license/apache-2-0/",
                ],
                "alternateName": ["Apache License Version 2.0"],
                "description": "A permissive open source license published by the Apache Software Foundation.",
                "version": "2.0",
                "copyrightNotice": "Copyright 2022 Apache Software Foundation",
                "legislationJurisdiction": "Worldwide",
            }
        },
    )
