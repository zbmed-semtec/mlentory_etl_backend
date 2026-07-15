"""
Structured bibliographic citations for MLModel (schema.org JSON-LD shape).

Stored as model-local literals under ``https://schema.org/citation``; RDF export
uses a single JSON string literal per model.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_ORG_CITATION = "https://schema.org/citation"


class CitationAuthor(BaseModel):
    """schema:Person or schema:Organization embedded in a citation."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    json_ld_type: Literal["Person", "Organization"] = Field(
        ...,
        alias="@type",
        description="schema.org class for the author entry",
    )
    name: str = Field(..., description="Author or organization display name")


class ModelCitationWork(BaseModel):
    """
    One cited creative work, aligned with schema.org CreativeWork-style JSON-LD.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    json_ld_type: Literal["CreativeWork"] = Field(
        default="CreativeWork",
        alias="@type",
        description="Fixed CreativeWork for this profile",
    )
    resource_id: Optional[str] = Field(
        default=None,
        alias="@id",
        description="Canonical PID when known (e.g. https://doi.org/10....)",
    )
    name: Optional[str] = Field(
        default=None,
        description="Title or name of the creative work when available",
    )
    author: List[CitationAuthor] = Field(
        default_factory=list,
        description="Ordered author list (Person or Organization)",
    )
    publicationDate: Optional[str] = Field(
        default=None,
        description="Publication date or year as ISO-like string when known",
    )
