"""
Croissant Dataset schema definition (dataset-level only).

Based on the Croissant specification:
https://raw.githubusercontent.com/mlcommons/croissant/main/docs/croissant-spec.md

This module defines a Pydantic model for Croissant Dataset metadata at the
dataset level only (excluding RecordSet, FileObject, FileSet, etc.).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic import ConfigDict


class CroissantDataset(BaseModel):
    """
    Croissant Dataset entity (dataset-level metadata only).
    
    Represents dataset-level information following the Croissant specification,
    using full IRI aliases for schema.org, Dublin Core Terms, and Croissant
    vocabulary.
    """
    
    # Core identification (schema.org)
    identifier: List[str] = Field(
        default_factory=list,
        description="Unique identifier(s) for the dataset (MLentory ID, URL, etc.)",
        alias="https://schema.org/identifier",
    )
    name: str = Field(
        description="Name of the dataset",
        alias="https://schema.org/name",
    )
    url: Optional[str] = Field(
        default=None,
        description="Primary URL where the dataset can be accessed",
        alias="https://schema.org/url",
    )
    sameAs: List[str] = Field(
        default_factory=list,
        description="Alternative URLs for the same dataset (mirrors, homepages, etc.)",
        alias="https://schema.org/sameAs",
    )
    
    # Description & documentation (schema.org)
    description: Optional[str] = Field(
        default=None,
        description="Description or summary of the dataset",
        alias="https://schema.org/description",
    )
    
    # Licensing (schema.org)
    license: Optional[str] = Field(
        default=None,
        description="License URL or identifier for the dataset",
        alias="https://schema.org/license",
    )
    
    # Croissant conformance (Dublin Core Terms)
    conformsTo: Optional[str] = Field(
        default="http://mlcommons.org/croissant/1.0",
        description="URI of the standard the dataset conforms to (Croissant version)",
        alias="http://purl.org/dc/terms/conformsTo",
    )
    
    # Citation (Croissant)
    citeAs: Optional[str] = Field(
        default=None,
        description="Citation text or BibTeX for referencing the dataset",
        alias="http://mlcommons.org/croissant/citeAs",
    )
    
    # Additional metadata
    keywords: List[str] = Field(
        default_factory=list,
        description="Keywords or tags describing the dataset",
        alias="https://schema.org/keywords",
    )
    
    creator: Optional[str] = Field(
        default=None,
        description="Creator or author of the dataset",
        alias="https://schema.org/creator",
    )
    
    datePublished: Optional[str] = Field(
        default=None,
        description="Publication date of the dataset (ISO 8601 format)",
        alias="https://schema.org/datePublished",
    )
    
    dateModified: Optional[str] = Field(
        default=None,
        description="Last modification date of the dataset (ISO 8601 format)",
        alias="https://schema.org/dateModified",
    )
    
    # Provenance / extraction metadata (non-standard extension)
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
                    "https://w3id.org/mlentory/mlentory_graph/dataset/abc123",
                    "https://huggingface.co/datasets/squad",
                ],
                "name": "SQuAD",
                "url": "https://huggingface.co/datasets/squad",
                "description": "Stanford Question Answering Dataset (SQuAD) is a reading comprehension dataset...",
                "license": "https://creativecommons.org/licenses/by-sa/4.0/",
                "conformsTo": "http://mlcommons.org/croissant/1.0",
                "citeAs": "@article{rajpurkar2016squad,...}",
                "keywords": ["question-answering", "nlp"],
                "creator": "Stanford NLP",
                "datePublished": "2016-06-16",
            }
        },
    )

