"""
Schema.org DefinedTerm schema definition.

A word, name, acronym, phrase, etc. with a formal definition. Often used in the
context of category or subject classification, glossaries or dictionaries,
product or creative work types, etc.

Reference: https://schema.org/DefinedTerm
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class DefinedTerm(BaseModel):
    """
    Schema.org DefinedTerm entity.
    
    Represents a term with a formal definition, such as task types, categories,
    or glossary entries.
    """
    
    # Core identification
    identifier: List[str] = Field(
        default_factory=list,
        description="Unique identifier(s) for the term (MLentory ID, URL, etc.)",
        alias="https://schema.org/identifier",
    )
    name: str = Field(
        description="The term being defined",
        alias="https://schema.org/name",
    )
    url: Optional[str] = Field(
        default=None,
        description="Primary URL for the term definition",
        alias="https://schema.org/url",
    )
    sameAs: List[str] = Field(
        default_factory=list,
        description="Alternative URLs for the same term (definition sources, Wikidata, etc.)",
        alias="https://schema.org/sameAs",
    )
    
    # Term-specific properties
    termCode: Optional[str] = Field(
        default=None,
        description="A code that identifies this term within a term set",
        alias="https://schema.org/termCode",
    )
    inDefinedTermSet: List[str] = Field(
        default_factory=list,
        description="The term set(s) that contain this term (URLs or identifiers)",
        alias="https://schema.org/inDefinedTermSet",
    )
    
    # Description and aliases
    description: Optional[str] = Field(
        default=None,
        description="Definition or description of the term",
        alias="https://schema.org/description",
    )
    alternateName: List[str] = Field(
        default_factory=list,
        description="Alternative names or aliases for this term",
        alias="https://schema.org/alternateName",
    )
    
    # Provenance
    extraction_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about how this term's data was extracted",
        alias="https://w3id.org/mlentory/mlentory_graph/meta/",
    )
    
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "identifier": [
                    "https://w3id.org/mlentory/mlentory_graph/term/abc123",
                    "https://huggingface.co/tasks/text-classification",
                ],
                "name": "text-classification",
                "url": "https://huggingface.co/tasks/text-classification",
                "termCode": "text-classification",
                "description": "Assigning a label or class to a given text",
                "inDefinedTermSet": [
                    "https://huggingface.co/tasks",
                    "https://huggingface.co/tasks/nlp",
                ],
                "alternateName": ["text classification", "document classification"],
                "sameAs": [
                    "https://www.wikidata.org/wiki/Q1234567",
                    "https://paperswithcode.com/task/text-classification",
                ],
                "extraction_metadata": {
                    "extraction_method": "catalog_csv",
                    "confidence": 1.0,
                },
            }
        },
    )

