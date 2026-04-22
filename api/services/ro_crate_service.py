"""
RO-Crate Service for ML Model Metadata.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from rdflib.util import from_n3
from rdflib import URIRef, Literal

from api.services.graph_service import graph_service
from api.services.elasticsearch_service import elasticsearch_service
from api.services.model_service import model_service

logger = logging.getLogger(__name__)


class RoCrateService:
    """Service for generating RO-Crate representations of ML models."""

    def __init__(self):
        """Initialize the RO-Crate service."""
        self.graph_service = graph_service
        self.es_service = elasticsearch_service
        self.model_service = model_service

    def create_crate(self, model_id: str) -> Dict[str, Any]:
        """
        Creates a json-ld object representing a detached RO-Crate
        with the ML model metadata.

        Args:
            model_id: The ID of the model to search for.

        Returns:
            Dictionary containing the RO-Crate JSON-LD structure
        """
        # Normalize model ID to full URI
        model_uri = self._normalize_model_uri(model_id)

        # Get model info from Neo4j
        model_info = self.get_model_info(model_uri)
        if not model_info:
            raise ValueError(f"Model not found: {model_id}")

        # Get last extraction date (from Neo4j metadata or use current date as fallback)
        last_extraction_date = self.get_last_extraction_date(model_uri)

        # Generate IDs
        ro_crate_id, model_crate_id, metadata_id = self.get_ids(model_uri)

        # Build RO-Crate structure
        ro_crate_graph = self.build_ro_crate_graph(ro_crate_id)
        ro_crate_metadata_descriptor = self.build_crate_metadata_descriptor(
            ro_crate_id, model_crate_id, model_info, last_extraction_date
        )
        model_metadata = self.build_model_metadata(model_crate_id, model_info)

        # Build hasPart relationships
        has_part_graph_nodes, has_part_ids = self.build_has_parts(model_info)

        # Add metadata file to hasPart
        model_metadata_file = self.build_model_metadata_file(
            metadata_id, model_info, last_extraction_date
        )
        has_part_graph_nodes.append(model_metadata_file)
        has_part_ids.append({"@id": model_metadata_file["@id"]})

        ro_crate_metadata_descriptor["hasPart"] = has_part_ids

        return {
            "@context": {
                "@vocab": "https://w3id.org/ro/crate/1.1/context",
                "fair4ml": "http://w3id.org/fair4ml/",
                "@dcterms": "http://purl.org/dc/terms/",
            },
            "@graph": [
                ro_crate_graph,
                ro_crate_metadata_descriptor,
                model_metadata,
                *has_part_graph_nodes,
            ],
        }

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
        logger.info(f"Model URI: {model_id}")
        return model_id

    def get_ids(self, model_uri: str) -> tuple[str, str, str]:
        """
        Generates the RO-Crate ID, model crate ID, and metadata ID based on the model URI.

        Args:
            model_uri: The full URI of the model

        Returns:
            Tuple containing (ro_crate_id, model_crate_id, metadata_id)
        """
        # Remove angle brackets if present
        clean_uri = model_uri.strip("<>")

        ro_crate_id = f"{clean_uri}/ro-crate-metadata.json"
        model_crate_id = clean_uri
        metadata_id = f"{clean_uri}/metadata.json"

        return ro_crate_id, model_crate_id, metadata_id

    def get_last_extraction_date(self, model_uri: str) -> str:
        """
        Retrieves the last extraction date for the given model.

        In Neo4j, we check for extraction metadata or use dateModified.
        Falls back to current date if not available.

        Args:
            model_uri: The full URI of the model

        Returns:
            ISO date string (YYYY-MM-DD)
        """
        try:
            # Get model metadata from graph service
            entity_data = self.graph_service._get_entity_data(model_uri)
            
            if entity_data:
                properties = entity_data.get("properties", {})
                
                # Try to get dateModified first
                date_modified = properties.get("schema__dateModified")
                if date_modified:
                    if isinstance(date_modified, list) and len(date_modified) > 0:
                        date_str = str(date_modified[0])
                    else:
                        date_str = str(date_modified)
                    # Extract date part (YYYY-MM-DD) if datetime string
                    if "T" in date_str:
                        return date_str.split("T")[0]
                    return date_str[:10] if len(date_str) >= 10 else date_str

                # Try dateCreated as fallback
                date_created = properties.get("schema__dateCreated")
                if date_created:
                    if isinstance(date_created, list) and len(date_created) > 0:
                        date_str = str(date_created[0])
                    else:
                        date_str = str(date_created)
                    if "T" in date_str:
                        return date_str.split("T")[0]
                    return date_str[:10] if len(date_str) >= 10 else date_str

        except Exception as e:
            logger.warning(f"Could not retrieve extraction date for {model_uri}: {e}")

        # Fallback to current date
        return datetime.now().strftime("%Y-%m-%d")

    def get_model_info(self, model_uri: str) -> Dict[str, Any]:
        """
        Retrieves the model information from Elasticsearch and Neo4j.
        
        Similar to the old SQL-based approach, this collects all properties
        from both Elasticsearch (base model data) and Neo4j (relationships).

        Args:
            model_uri: The full URI of the model

        Returns:
            Dictionary containing model information in flat format
        """
        info = {}
        
        try:
            # Get base model data from Elasticsearch
            es_model = self.es_service.get_model_by_id(model_uri)
            if es_model:
                if es_model.db_identifier:
                    # Use the MLentory ID if available, otherwise first identifier
                    mlentory_id = es_model.mlentory_id if es_model.mlentory_id != -1 else None
                    if mlentory_id:
                        info["identifier"] = mlentory_id
                    elif es_model.db_identifier:
                        info["identifier"] = es_model.db_identifier[0] if isinstance(es_model.db_identifier, list) else es_model.db_identifier
                
                if es_model.name:
                    info["name"] = es_model.name
                if es_model.description:
                    info["description"] = es_model.description
                if es_model.sharedBy:
                    info["sharedBy"] = es_model.sharedBy
                if es_model.license:
                    info["license"] = es_model.license
                if es_model.mlTask:
                    info["mlTask"] = es_model.mlTask
                if es_model.keywords:
                    info["keywords"] = es_model.keywords
                if es_model.platform:
                    info["platform"] = es_model.platform
                if es_model.datasets:
                    info["datasets"] = es_model.datasets
            
            # Get additional properties and relationships from Neo4j
            entity_data = self.graph_service._get_entity_data(model_uri)
            logger.info(f"Entity data from Neo4j: {entity_data}")
            
            if entity_data:
                properties = entity_data.get("properties", {})
                
                # Map Neo4j properties to expected format
                for key, value in properties.items():
                    # Skip type property
                    if key == "type":
                        continue
                    
                    # Extract simple property name (remove prefixes)
                    if "__" in key:
                        simple_key = key.split("__")[-1]
                    else:
                        simple_key = key
                    
                    # Convert list values appropriately
                    if isinstance(value, list):
                        if len(value) == 1:
                            # Single value - extract it
                            info[simple_key] = value[0]
                        elif len(value) > 1:
                            # Multiple values - keep as list
                            info[simple_key] = value
                        else:
                            continue
                    else:
                        info[simple_key] = value
            
            # Extract keywords from relationships
            if not info.get("keywords"):
                keywords = self.extract_keywords(model_uri)
                if keywords:
                    info["keywords"] = list(keywords) if isinstance(keywords, set) else keywords
            
            if not info:
                logger.warning(f"No model data found for {model_uri} in ES or Neo4j")
                return {}
            
            logger.info(f"Model info collected: {list(info.keys())}")
            return info

        except Exception as e:
            logger.error(f"Error retrieving model info for {model_uri}: {e}", exc_info=True)
            return {}

    def extract_keywords(self, model_uri: str) -> Set[str]:
        """
        Extract keywords (DefinedTerm entities) related to the model.

        Args:
            model_uri: The full URI of the model

        Returns:
            Set of keyword strings (lowercased)
        """
        keywords: Set[str] = set()

        try:
            # Get related entities for keywords
            entity_data = self.graph_service._get_entity_data(model_uri)
            
            if not entity_data:
                return keywords

            properties = entity_data.get("properties", {})
            
            # Get keywords from schema__keywords relationship
            keyword_uris = properties.get("schema__keywords", [])
            if not keyword_uris:
                return keywords

            # Fetch keyword entity details
            if isinstance(keyword_uris, str):
                keyword_uris = [keyword_uris]
            
            keyword_entities = self.graph_service.get_entities_properties_batch(
                entity_ids=list(keyword_uris),
                properties=["schema__name", "type"]
            )

            defined_term_uri = URIRef("https://schema.org/DefinedTerm")
            
            for keyword_uri, keyword_props in keyword_entities.items():
                # Check if it's a DefinedTerm type
                entity_types = keyword_props.get("type", [])
                if any("DefinedTerm" in str(t) for t in entity_types):
                    # Extract name
                    names = keyword_props.get("schema__name", [])
                    if not names:
                        names = keyword_props.get("name", [])
                    
                    for name in names:
                        if isinstance(name, (str, Literal)):
                            keywords.add(str(name).lower())

        except Exception as e:
            logger.warning(f"Error extracting keywords for {model_uri}: {e}")

        return keywords

    def get_model_source(self, info: Dict[str, Any]) -> Optional[str]:
        """
        Retrieves the data source information for the model.

        Args:
            info: Dictionary containing model information

        Returns:
            Source URI or None
        """
        url = info.get("url", "")
        if isinstance(url, list):
            url = url[0] if url else ""

        if "huggingface.co" in str(url):
            return "https://ror.org/02grspc61"
        elif "openml" in str(url):
            return "https://www.openml.org"
        elif "bioimage.io" in str(url):
            return "https://ai4life.eurobioimaging.eu"

        return None

    def build_ro_crate_graph(self, ro_crate_id: str) -> Dict[str, Any]:
        """
        Builds the base RO-Crate metadata graph.

        Args:
            ro_crate_id: The ID of the RO-Crate

        Returns:
            Dictionary representing the RO-Crate metadata graph
        """
        return {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": ro_crate_id},
        }

    def build_crate_metadata_descriptor(
        self, ro_crate_id: str, model_crate_id: str, info: Dict[str, Any], date: str
    ) -> Dict[str, Any]:
        """
        Builds the RO-Crate metadata descriptor.

        Args:
            ro_crate_id: The ID of the RO-Crate
            model_crate_id: The ID of the model crate
            info: Dictionary containing model information
            date: The last extraction date

        Returns:
            Dictionary representing the RO-Crate metadata descriptor
        """
        model_name = info.get("name", "Unknown Model")
        if isinstance(model_name, list):
            model_name = model_name[0] if model_name else "Unknown Model"

        model_url = info.get("url", "")
        if isinstance(model_url, list):
            model_url = model_url[0] if model_url else ""

        descriptor = {
            "@id": ro_crate_id,
            "@type": "Dataset",
            "name": f"RO-Crate for machine learning model: {model_name}",
            "description": f"This RO-Crate describes the metadata about the machine learning model: {model_name}",
            "license": {
                "@type": "CreativeWork",
                "@id": "http://spdx.org/licenses/CC-BY-4.0",
                "name": "Creative Commons Attribution 4.0 International",
                "alternateName": "CC BY 4.0",
                "url": "https://creativecommons.org/licenses/by/4.0/",
            },
            "sdPublisher": "https://ror.org/0259fwx54",
            "about": {"@id": model_crate_id},
            "hasPart": [],
        }

        # Add keywords if available
        keywords = info.get("keywords")
        if keywords:
            if isinstance(keywords, set):
                keywords = list(keywords)
            descriptor["keywords"] = keywords

        # Add datePublished if available
        date_published = info.get("datePublished")
        if date_published:
            if isinstance(date_published, list):
                date_published = date_published[0]
            date_str = str(date_published)
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            descriptor["datePublished"] = date_str[:10]

        return descriptor

    def build_model_metadata(self, model_crate_id: str, info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Builds the metadata for the machine learning model.

        Args:
            model_crate_id: The ID of the model crate
            info: Dictionary containing model information

        Returns:
            Dictionary representing the model metadata
        """
        metadata = {
            "@id": model_crate_id,
            "@type": "MLModel",
        }

        # Add description
        description = info.get("description")
        if description:
            if isinstance(description, list):
                description = description[0]
            metadata["description"] = description

        # Add license if available
        license_val = info.get("license")
        if license_val:
            if isinstance(license_val, list):
                license_val = license_val[0]
            metadata["license"] = license_val

        # Add keywords if available
        keywords = info.get("keywords")
        if keywords:
            if isinstance(keywords, set):
                keywords = list(keywords)
            metadata["keywords"] = keywords

        # Add source
        source = self.get_model_source(info)
        if source:
            metadata["source"] = source

        # Add standard properties
        for prop in [
            "name",
            "dateCreated",
            "dateModified",
            "datePublished",
            "archivedAt",
            "url",
        ]:
            if prop in info:
                value = info[prop]
                if isinstance(value, list):
                    value = value[0] if value else None
                if value:
                    # Format dates
                    if prop.startswith("date"):
                        date_str = str(value)
                        if "T" in date_str:
                            date_str = date_str.split("T")[0]
                        metadata[prop] = date_str[:10]
                    else:
                        metadata[prop] = value

        return metadata

    def build_has_parts(self, model_info: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Builds the related parts of the RO-Crate metadata.

        Currently returns empty lists as the original implementation was commented out.
        Can be extended to include datasets, articles, etc. in the future.

        Args:
            model_info: Dictionary containing model information

        Returns:
            Tuple of (has_part_graph_nodes, has_part_ids)
        """
        # TODO: Implement hasPart relationships for datasets, articles, etc.
        # This would require querying Neo4j for related entities
        return [], []

    def build_model_metadata_file(
        self, metadata_id: str, info: Dict[str, Any], date: str
    ) -> Dict[str, Any]:
        """
        Builds the metadata file for the machine learning model.

        Args:
            metadata_id: The ID of the metadata file
            info: Dictionary containing model information
            date: The last extraction date

        Returns:
            Dictionary representing the model metadata file
        """
        # Extract hash ID from metadata_id
        parts = metadata_id.split("/")
        hash_id = parts[-2] if len(parts) >= 2 else parts[-1].replace("/metadata.json", "")

        model_name = info.get("name", "Unknown Model")
        if isinstance(model_name, list):
            model_name = model_name[0] if model_name else "Unknown Model"

        return {
            "@id": metadata_id,
            "@type": "File",
            "name": f"Metadata for model: {model_name}",
            "description": f"This file contains the metadata for the machine learning model: {model_name}",
            "datePublished": str(date)[:10],
            "url": f"https://mlentory.zbmed.de/mlentory_graph/{hash_id}/metadata.json",
        }


# Global service instance
ro_crate_service = RoCrateService()

