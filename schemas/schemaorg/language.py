"""
Schema.org Language schema definition.

Natural languages such as Spanish, Tamil, Hindi, English, etc. Formal language 
code tags expressed in BCP 47 can be used via the alternateName property.

Reference: https://schema.org/Language
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class Language(BaseModel):
    """
    Schema.org Language entity.
    
    Represents a natural language with its ISO 639 codes and metadata.
    """
    
    # Core identification
    identifier: List[str] = Field(
        default_factory=list,
        description="Unique identifier(s) for the language (MLentory ID, etc.)",
        alias="https://schema.org/identifier",
    )
    name: str = Field(
        description="The name of the language (e.g., 'English', 'Spanish')",
        alias="https://schema.org/name",
    )
    url: Optional[str] = Field(
        default=None,
        description="Primary URL for the language definition or reference",
        alias="https://schema.org/url",
    )
    sameAs: List[str] = Field(
        default_factory=list,
        description="Alternative URLs that identify the same language (e.g., Wikidata)",
        alias="https://schema.org/sameAs",
    )
    
    # Language codes (per Schema.org guidance, BCP 47 codes via alternateName)
    alternateName: List[str] = Field(
        default_factory=list,
        description="Alternative names and language codes (ISO 639-1, ISO 639-2, BCP 47 tags)",
        alias="https://schema.org/alternateName",
    )
    
    # Description
    description: Optional[str] = Field(
        default=None,
        description="Description of the language, scope, or type",
        alias="https://schema.org/description",
    )
    
    # Provenance
    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about how this language's data was extracted",
        alias="https://w3id.org/mlentory/mlentory_graph/meta/",
    )
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "identifier": [
                    "https://w3id.org/mlentory/mlentory_graph/language/abc123",
                ],
                "name": "English",
                "url": "https://www.wikidata.org/wiki/Q1860",
                "alternateName": ["en", "eng", "en-US"],
                "description": "ISO language (Individual, Living)",
                "sameAs": [
                    "https://www.wikidata.org/wiki/Q1860",
                ],
                "extraction_metadata": {
                    "extraction_method": "pycountry",
                    "confidence": 1.0,
                },
            }
        },
    )

