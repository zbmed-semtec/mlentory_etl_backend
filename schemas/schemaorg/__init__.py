"""
Schema.org entity schemas.

Pydantic models for schema.org entities with IRI aliases for RDF serialization.
"""

from .scholarly_article import ScholarlyArticle
from .creative_work import CreativeWork
from .defined_term import DefinedTerm
from .language import Language

__all__ = ["ScholarlyArticle", "CreativeWork", "DefinedTerm", "Language"]

