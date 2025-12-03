"""
Graph Service for Variable-Depth Traversal.

This module provides the service layer for exploring the knowledge graph
starting from any entity. It uses Cypher queries to traverse the graph
up to a configurable depth and returns a structured graph response.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from api.config import get_neo4j_config
from api.schemas.graph import GraphEdge, GraphNode, GraphResponse
from etl_loaders.rdf_store import _run_cypher

logger = logging.getLogger(__name__)


class GraphService:
    """Service for generic graph exploration."""

    def __init__(self):
        """Initialize the Graph service."""
        self.config = get_neo4j_config()

        # Known URI prefixes used when minting identifiers (see LoadHelpers)
        self.entity_uri_prefixes: Dict[str, str] = {
            "MLModel": "model",
            "License": "license",
            "Dataset": "dataset",
            "DefinedTerm": "term",
            "ScholarlyArticle": "article",
            "Language": "language",
        }

        # Relationship sets grounded in the MLModel schema structure
        self.default_relationships: Dict[str, List[str]] = {
            "MLModel": [
                # License & provenance
                "schema__license",
                "fair4ml__fineTunedFrom",
                "fair4ml__mlTask",
                "schema__inLanguage",
                "schema__keywords",
                "codemeta__issueTracker",
                "codemeta__readme",
                "schema__archivedAt",
                "schema__discussionUrl",
                "schema__url",
                "schema__identifier",
                "fair4ml__evaluatedOn",
                "fair4ml__validatedOn",
                "fair4ml__testedOn",
                "fair4ml__trainedOn",
                "codemeta__referencePublication",
                "fair4ml__sharedBy",
                "schema__author",
                "fair4ml__modelCategory",
            ]
        }

    def get_entity_graph(
        self,
        entity_id: str,
        depth: int = 1,
        relationships: Optional[List[str]] = None,
        direction: str = "both",
        entity_label: Optional[str] = None,
    ) -> GraphResponse:
        """
        Fetch a subgraph starting from a specific entity.

        Refactored to a 2-step approach using a helper for single-entity retrieval:
        1. Fetch the main entity (properties + allowed relations).
        2. Iterate over the neighbors found in step 1 and fetch their full details (properties + all relations).

        Args:
            entity_id: Compact alphanumeric identifier of the starting entity (no scheme).
            depth: Traversal depth (Currently supports 1 for direct neighbors).
            relationships: Optional list of relationship types to follow
                (e.g., ["schema__license", "fair4ml__trainedOn"]).
            direction: Traversal direction (Ignored in this version, defaults to outgoing for properties).
            entity_label: Optional Neo4j label for the start node
                (e.g., "MLModel").

        Returns:
            GraphResponse containing nodes and edges.
        """
        # Reconstruct full URI from compact ID when possible
        entity_uri = self._build_entity_uri(entity_id)

        # If no relationships provided, choose sensible defaults per entity type
        if not relationships and entity_label:
            relationships = self.default_relationships.get(entity_label, [])

        try:
            # --- STEP 1: Main Entity ---
            # Fetch details for the start node, respecting the allowed relationships
            start_data = self._get_entity_data(entity_uri, relationships)

            if not start_data:
                return GraphResponse(nodes=[], edges=[], metadata={"error": "Entity not found"})

            graph_nodes: List[GraphNode] = []
            graph_edges: List[GraphEdge] = []
            seen_nodes: Set[str] = set()

            # Add start node
            start_node = GraphNode(
                id=start_data["id"],
                labels=start_data.get("labels", []),
                properties=start_data.get("properties", {}),
            )
            graph_nodes.append(start_node)
            seen_nodes.add(start_data["id"])

            # Add edges from start node
            for edge_data in start_data.get("edges", []):
                edge = GraphEdge(
                    id=edge_data["id"],
                    source=edge_data["source"],
                    target=edge_data["target"],
                    type=edge_data["type"],
                    properties=edge_data["props"] or {},
                )
                graph_edges.append(edge)

            # --- STEP 2: Neighbors ---
            neighbor_uris = start_data.get("neighbor_uris", [])
            
            for neighbor_uri in neighbor_uris:
                # Fetch details for neighbor, NO restrictions on relationships
                neighbor_data = self._get_entity_data(neighbor_uri, allowed_relationships=None)
                
                if not neighbor_data:
                    continue
                    
                nid = neighbor_data["id"]
                if nid in seen_nodes:
                    continue
                
                neighbor_node = GraphNode(
                    id=nid,
                    labels=neighbor_data.get("labels", []),
                    properties=neighbor_data.get("properties", {}),
                )
                graph_nodes.append(neighbor_node)
                seen_nodes.add(nid)
                
                # Note: We do NOT add edges from neighbors to other nodes here, 
                # keeping the graph focused on the start node's immediate context (Depth 1).
                # However, the neighbor_node.properties contains all its relations as keys.

            return GraphResponse(
                nodes=graph_nodes,
                edges=graph_edges,
                metadata={
                    "start_uri": entity_uri,
                    "depth": 1,
                    "node_count": len(graph_nodes),
                    "edge_count": len(graph_edges),
                    "relationships": relationships or [],
                    "entity_label": entity_label,
                    "strategy": "2-step-loop"
                },
            )

        except Exception as e:
            logger.error(f"Error traversing graph for {entity_uri}: {e}", exc_info=True)
            return GraphResponse(nodes=[], edges=[], metadata={"error": str(e)})

    def _get_entity_data(
        self,
        uri: str,
        allowed_relationships: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch all properties and relations for a single entity.
        
        Internal properties and external relations are treated as 'properties' of the model.
        
        Args:
            uri: The full URI of the entity.
            allowed_relationships: If provided, only these relationship types are fetched.
                                   If None, all outgoing relationships are fetched.
                                   
        Returns:
            Dict containing:
              - id: Node ID (URI or elementId)
              - labels: List of labels
              - properties: Dict of properties (including relations as key=[targets])
              - edges: List of edge dicts (id, source, target, type, props)
              - neighbor_uris: List of distinct target URIs
            Returns None if entity not found.
        """
        # 1. Get Node Properties
        # We use OPTIONAL MATCH or just MATCH. If node exists, we want it.
        props_query = """
        MATCH (n {uri: $uri})
        RETURN 
            coalesce(n.uri, elementId(n)) as id,
            labels(n) as labels,
            properties(n) as props
        """
        props_res = _run_cypher(props_query, {"uri": uri}, self.config)
        
        if not props_res:
            return None
            
        node_record = props_res[0]
        node_id = node_record.get("id")
        labels = node_record.get("labels", [])
        raw_props = node_record.get("props", {})
        
        # Normalize properties to List[str] or strict types
        # User requested "internal properties... treated as 'properties'"
        normalized_props = {}
        for k, v in raw_props.items():
            if v is None:
                continue
            if isinstance(v, list):
                normalized_props[k] = [str(x) for x in v if x is not None]
            else:
                normalized_props[k] = [str(v)]
                
        # 2. Get Relations (treated as properties + explicit edges)
        # If allowed_relationships is set, we filter.
        
        # Build dynamic WHERE clause for relationships
        rel_filter = ""
        params = {"uri": uri}
        
        if allowed_relationships is not None:
            # Pass valid relationships as parameter
            params["rels"] = allowed_relationships
            rel_filter = "AND type(r) IN $rels"
        
        rels_query = f"""
        MATCH (n {{uri: $uri}})-[r]->(m)
        WHERE 1=1 {rel_filter}
        RETURN 
            type(r) as type,
            coalesce(m.uri, elementId(m)) as target_uri,
            elementId(r) as edge_id,
            properties(r) as edge_props
        """
        
        rels_res = _run_cypher(rels_query, params, self.config)
        
        edges = []
        neighbor_uris = []
        
        for row in rels_res:
            rtype = row["type"]
            target = row["target_uri"]
            edge_id = row["edge_id"]
            edge_props = row["edge_props"]
            
            # Add relation to normalized properties
            if rtype not in normalized_props:
                normalized_props[rtype] = []
            # Avoid duplicates in property list if multiple edges of same type point to same target
            if target not in normalized_props[rtype]:
                normalized_props[rtype].append(target)
            
            neighbor_uris.append(target)
            
            edges.append({
                "id": edge_id,
                "source": uri,
                "target": target,
                "type": rtype,
                "props": edge_props
            })
            
        return {
            "id": node_id,
            "labels": labels,
            "properties": normalized_props,
            "edges": edges,
            "neighbor_uris": list(set(neighbor_uris))
        }

    def get_entities_properties_batch(
        self,
        entity_ids: List[str],
        properties: Optional[List[str]] = None
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Fetch properties for multiple entities in a single batch query.

        Args:
            entity_ids: List of entity URIs or IDs. Angle brackets will be stripped.
            properties: Optional list of specific properties to fetch.
                        If None/empty, fetches all properties.

        Returns:
            Dictionary mapping Entity URI -> { Property Name -> List[Values] }
        """
        if not entity_ids:
            return {}

        # Clean IDs (strip <>)
        clean_ids = [
            eid.strip("<>") if eid.strip().startswith("<") and eid.strip().endswith(">") else eid.strip()
            for eid in entity_ids
        ]

        # Determine what to return
        if properties:
            # Return specific properties
            # We construct a map projection in Cypher
            # properties are typically single values or lists in Neo4j.
            # We need to ensure everything is a list of strings for the response format.
            
            # Sanitize property names to simple alphanumeric to avoid injection
            safe_props = [p for p in properties if p.isalnum() or p.replace("_","").replace(".","").isalnum()]
            
            if not safe_props:
                # Fallback to returning all properties if sanitization removed everything
                return_clause = "properties(n)"
            else:
                # Construct map projection: {prop1: n.prop1, prop2: n.prop2}
                # Note: If a property doesn't exist on a node, it returns null
                projection_items = [f"{p}: n.{p}" for p in safe_props]
                return_clause = f"{{{', '.join(projection_items)}}}"
        else:
            # Return all properties
            return_clause = "properties(n)"

        props_query = f"""
        UNWIND $uris as uri
        MATCH (n {{uri: uri}})-[r]->(m)
        RETURN n.uri as uri, {return_clause} as props
        """
        
        rels_query = f"""
        UNWIND $uris AS uri
        MATCH (n {{uri: uri}})-[r]->(m)
        RETURN
          n.uri AS uri,
          type(r) AS rel_type,
          collect(DISTINCT m.uri) AS targets
        """
        
        response_data = {}

        try:
            results = _run_cypher(props_query, {"uris": clean_ids}, self.config)
            for record in results:
                uri = record.get("uri")
                props_raw = record.get("props", {})
                relationships_raw = record.get("relationships", {})
                logger.info("\n--------------------------------\n")
                logger.info(f"Record: {record}")
                logger.info("\n--------------------------------\n")
                targets_uri = record.get("targets_uri", {})
                
                if not uri:
                    continue
                    
                # Normalize values to List[str]
                normalized_props = {}
                for key, val in props_raw.items():
                    if val is None:
                        continue
                    if isinstance(val, list):
                        normalized_props[key] = [str(v) for v in val if v is not None]
                    else:
                        normalized_props[key] = [str(val)]
                
                response_data[uri] = normalized_props
            
            results = _run_cypher(rels_query, {"uris": clean_ids}, self.config)
            for record in results:
                uri = record.get("uri")
                rel_type = record.get("rel_type")
                targets = record.get("targets") or []
                if not uri:
                    continue
                
                if uri in response_data:
                    response_data[uri][rel_type] = targets
            
            return response_data

        except Exception as e:
            logger.error(f"Error fetching batch properties: {e}", exc_info=True)
            return {}

    def get_related_entities(
        self,
        entity_ids: List[str]
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Fetch related entities for the given entity IDs using the _get_entity_data helper.
        
        This method uses the same logic as get_entity_graph but returns data in a 
        flattened format suitable for frontend consumption.
        
        Args:
            entity_ids: List of entity URIs or compact IDs.
            
        Returns:
            Dictionary mapping Entity URI -> { Property/Relationship Name -> List[Values] }
        """
        if not entity_ids:
            return {}
        
        result = {}
        
        for entity_id in entity_ids:
            # Build full URI
            entity_uri = self._build_entity_uri(entity_id)
            
            # Fetch entity data without relationship restrictions
            entity_data = self._get_entity_data(entity_uri, allowed_relationships=None)
            
            if entity_data:
                # Use the properties dict which includes both internal props and relations
                result[entity_uri] = entity_data.get("properties", {})
            
            # Get the info of 
        
        return result

    def _build_entity_uri(self, entity_id: str) -> str:
        """
        Reconstruct the full entity URI from the compact identifier.

        Args:
            entity_id: The identifier fragment provided by the client.

        Returns:
            Full URI string.
        """
        if entity_id.startswith(("http://", "https://")):
            return entity_id
        
        return f"https://w3id.org/mlentory/mlentory_graph/{entity_id}"


# Global service instance
graph_service = GraphService()
