"""
Model Service Layer.

This module provides business logic for model-related operations,
consolidating common functionality used across multiple endpoints.
It orchestrates calls to Elasticsearch and Neo4j services to build
complete model responses.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from api.schemas.responses import ModelDetail, ModelListItem
from api.services.elasticsearch_service import elasticsearch_service
from api.services.graph_service import graph_service

logger = logging.getLogger(__name__)


class ModelService:
    """Service layer for ML model operations."""

    def __init__(self):
        """Initialize the model service."""
        self.es_service = elasticsearch_service
        self.graph_service = graph_service

    def _normalize_model_uri(self, model_id: str) -> str:
        """
        Convert compact model ID to full URI.

        Args:
            model_id: Model identifier (URI or compact ID)

        Returns:
            Full model URI
        """
        if not model_id.startswith("https://"):
            return f"https://w3id.org/mlentory/mlentory_graph/{model_id}"
        return model_id

    def _build_base_model_response(self, es_model: ModelListItem) -> ModelDetail:
        """
        Build base ModelDetail response from Elasticsearch data.

        Args:
            es_model: Model data from Elasticsearch

        Returns:
            ModelDetail with basic fields populated
        """
        return ModelDetail(
            identifier=es_model.db_identifier,
            name=es_model.name,
            description=es_model.description,
            sharedBy=es_model.sharedBy,
            license=es_model.license,
            mlTask=es_model.mlTask,
            keywords=es_model.keywords,
            platform=es_model.platform,
            related_entities={}
        )

    def _enrich_with_graph_properties(
        self,
        model_response: ModelDetail,
        model_node: Any,
        skip_metadata: bool = False
    ) -> None:
        """
        Enrich model response with properties from graph node.

        Args:
            model_response: ModelDetail to enrich
            model_node: Graph node containing properties
            skip_metadata: Whether to skip metadata fields
        """
        if not model_node:
            return

        for key, value in model_node.properties.items():
            # Skip metadata if requested
            if skip_metadata and key == "mlentory__meta":
                continue

            key_clean = key.split("__")[-1]
            if key_clean in model_response.__dict__:
                model_response.__setattr__(key_clean, value)

    def _build_related_entities(
        self,
        graph_data: Any,
        start_uri: str,
        model_response: ModelDetail,
        update_model_properties: bool = False
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build related entities dictionary from graph edges.

        Args:
            graph_data: Graph response containing nodes and edges
            start_uri: URI of the start node
            model_response: ModelDetail to optionally update with related entity URIs
            update_model_properties: Whether to update model properties with entity URIs

        Returns:
            Dictionary mapping relationship types to entity lists
        """
        nodes_map = {n.id: n for n in graph_data.nodes}
        related_entities: Dict[str, List[Dict[str, Any]]] = {}

        for edge in graph_data.edges:
            if edge.source == start_uri:
                rel_type = edge.type
                target_node = nodes_map.get(edge.target)

                if not target_node:
                    continue

                # Skip self-references
                if target_node.id == start_uri:
                    continue

                # Initialize relationship type list if needed
                if rel_type not in related_entities:
                    related_entities[rel_type] = []

                # Create entity dict from node properties + uri
                entity_dict = target_node.properties.copy()
                entity_dict["uri"] = target_node.id

                # Optionally update model response properties with entity URIs
                if update_model_properties:
                    property_name = rel_type.split("__")[1] if "__" in rel_type else rel_type

                    if hasattr(model_response, property_name):
                        current_val = getattr(model_response, property_name)
                        if isinstance(current_val, list):
                            if target_node.id not in current_val:
                                model_response.__setattr__(
                                    property_name,
                                    [*current_val, target_node.id]
                                )
                        else:
                            model_response.__setattr__(property_name, target_node.id)

                related_entities[rel_type].append(entity_dict)

        return related_entities

    def _build_alias_map(self) -> Dict[str, str]:
        """
        Build mapping from predicate IRIs to field names.

        Returns:
            Dictionary mapping alias URIs to field names
        """
        alias_map = {}
        for name, field in ModelDetail.model_fields.items():
            if field.alias:
                alias_map[field.alias] = name
        return alias_map

    def _attach_extraction_metadata(
        self,
        model_response: ModelDetail,
        model_uri: str
    ) -> None:
        """
        Fetch and attach extraction metadata to model response.

        Args:
            model_response: ModelDetail to enrich with metadata
            model_uri: Full URI of the model
        """
        # Fetch raw metadata from Neo4j
        raw_metadata = self.graph_service.get_model_metadata(model_uri)

        # Build alias map for predicate IRI -> field name mapping
        alias_map = self._build_alias_map()

        # Format metadata with field names instead of URIs where possible
        formatted_metadata = {}
        for predicate_iri, meta_item in raw_metadata.items():
            field_name = alias_map.get(predicate_iri)
            if field_name:
                formatted_metadata[field_name] = meta_item
            else:
                # Keep original URI if no mapping found
                formatted_metadata[predicate_iri] = meta_item

        model_response.extraction_metadata = formatted_metadata

    def get_model_detail(
        self,
        model_id: str,
        resolve_properties: Optional[List[str]] = None
    ) -> ModelDetail:
        """
        Get detailed model information with related entities.

        This is the standard detail endpoint that fetches model data from
        Elasticsearch and enriches it with related entities from Neo4j.

        Args:
            model_id: Model identifier (URI or compact ID)
            resolve_properties: Optional list of relationship types to resolve

        Returns:
            ModelDetail with basic info and related entities

        Raises:
            ValueError: If model not found
        """
        # 1. Normalize URI
        model_uri = self._normalize_model_uri(model_id)

        # 2. Get basic model info from Elasticsearch
        es_model = self.es_service.get_model_by_id(model_uri)
        if not es_model:
            raise ValueError(f"Model not found: {model_id}")

        # 3. Build base response
        model_response = self._build_base_model_response(es_model)

        # 4. Get related entities from Neo4j
        graph_data = self.graph_service.get_entity_graph(
            entity_id=model_uri,
            depth=2,
            relationships=resolve_properties,
            direction="outgoing",
            entity_label="MLModel",
        )

        # 5. Enrich with graph node properties
        nodes_map = {n.id: n for n in graph_data.nodes}
        start_uri = graph_data.metadata.get("start_uri")
        model_node = nodes_map.get(start_uri)

        self._enrich_with_graph_properties(model_response, model_node)

        # 6. Build related entities (with property updates)
        related_entities = self._build_related_entities(
            graph_data=graph_data,
            start_uri=start_uri,
            model_response=model_response,
            update_model_properties=True  # Update model properties with entity URIs
        )

        model_response.related_entities = related_entities

        return model_response

    def get_model_detail_with_metadata(self, model_id: str) -> ModelDetail:
        """
        Get detailed model information including extraction metadata.

        This endpoint extends the standard model detail view by including
        metadata about how each property was extracted (confidence, method, etc.).

        Args:
            model_id: Model identifier (URI or compact ID)

        Returns:
            ModelDetail with basic info, related entities, and extraction metadata

        Raises:
            ValueError: If model not found
        """
        # 1. Normalize URI
        model_uri = self._normalize_model_uri(model_id)

        # 2. Get basic model info from Elasticsearch
        es_model = self.es_service.get_model_by_id(model_uri)
        if not es_model:
            raise ValueError(f"Model not found: {model_id}")

        # 3. Build base response
        model_response = self._build_base_model_response(es_model)

        # 4. Get related entities from Neo4j (with default relationships)
        graph_data = self.graph_service.get_entity_graph(
            entity_id=model_uri,
            depth=1,
            relationships=None,  # Use default relationships
            direction="outgoing",
            entity_label="MLModel",
        )

        # 5. Enrich with graph node properties
        nodes_map = {n.id: n for n in graph_data.nodes}
        start_uri = graph_data.metadata.get("start_uri")
        model_node = nodes_map.get(start_uri)

        self._enrich_with_graph_properties(
            model_response,
            model_node,
            skip_metadata=True  # Skip metadata fields
        )

        # 6. Build related entities (with property updates)
        related_entities = self._build_related_entities(
            graph_data=graph_data,
            start_uri=start_uri,
            model_response=model_response,
            update_model_properties=True  # Keep property updates
        )

        model_response.related_entities = related_entities

        # 7. Attach extraction metadata
        self._attach_extraction_metadata(model_response, model_uri)

        return model_response

    def get_model_full_history(self, model_id: str) -> List[Dict[str, Any]]:
        """
        Get the full history of a model including all versions and metadata.

        Args:
            model_id: Model identifier (URI or compact ID)

        Returns:
            List of model state objects, sorted by date (newest first)
        """
        # 1. Normalize URI
        model_uri = self._normalize_model_uri(model_id)

        # 2. Fetch history from Graph Service
        raw_history = self.graph_service.get_model_history(model_uri)
        
        # 3. Process history into schema.org format with normalized keys
        alias_map = self._build_alias_map()
        processed_history = []
        
        for state in raw_history:
            # Extract relationship URIs before processing using graph service
            relationship_uris = self.graph_service.extract_related_entity_uris(state)

            # Build related entities by fetching entity details using graph service
            related_entities = self.graph_service.build_related_entities_from_uris(relationship_uris)

            processed_state = {
                "related_entities": related_entities
            }
            
            # Extract metadata separate from properties
            raw_metadata = state.pop("extraction_metadata", {})
            formatted_metadata = {}
            
            # Map properties and metadata to friendly names
            for predicate, values in state.items():
                # Map predicate to field name
                field_name = alias_map.get(predicate)
                
                # If we have a friendly name, use it
                key = field_name if field_name else predicate
                
                # Add to state (handling list vs scalar if needed, currently list from graph service)
                # The frontend expects lists for schema.org properties usually
                processed_state[key] = values
                
                # Handle corresponding metadata
                if predicate in raw_metadata:
                    formatted_metadata[key] = raw_metadata[predicate]
            
            # Add formatted metadata to the state
            # Note: We use the full URI for the metadata key as per requirement Option 1
            processed_state["https://w3id.org/mlentory/mlentory_graph/meta/"] = formatted_metadata
            
            processed_history.append(processed_state)
            
        return processed_history


# Global service instance
model_service = ModelService()

