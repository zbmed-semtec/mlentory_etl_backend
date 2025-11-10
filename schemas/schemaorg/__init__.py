"""
Schema.org entity schemas.

Pydantic models for schema.org entities with IRI aliases for RDF serialization.
"""

from .scholarly_article import ScholarlyArticle
from .creative_work import CreativeWork

__all__ = ["ScholarlyArticle", "CreativeWork"]

