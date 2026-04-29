"""
Metadata Service for ML Model Metadata.

This service generates JSON-LD metadata representations of ML models,
similar to the MetadataController but using Neo4j and Elasticsearch.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from rdflib.term import Literal

from api.services.graph_service import graph_service
from api.services.elasticsearch_service import elasticsearch_service
from api.services.model_service import model_service
from api.services.ro_crate_service import ro_crate_service

logger = logging.getLogger(__name__)


class MetadataService:
    """Service for generating JSON-LD metadata representations of ML models."""

    def __init__(self):
        """Initialize the metadata service."""
        self.graph_service = graph_service
        self.es_service = elasticsearch_service
        self.model_service = model_service
        self.ro_crate_service = ro_crate_service

    def get_metadata(self, model_id: str) -> Dict[str, Any]:
        """
        Retrieves metadata for a given model ID in JSON-LD format.

        Args:
            model_id: The ID of the model to search for (may include angle brackets or be compact)

        Returns:
            Dictionary containing the JSON-LD metadata of the model

        Raises:
            ValueError: If model not found
        """
        # Normalize model ID to full URI
        model_uri = self._normalize_model_uri(model_id)

        # Get model info from Neo4j and Elasticsearch
        model_info = self.ro_crate_service.get_model_info(model_uri)
        if not model_info:
            raise ValueError(f"Model not found: {model_id}")

        # Get IDs for metadata structure
        ro_crate_id, model_crate_id, metadata_id = self.ro_crate_service.get_ids(model_uri)
        hash_id = metadata_id.split("/")[-2]

        # Get source information
        source_info = self.ro_crate_service.get_model_source(model_info)

        # Build JSON-LD preamble
        jsonld_preamble = {
            "@context": {
                "@vocab": "https://schema.org",
                "fair4ml": "http://w3id.org/fair4ml/",
                "@dcterms": "http://purl.org/dc/terms/",
            },
            "@id": model_crate_id,
            "@type": "MLModel",
            **({"description": model_info.get("description")} if model_info.get("description") else {}),
            **({"license": model_info.get("license")} if model_info.get("license") else {}),
            **({"name": model_info.get("name")} if model_info.get("name") else {}),
            **({"author": model_info.get("author")} if model_info.get("author") else {}),
            **({"dateCreated": self._format_date(model_info.get("dateCreated"))} if model_info.get("dateCreated") else {}),
            **({"datePublished": self._format_date(model_info.get("datePublished"))} if model_info.get("datePublished") else {}),
            **({"dateModified": self._format_date(model_info.get("dateModified"))} if model_info.get("dateModified") else {}),
            **({"source": source_info} if source_info else {}),
            "url": [
                "https://mlentory.zbmed.de/mlentory_graph/" + hash_id,
                "https://mlentory.zbmed.de/mlentory_graph/" + hash_id + "/metadata.json",
            ]
        }

        # Properties to extract from entity history
        metadata_properties = [
            "coprightHolder", "funding", "archivedAt",
            "supportedLanguages", "inLanguage", "url", "citation",
            "conditionsOfAccess", "contributor", "maintainer",
            "version"
        ]

        # Extract keywords if not already present
        if "keywords" not in jsonld_preamble:
            keywords = self.ro_crate_service.extract_keywords(model_uri)
            if keywords:
                jsonld_preamble["keywords"] = list(keywords) if isinstance(keywords, set) else keywords

        # Get entity history and extract additional properties
        try:
            entity_history = self.model_service.get_model_full_history(model_uri)
            if entity_history:
                # Use the most recent version (first in list)
                latest_version = entity_history[0] if entity_history else {}
                
                for key, value in latest_version.items():
                    # Skip metadata and related_entities keys
                    if key in ["https://w3id.org/mlentory/mlentory_graph/meta/", "related_entities"]:
                        continue
                    
                    if key == "keywords":
                        # Keywords already handled above, but update if present in history
                        keywords = self.ro_crate_service.extract_keywords(model_uri)
                        if keywords:
                            jsonld_preamble["keywords"] = list(keywords) if isinstance(keywords, set) else keywords
                    elif key in metadata_properties:
                        if value and key not in jsonld_preamble:
                            if isinstance(value, list) and len(value) == 1:
                                jsonld_preamble[key] = value[0]
                            else:
                                jsonld_preamble[key] = value
        except Exception as e:
            logger.warning(f"Error retrieving entity history for {model_uri}: {e}")

        # Clean up null-like values
        jsonld_preamble = {
            property: value
            for property, value in jsonld_preamble.items()
            if not self._is_null_like(value)
        }

        return jsonld_preamble

    def _normalize_model_uri(self, model_id: str) -> str:
        """
        Normalize model ID to full URI format.

        Args:
            model_id: Model identifier (may include angle brackets or be compact)

        Returns:
            Full URI string
        """
        # Remove angle brackets if present
        if model_id.startswith("<") and model_id.endswith(">"):
            model_id = model_id[1:-1]

        # Add full URI prefix if not present
        if not model_id.startswith("https://"):
            return f"https://w3id.org/mlentory/mlentory_graph/{model_id}"
        
        return model_id

    def _format_date(self, date_value: Any) -> Optional[str]:
        """
        Format date value to YYYY-MM-DD format.

        Args:
            date_value: Date value (string, list, or other)

        Returns:
            Formatted date string or None
        """
        if not date_value:
            return None
        
        # Handle list values
        if isinstance(date_value, list):
            if len(date_value) == 0:
                return None
            date_value = date_value[0]
        
        # Convert to string
        date_str = str(date_value)
        
        # Extract date part (YYYY-MM-DD) if datetime string
        if "T" in date_str:
            return date_str.split("T")[0]
        
        # Return first 10 characters if available
        return date_str[:10] if len(date_str) >= 10 else date_str

    def _is_null_like(self, value: Any) -> bool:
        """
        Check if a value is null-like (None, empty string, or "Information not found").

        Args:
            value: Value to check

        Returns:
            True if value is null-like, False otherwise
        """
        if isinstance(value, Literal):
            value = str(value)
        if isinstance(value, list):
            return all(self._is_null_like(item) for item in value)
        return value in (None, "", "Information not found")


# Global service instance
metadata_service = MetadataService()

