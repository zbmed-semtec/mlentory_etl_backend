"""
Neo4j Service for Related Entity Queries.
Example:
    >>> from api.services.neo4j_service import neo4j_service
    >>> 
    >>> # Fetch specific entities for a model
    >>> entities = neo4j_service.get_related_entities(
    ...     model_uri="https://w3id.org/mlentory/model/abc123",
    ...     entities=["license", "datasets", "articles"]
    ... )
    >>> 
    >>> print(f"License: {entities.license.name}")
    >>> print(f"Datasets: {len(entities.datasets)}")
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from api.config import get_neo4j_config
from api.schemas.responses import (
    ArticleEntity,
    DatasetEntity,
    KeywordEntity,
    LanguageEntity,
    LicenseEntity,
    RelatedEntities,
    TaskEntity,
)
from etl_loaders.rdf_store import _run_cypher

logger = logging.getLogger(__name__)


class Neo4jService:
    """Service for querying related entities in Neo4j."""

    def __init__(self):
        """Initialize the Neo4j service."""
        self.config = get_neo4j_config()

    def get_related_entities(self, model_uri: str, entities: List[str]) -> RelatedEntities:
        """
        Fetch related entities for a model from Neo4j.

        Args:
            model_uri: URI of the model
            entities: List of entity types to fetch (e.g., ['license', 'datasets'])

        Returns:
            RelatedEntities object with requested entities populated
        """
        related = RelatedEntities()

        # Fetch each requested entity type
        for entity_type in entities:
            if entity_type == "license":
                related.license = self._get_license(model_uri)
            elif entity_type == "datasets":
                related.datasets = self._get_datasets(model_uri)
            elif entity_type == "articles":
                related.articles = self._get_articles(model_uri)
            elif entity_type == "keywords":
                related.keywords = self._get_keywords(model_uri)
            elif entity_type == "tasks":
                related.tasks = self._get_tasks(model_uri)
            elif entity_type == "languages":
                related.languages = self._get_languages(model_uri)

        return related

    def _get_license(self, model_uri: str) -> Optional[LicenseEntity]:
        """Get license information for a model."""
        query = """
        MATCH (m:MLModel {uri: $model_uri})-[:HAS_LICENSE|:license]->(l:License)
        RETURN l.uri as uri, l.name as name, l.url as url
        LIMIT 1
        """
        results = _run_cypher(query, {"model_uri": model_uri}, self.config)
        if results:
            result = results[0]
            return LicenseEntity(
                uri=result.get("uri", ""),
                name=result.get("name"),
                url=result.get("url"),
            )
        return None

    def _get_datasets(self, model_uri: str) -> List[DatasetEntity]:
        """Get datasets related to a model."""
        query = """
        MATCH (m:MLModel {uri: $model_uri})-[:USES_DATASET|:dataset|:trainingData]->(d:Dataset)
        RETURN DISTINCT d.uri as uri, d.name as name, d.description as description, d.url as url
        """
        results = _run_cypher(query, {"model_uri": model_uri}, self.config)
        return [
            DatasetEntity(
                uri=result.get("uri", ""),
                name=result.get("name"),
                description=result.get("description"),
                url=result.get("url"),
            )
            for result in results
        ]

    def _get_articles(self, model_uri: str) -> List[ArticleEntity]:
        """Get scholarly articles related to a model."""
        query = """
        MATCH (m:MLModel {uri: $model_uri})-[:CITED_IN|:mentions|:describedBy]->(a:ScholarlyArticle)
        RETURN DISTINCT a.uri as uri, a.title as title, a.author as authors,
                        a.publicationDate as publication_date, a.url as url
        """
        results = _run_cypher(query, {"model_uri": model_uri}, self.config)
        articles = []
        for result in results:
            # Handle authors - could be a list or single value
            authors_raw = result.get("authors", [])
            if isinstance(authors_raw, str):
                authors = [authors_raw]
            elif isinstance(authors_raw, list):
                authors = authors_raw
            else:
                authors = []

            articles.append(
                ArticleEntity(
                    uri=result.get("uri", ""),
                    title=result.get("title"),
                    authors=authors,
                    publication_date=result.get("publication_date"),
                    url=result.get("url"),
                )
            )
        return articles

    def _get_keywords(self, model_uri: str) -> List[KeywordEntity]:
        """Get keywords/tags related to a model."""
        query = """
        MATCH (m:MLModel {uri: $model_uri})-[:HAS_KEYWORD|:keyword|:tag]->(k:DefinedTerm)
        RETURN DISTINCT k.uri as uri, k.name as name, k.description as description
        """
        results = _run_cypher(query, {"model_uri": model_uri}, self.config)
        return [
            KeywordEntity(
                uri=result.get("uri", ""),
                name=result.get("name", ""),
                description=result.get("description"),
            )
            for result in results
        ]

    def _get_tasks(self, model_uri: str) -> List[TaskEntity]:
        """Get ML tasks related to a model."""
        query = """
        MATCH (m:MLModel {uri: $model_uri})-[:PERFORMS_TASK|:mlTask|:applicationArea]->(t:DefinedTerm)
        WHERE t.type = 'MLTask' OR t.termCode =~ '.*task.*'
        RETURN DISTINCT t.uri as uri, t.name as name, t.description as description
        """
        results = _run_cypher(query, {"model_uri": model_uri}, self.config)
        return [
            TaskEntity(
                uri=result.get("uri", ""),
                name=result.get("name", ""),
                description=result.get("description"),
            )
            for result in results
        ]

    def _get_languages(self, model_uri: str) -> List[LanguageEntity]:
        """Get languages related to a model."""
        query = """
        MATCH (m:MLModel {uri: $model_uri})-[:SUPPORTS_LANGUAGE|:language|:inLanguage]->(l:Language)
        RETURN DISTINCT l.uri as uri, l.name as name, l.isoCode as iso_code
        """
        results = _run_cypher(query, {"model_uri": model_uri}, self.config)
        return [
            LanguageEntity(
                uri=result.get("uri", ""),
                name=result.get("name", ""),
                iso_code=result.get("iso_code"),
            )
            for result in results
        ]


# Global service instance
neo4j_service = Neo4jService()
