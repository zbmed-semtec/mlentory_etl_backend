"""
API Response Schemas.

This module defines Pydantic models for all API responses. It reuses and extends
the existing FAIR4ML schema definitions to ensure consistency between the ETL
pipeline and the API layer.

Field Naming:
    We use camelCase for FAIR4ML-compliant fields (e.g., sharedBy, mlTask)
    to match the FAIR4ML specification and JSON-LD conventions.

Example:
    >>> from api.schemas.responses import ModelDetail, RelatedEntities
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
    ...     related_entities=RelatedEntities(
    ...         license=LicenseEntity(uri="...", name="Apache-2.0")
    ...     )
    ... )
"""

from __future__ import annotations

from typing import Generic, List, Optional, TypeVar
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


class LicenseEntity(BaseModel):
    """License entity information."""

    uri: str = Field(description="License URI")
    name: Optional[str] = Field(description="License name", default=None)
    url: Optional[str] = Field(description="License URL", default=None)


class DatasetEntity(BaseModel):
    """Dataset entity information."""

    uri: str = Field(description="Dataset URI")
    name: Optional[str] = Field(description="Dataset name", default=None)
    description: Optional[str] = Field(description="Dataset description", default=None)
    url: Optional[str] = Field(description="Dataset URL", default=None)


class ArticleEntity(BaseModel):
    """Scholarly article entity information."""

    uri: str = Field(description="Article URI")
    title: Optional[str] = Field(description="Article title", default=None)
    authors: List[str] = Field(description="Article authors", default_factory=list)
    publication_date: Optional[str] = Field(description="Publication date", default=None)
    url: Optional[str] = Field(description="Article URL", default=None)


class KeywordEntity(BaseModel):
    """Keyword/tag entity information."""

    uri: str = Field(description="Keyword URI")
    name: str = Field(description="Keyword name")
    description: Optional[str] = Field(description="Keyword description", default=None)


class TaskEntity(BaseModel):
    """ML task entity information."""

    uri: str = Field(description="Task URI")
    name: str = Field(description="Task name")
    description: Optional[str] = Field(description="Task description", default=None)


class LanguageEntity(BaseModel):
    """Language entity information."""

    uri: str = Field(description="Language URI")
    name: str = Field(description="Language name")
    iso_code: Optional[str] = Field(description="ISO language code", default=None)


class RelatedEntities(BaseModel):
    """Container for related entities from Neo4j."""

    license: Optional[LicenseEntity] = Field(description="License information", default=None)
    datasets: List[DatasetEntity] = Field(description="Related datasets", default_factory=list)
    articles: List[ArticleEntity] = Field(description="Related scholarly articles", default_factory=list)
    keywords: List[KeywordEntity] = Field(description="Related keywords", default_factory=list)
    tasks: List[TaskEntity] = Field(description="Related ML tasks", default_factory=list)
    languages: List[LanguageEntity] = Field(description="Related languages", default_factory=list)


class ModelDetail(MLModel):
    """Extended model information with related entities from Neo4j."""

    # Add platform field (not in FAIR4ML schema)
    platform: Optional[str] = Field(
        description="Platform where model is hosted (e.g., 'Hugging Face')",
        default=None
    )

    # Related entities from Neo4j knowledge graph
    related_entities: RelatedEntities = Field(
        description="Related entities from knowledge graph",
        default_factory=RelatedEntities
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Service status")
    version: str = Field(description="API version")
    elasticsearch: bool = Field(description="Elasticsearch connection status")
    neo4j: bool = Field(description="Neo4j connection status")
