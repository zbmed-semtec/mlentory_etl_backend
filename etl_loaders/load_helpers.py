"""
Load Helpers.

Common utilities for loading and processing MLModel data across different loaders.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict
from urllib.parse import urlparse


class LoadHelpers:
    """Common utilities for loading and processing MLModel data."""

    @staticmethod
    def is_iri(value: str) -> bool:
        """
        Check if a string is a valid IRI.

        Args:
            value: String to check

        Returns:
            True if value is a valid IRI, False otherwise
        """
        if not value or not isinstance(value, str):
            return False

        try:
            result = urlparse(value)
            # Check if it has a scheme (http, https, etc.) and netloc (domain)
            return bool(result.scheme and result.netloc)
        except Exception:
            return False

    @staticmethod
    def _strip_angle_brackets(value: str) -> str:
        """Return value without surrounding angle brackets if present."""
        if isinstance(value, str) and value.startswith("<") and value.endswith(">"):
            return value[1:-1]
        return value

    @staticmethod
    def mint_subject_generic(
        entity: Dict[str, Any],
        kind: str,
        identifier_predicate: str = "https://schema.org/identifier",
        url_predicate: str = "https://schema.org/url",
        mlentory_graph_prefix: str = "https://w3id.org/mlentory/mlentory_graph/",
    ) -> str:
        """
        Mint a subject IRI for an entity with consistent, centralized logic.

        Preference order:
          1) An identifier that is an MLentory graph IRI (starts with mlentory_graph/).
          2) Any other valid IRI from the identifiers list.
          3) Hash-based IRI derived from the URL predicate.
          4) Fallback hash-based IRI derived from the full payload.

        Args:
            entity: Entity payload
            kind: Kind label used in minted fallback IRIs (e.g., "model")
            identifier_predicate: Predicate for identifiers
            url_predicate: Predicate for the canonical URL
            mlentory_graph_prefix: MLentory IRI prefix to prioritize

        Returns:
            Subject IRI as a string
        """
        identifiers = entity.get(identifier_predicate, [])
        if isinstance(identifiers, str):
            identifiers = [identifiers]

        # Prefer MLentory IRIs
        if identifiers and isinstance(identifiers, list):
            for identifier in identifiers:
                normalized = LoadHelpers._strip_angle_brackets(identifier)
                if isinstance(normalized, str) and normalized.startswith(mlentory_graph_prefix):
                    return normalized
            # Otherwise any valid IRI
            for identifier in identifiers:
                normalized = LoadHelpers._strip_angle_brackets(identifier)
                if LoadHelpers.is_iri(normalized):
                    return normalized

        # Fallback: mint IRI from URL
        url = entity.get(url_predicate, "")
        if isinstance(url, str) and url:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            return f"https://w3id.org/mlentory/{kind}/{url_hash}"

        # Ultimate fallback: hash of entire payload
        payload_hash = hashlib.sha256(str(entity).encode()).hexdigest()
        return f"https://w3id.org/mlentory/{kind}/{payload_hash}"

    @staticmethod
    def mint_subject(model: Dict[str, Any]) -> str:
        """
        Mint a subject IRI for a model.

        Uses centralized logic shared across entity types.

        Args:
            model: Model dictionary with identifier/name fields

        Returns:
            Subject IRI as a string
        """
        return LoadHelpers.mint_subject_generic(
            entity=model,
            kind="model",
            identifier_predicate="https://schema.org/identifier",
            url_predicate="https://schema.org/url",
            mlentory_graph_prefix="https://w3id.org/mlentory/mlentory_graph/",
        )

    @staticmethod
    def mint_article_subject(article: Dict[str, Any]) -> str:
        """
        Mint a subject IRI for a scholarly article.

        Uses centralized logic shared across entity types.

        Args:
            article: Article dictionary with identifier/name fields

        Returns:
            Subject IRI as a string
        """
        return LoadHelpers.mint_subject_generic(
            entity=article,
            kind="article",
            identifier_predicate="https://schema.org/identifier",
            url_predicate="https://schema.org/url",
            mlentory_graph_prefix="https://w3id.org/mlentory/mlentory_graph/",
        )

    @staticmethod
    def mint_license_subject(license_data: Dict[str, Any]) -> str:
        """
        Mint a subject IRI for a CreativeWork license entity.

        Args:
            license_data: License dictionary with identifier/name fields

        Returns:
            Subject IRI as a string
        """
        return LoadHelpers.mint_subject_generic(
            entity=license_data,
            kind="license",
            identifier_predicate="https://schema.org/identifier",
            url_predicate="https://schema.org/url",
            mlentory_graph_prefix="https://w3id.org/mlentory/mlentory_graph/",
        )

    @staticmethod
    def mint_dataset_subject(dataset_data: Dict[str, Any]) -> str:
        """
        Mint a subject IRI for a Croissant Dataset entity.

        Uses centralized logic shared across entity types.

        Args:
            dataset_data: Dataset dictionary with identifier/name fields

        Returns:
            Subject IRI as a string
        """
        return LoadHelpers.mint_subject_generic(
            entity=dataset_data,
            kind="dataset",
            identifier_predicate="https://schema.org/identifier",
            url_predicate="https://schema.org/url",
            mlentory_graph_prefix="https://w3id.org/mlentory/mlentory_graph/",
        )

    @staticmethod
    def mint_defined_term_subject(term_data: Dict[str, Any]) -> str:
        """
        Mint a subject IRI for a DefinedTerm entity.

        Uses centralized logic shared across entity types.

        Args:
            term_data: Term dictionary with identifier/name fields

        Returns:
            Subject IRI as a string
        """
        return LoadHelpers.mint_subject_generic(
            entity=term_data,
            kind="term",
            identifier_predicate="https://schema.org/identifier",
            url_predicate="https://schema.org/url",
            mlentory_graph_prefix="https://w3id.org/mlentory/mlentory_graph/",
        )

    @staticmethod
    def mint_language_subject(language_data: Dict[str, Any]) -> str:
        """
        Mint a subject IRI for a Language entity.

        Uses centralized logic shared across entity types.

        Args:
            language_data: Language dictionary with identifier/name fields

        Returns:
            Subject IRI as a string
        """
        return LoadHelpers.mint_subject_generic(
            entity=language_data,
            kind="language",
            identifier_predicate="https://schema.org/identifier",
            url_predicate="https://schema.org/url",
            mlentory_graph_prefix="https://w3id.org/mlentory/mlentory_graph/",
        )
