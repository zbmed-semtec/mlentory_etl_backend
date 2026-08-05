"""
Graph Service for Variable-Depth Traversal.

This module provides the service layer for exploring the knowledge graph
starting from any entity. It uses Cypher queries to traverse the graph
up to a configurable depth and returns a structured graph response.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

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
                "fair4ml__baseModel",
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

        Loads the start node and its 1-hop neighborhood in a single Cypher
        query (model props, outgoing edges, neighbor props, and each
        neighbor's outgoing relation targets), then assembles GraphResponse
        in Python. Depth beyond 1 is not traversed.

        Args:
            entity_id: Compact alphanumeric identifier of the starting entity (no scheme).
            depth: Traversal depth (Currently supports 1 for direct neighbors).
            relationships: Optional list of relationship types to follow
                (e.g., ["schema__license", "fair4ml__evaluatedOn"]).
            direction: Traversal direction (Ignored in this version, defaults to outgoing for properties).
            entity_label: Optional Neo4j label for the start node
                (e.g., "MLModel").

        Returns:
            GraphResponse containing nodes and edges.
        """
        # depth>1 and direction are accepted for API compatibility but not applied yet
        _ = (depth, direction)

        entity_uri = self._build_entity_uri(entity_id)

        if not relationships and entity_label:
            relationships = self.default_relationships.get(entity_label, [])

        try:
            rows = self._fetch_entity_neighborhood(entity_uri, relationships)
            neo4j_query_count = 1

            if not rows:
                return GraphResponse(
                    nodes=[],
                    edges=[],
                    metadata={
                        "error": "Entity not found",
                        "neo4j_query_count": neo4j_query_count,
                    },
                )

            graph_nodes, graph_edges = self._assemble_neighborhood_graph(
                entity_uri, rows
            )

            logger.info(
                "get_entity_graph uri=%s neo4j_query_count=%s nodes=%s edges=%s",
                entity_uri,
                neo4j_query_count,
                len(graph_nodes),
                len(graph_edges),
            )

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
                    "strategy": "batched-1hop",
                    "neo4j_query_count": neo4j_query_count,
                },
            )

        except Exception as e:
            logger.error(f"Error traversing graph for {entity_uri}: {e}", exc_info=True)
            return GraphResponse(nodes=[], edges=[], metadata={"error": str(e)})

    def _fetch_entity_neighborhood(
        self,
        entity_uri: str,
        allowed_relationships: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        """
        Load start node + 1-hop neighbors (and neighbor outgoing targets) in one query.

        Returns one row per (start→neighbor edge × neighbor→target edge) combination.
        When the start node has no outgoing edges, a single row with null link fields
        is still returned so the start node can be assembled.
        """
        # Single round-trip: start node + allowed outgoing edges + neighbor
        # properties + each neighbor's outgoing targets (folded into props later).
        # WHERE on OPTIONAL MATCH nullifies non-matching optionals without
        # dropping the start-node row when there are no edges.
        query = """
        MATCH (m {uri: $uri})
        WHERE 'Resource' IN labels(m)
        OPTIONAL MATCH (m)-[r]->(n)
        WHERE $rels IS NULL OR type(r) IN $rels
        OPTIONAL MATCH (n)-[nr]->(nt)
        RETURN
            coalesce(m.uri, elementId(m)) AS m_id,
            labels(m) AS m_labels,
            properties(m) AS m_props,
            type(r) AS rel_type,
            elementId(r) AS edge_id,
            properties(r) AS edge_props,
            coalesce(n.uri, elementId(n)) AS n_id,
            labels(n) AS n_labels,
            properties(n) AS n_props,
            type(nr) AS n_rel_type,
            coalesce(nt.uri, elementId(nt)) AS n_rel_target
        """
        params: Dict[str, Any] = {
            "uri": entity_uri,
            "rels": allowed_relationships,
        }
        return _run_cypher(query, params, self.config)

    def _assemble_neighborhood_graph(
        self,
        entity_uri: str,
        rows: List[Dict[str, Any]],
    ) -> Tuple[List[GraphNode], List[GraphEdge]]:
        """Assemble GraphNode/GraphEdge lists from batched neighborhood rows."""
        first = rows[0]
        start_id = first.get("m_id") or entity_uri
        start_labels = first.get("m_labels") or []
        start_props = self._normalize_node_properties(
            first.get("m_props") or {}, start_labels
        )

        neighbor_props: Dict[str, Dict[str, Any]] = {}
        neighbor_labels: Dict[str, List[str]] = {}
        seen_edges: Set[str] = set()
        graph_edges: List[GraphEdge] = []

        for row in rows:
            rel_type = row.get("rel_type")
            n_id = row.get("n_id")
            if not rel_type or not n_id:
                continue

            # Fold start→neighbor relation into start node properties
            if rel_type not in start_props:
                start_props[rel_type] = []
            if n_id not in start_props[rel_type]:
                start_props[rel_type].append(n_id)

            edge_id = str(row.get("edge_id") or f"{start_id}|{rel_type}|{n_id}")
            if edge_id not in seen_edges:
                seen_edges.add(edge_id)
                graph_edges.append(
                    GraphEdge(
                        id=edge_id,
                        source=entity_uri,
                        target=n_id,
                        type=rel_type,
                        properties=row.get("edge_props") or {},
                    )
                )

            if n_id == entity_uri:
                continue

            if n_id not in neighbor_props:
                n_labels = row.get("n_labels") or []
                neighbor_labels[n_id] = n_labels
                neighbor_props[n_id] = self._normalize_node_properties(
                    row.get("n_props") or {}, n_labels
                )

            # Neighbor outgoing relations as properties (not as graph edges)
            n_rel_type = row.get("n_rel_type")
            n_rel_target = row.get("n_rel_target")
            if n_rel_type and n_rel_target:
                props = neighbor_props[n_id]
                if n_rel_type not in props:
                    props[n_rel_type] = []
                if n_rel_target not in props[n_rel_type]:
                    props[n_rel_type].append(n_rel_target)

        graph_nodes: List[GraphNode] = [
            GraphNode(id=start_id, labels=start_labels, properties=start_props)
        ]
        for nid, props in neighbor_props.items():
            graph_nodes.append(
                GraphNode(
                    id=nid,
                    labels=neighbor_labels.get(nid, []),
                    properties=props,
                )
            )

        return graph_nodes, graph_edges

    @staticmethod
    def _normalize_node_properties(
        raw_props: Dict[str, Any],
        labels: List[str],
    ) -> Dict[str, Any]:
        """Normalize Neo4j props to List[str] values and attach type from labels."""
        normalized: Dict[str, Any] = {}
        for k, v in raw_props.items():
            if v is None:
                continue
            if isinstance(v, list):
                normalized[k] = [str(x) for x in v if x is not None]
            else:
                normalized[k] = [str(v)]

        if labels:
            normalized["type"] = []
            for label in labels:
                if "__" in label:
                    normalized["type"].append(label)
            if len(labels) == 1 and labels[0] == "Resource":
                normalized["type"].append("schema__url")

        return normalized

    def _get_entity_data(
        self,
        uri: str,
        ignore_metadata: bool = True,
        allowed_relationships: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch all properties and relations for a single entity.
        
        Internal properties and external relations are treated as 'properties' of the model.
        
        Args:
            uri: The full URI of the entity.
            allowed_relationships: If provided, only these relationship types are fetched.
                                   If None, all outgoing relationships are fetched.
                                   
            ignore_metadata: If True, ignore metadata nodes.
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
        labels = []
        raw_props = {}
        
        for record in props_res:
            if ignore_metadata and "Resource" not in record.get("labels", []):
                continue
            labels.extend(record.get("labels", []))
            raw_props.update(record.get("props", {}))
        
        normalized_props = self._normalize_node_properties(raw_props, labels)

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

        # Use :Resource so Neo4j can hit the uri index (unlabeled MATCH scans and
        # dominated Extraction Info latency). Read node props without requiring an
        # outgoing edge — leaf URL nodes were previously dropped by that join.
        props_query = f"""
        UNWIND $uris AS uri
        MATCH (n:Resource {{uri: uri}})
        RETURN n.uri AS uri, {return_clause} AS props
        """

        rels_query = """
        UNWIND $uris AS uri
        MATCH (n:Resource {uri: uri})-[r]->(m)
        RETURN
          n.uri AS uri,
          type(r) AS rel_type,
          collect(DISTINCT m.uri) AS targets
        """

        response_data: Dict[str, Dict[str, List[str]]] = {}

        try:
            results = _run_cypher(props_query, {"uris": clean_ids}, self.config)
            for record in results:
                uri = record.get("uri")
                props_raw = record.get("props") or {}
                if not uri:
                    continue

                normalized_props: Dict[str, List[str]] = {}
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
                if not uri or not rel_type:
                    continue

                if uri not in response_data:
                    response_data[uri] = {}
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
        
        for entity_id in self._expand_entity_id_params(entity_ids):
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
        normalized = entity_id.strip()
        if normalized.startswith("<") and normalized.endswith(">"):
            normalized = normalized[1:-1].strip()

        if normalized.startswith(("http://", "https://")):
            return normalized

        return f"https://w3id.org/mlentory/mlentory_graph/{normalized}"

    def _expand_entity_id_params(self, entity_ids: List[str]) -> List[str]:
        """
        Normalize entity ID query params.

        Some reverse proxies collapse repeated ``entity_ids`` keys into a single
        comma-separated value; split those back into individual IDs.
        """
        expanded: List[str] = []
        for entity_id in entity_ids:
            if not entity_id:
                continue

            raw = entity_id.strip()
            if not raw:
                continue

            if "," in raw and ("mlentory_graph/" in raw or raw.startswith("http")):
                parts = [part.strip() for part in raw.split(",") if part.strip()]
                expanded.extend(parts)
            else:
                expanded.append(raw)

        # Preserve order while removing duplicates
        return list(dict.fromkeys(expanded))

    def find_entity_uri_by_name(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """
        Find entity URI by name (exact match, case-insensitive).
        
        Args:
            entity_name: The entity name to search for
            
        Returns:
            Dictionary with uri, name, and entity_types, or None if not found
        """
        query = """
        MATCH (e)
        WHERE toLower(e.schema__name) = toLower($searchValue)
        RETURN e.uri as uri,
            e.schema__name as name,
            labels(e) as entity_types
        LIMIT 1
        """
        
        try:
            results = _run_cypher(query, {"searchValue": entity_name}, self.config)
            if not results:
                return None
            
            record = results[0]
            return {
                "uri": record.get("uri"),
                "name": record.get("name"),
                "entity_types": record.get("entity_types", [])
            }
        except Exception as e:
            logger.error(f"Error finding entity URI by name '{entity_name}': {e}", exc_info=True)
            return None


    def get_models_by_entity_uri(self, entity_uri: str) -> List[Dict[str, Any]]:
        """
        Get all models related to an entity URI.
        
        Args:
            entity_uri: The entity URI to find related models for
            
        Returns:
            List of dictionaries containing model information and relationship types
        """
        query = """
        MATCH (e {uri: $entityURI})
        MATCH (m:fair4ml__MLModel)-[r]-(e)
        RETURN DISTINCT 
            m.uri as model_uri,
            m.schema__name as model_name,
            type(r) as relationship_type,
            properties(m) as model_properties
        ORDER BY m.schema__name
        """
        
        try:
            results = _run_cypher(query, {"entityURI": entity_uri}, self.config)

            models: List[Dict[str, Any]] = []
            for record in results:
                raw_props: Dict[str, Any] = record.get("model_properties", {}) or {}

                # Normalize Neo4j property values (including DateTime) into JSON‑serializable types
                normalized_props: Dict[str, Any] = {}
                for key, value in raw_props.items():
                    if value is None:
                        continue
                    # Collections – convert each element to string
                    if isinstance(value, (list, tuple, set)):
                        normalized_props[key] = [str(v) for v in value if v is not None]
                    # Scalar – convert to string to safely handle neo4j.time.DateTime and others
                    else:
                        normalized_props[key] = str(value)

                models.append(
                    {
                        "model_uri": record.get("model_uri"),
                        "model_name": record.get("model_name"),
                        "relationship_type": record.get("relationship_type"),
                        "model_properties": normalized_props,
                    }
                )

            return models
        except Exception as e:
            logger.error(
                f"Error getting models for entity URI '{entity_uri}': {e}",
                exc_info=True,
            )
            return []

    def grouped_facet_values(self, entity_type: List[str]) -> Tuple[Dict[str, List[str]], int]:
        """
        List all entities grouped by relationship type.
        
        Args:
            entity_type: List of relationship types to filter by
            
        Returns:
            Tuple of (grouped dictionary, total count) where dictionary maps
            normalized relationship keys -> list of entity names
        """

        def _normalize_relationship_key(rel_type: str) -> str:
            """
            Normalize relationship type to simplified key.
            
            Maps dataset-related types to "datasets" and removes prefixes.
            
            Args:
                rel_type: Original relationship type (e.g., "fair4ml__mlTask", "schema__keywords")
                
            Returns:
                Simplified key (e.g., "mlTask", "keywords", "datasets")
            """
            # Dataset-related relationship types
            dataset_types = {
                "fair4ml__baseModel",
                "fair4ml__evaluatedOn"
            }
            
            if rel_type in dataset_types:
                return "datasets"
            
            # Remove prefixes: "schema__" and "fair4ml__"
            if rel_type.startswith("schema__"):
                return rel_type.replace("schema__", "")
            elif rel_type.startswith("fair4ml__"):
                return rel_type.replace("fair4ml__", "")
            
            return rel_type

        query = """
        MATCH (m:fair4ml__MLModel)-[r]-(e)
        WHERE type(r) IN $entity_types
        RETURN DISTINCT
            m.fair4ml__sharedBy as shared_by,
            e.schema__name as entity_name,
            type(r) as relationship_type
        ORDER BY type(r), e.schema__name
        """

        try:
            results = _run_cypher(query, {"entity_types": entity_type}, self.config)
            count = len(results)
            
            # Group entities by normalized relationship type
            grouped: Dict[str, List[str]] = {}
            shared_by_values = set()
            
            for record in results:
                rel_type = record.get("relationship_type")
                entity_name = record.get("entity_name")
                shared_by = record.get("shared_by")
                
                # Collect unique shared_by values (handle both single values and lists)
                if shared_by:
                    if isinstance(shared_by, list):
                        for val in shared_by:
                            if val:
                                shared_by_values.add(str(val))
                    else:
                        shared_by_values.add(str(shared_by))
                
                if rel_type and entity_name:
                    # Normalize the relationship type key
                    normalized_key = _normalize_relationship_key(rel_type)
                    
                    if normalized_key not in grouped:
                        grouped[normalized_key] = []
                    # ensure uniqueness per key and entity_name is a string
                    entity_name_str = str(entity_name) if entity_name else None
                    if entity_name_str and entity_name_str not in grouped[normalized_key]:
                        grouped[normalized_key].append(entity_name_str)
            
            # Add shared_by as a new key with unique values (sorted strings)
            if shared_by_values:
                grouped["shared_by"] = sorted([str(v) for v in shared_by_values])
            
            return grouped, count
        except Exception as e:
            logger.error(f"Error listing entities: {e}", exc_info=True)
            return {}, 0

    def get_model_metadata(self, model_uri: str) -> Dict[str, Any]:
        """
        Fetch extraction metadata for a model's properties.
        
        Args:
            model_uri: The full URI of the model.
            
        Returns:
            Dict mapping property URIs to their metadata.
        """
        query = """
        MATCH (m {uri: $uri})-[r:HAS_PROPERTY_SNAPSHOT]->(s:MLModelPropertySnapshot)
        WHERE r.valid_to IS NULL
        RETURN 
            s.predicate_iri as predicate,
            s.extraction_method as method,
            s.confidence as confidence,
            s.notes as notes,
            r.valid_from as valid_from,
            r.valid_to as valid_to
        """
        
        try:
            results = _run_cypher(query, {"uri": model_uri}, self.config)
            
            metadata = {}
            for record in results:
                predicate = record.get("predicate")
                if not predicate:
                    continue
                    
                meta_item = {
                    "extraction_method": record.get("method"),
                    "confidence": record.get("confidence"),
                    "notes": record.get("notes"),
                }
                
                # Add valid_period if dates exist
                valid_from = record.get("valid_from")
                valid_to = record.get("valid_to")
                
                if valid_from or valid_to:
                    meta_item["valid_period"] = {
                        "from": str(valid_from) if valid_from else None,
                        "until": str(valid_to) if valid_to else None
                    }
                    
                metadata[predicate] = meta_item
                
            return metadata
            
        except Exception as e:
            logger.error(f"Error fetching metadata for {model_uri}: {e}", exc_info=True)
            return {}

    def get_model_history(self, model_uri: str) -> List[Dict[str, Any]]:
        """
        Fetch the full history of a model including all property versions and their metadata.
        
        This method retrieves all property snapshots (current and historical) for a model
        and reconstructs the state of the model at each distinct modification time.
        
        Args:
            model_uri: The full URI of the model.
            
        Returns:
            List of model states, sorted by dateModified (newest first).
        """
        query = """
        MATCH (m {uri: $uri})-[r:HAS_PROPERTY_SNAPSHOT]->(s:MLModelPropertySnapshot)
        RETURN 
            s.predicate_iri as predicate,
            s.value as value,
            s.value_uri as value_uri,
            s.extraction_method as method,
            s.confidence as confidence,
            s.notes as notes,
            r.valid_from as valid_from,
            r.valid_to as valid_to
        ORDER BY r.valid_from DESC
        """
        
        try:
            results = _run_cypher(query, {"uri": model_uri}, self.config)
            
            # 1. Collect all distinct time points (valid_from dates)
            # These represent the moments when the model state changed
            time_points = set()
            snapshots = []
            
            for record in results:
                valid_from = record.get("valid_from")
                if valid_from:
                    time_points.add(str(valid_from))
                
                # Normalize record for easier processing
                snapshot = {
                    "predicate": record.get("predicate"),
                    "value": record.get("value"),
                    "value_uri": record.get("value_uri"),
                    "metadata": {
                        "extraction_method": record.get("method"),
                        "confidence": record.get("confidence"),
                        "notes": record.get("notes"),
                        "valid_period": {
                            "from": str(valid_from) if valid_from else None,
                            "until": str(record.get("valid_to")) if record.get("valid_to") else None
                        }
                    },
                    "valid_from": str(valid_from) if valid_from else None,
                    "valid_to": str(record.get("valid_to")) if record.get("valid_to") else None
                }
                snapshots.append(snapshot)
                
            # Sort time points descending (newest first)
            sorted_time_points = sorted(list(time_points), reverse=True)
            
            history = []
            
            # 2. Reconstruct model state for each time point
            for timestamp in sorted_time_points:
                model_state = {
                    "dateModified": timestamp,
                    "extraction_metadata": {}
                }
                
                # Check which snapshots were valid at this timestamp
                for snap in snapshots:
                    # A snapshot is valid if:
                    # valid_from <= timestamp AND (valid_to is NULL OR valid_to > timestamp)
                    # Note: We use string comparison for ISO dates which works for standard format
                    
                    is_active = (snap["valid_from"] is None or snap["valid_from"] <= timestamp) and \
                                (snap["valid_to"] is None or snap["valid_to"] >= timestamp)
                                
                    if is_active:
                        predicate = snap["predicate"]
                        
                        # Handle value (scalar or URI)
                        # We collect values in a list to handle multi-valued properties
                        val = snap["value_uri"] if snap["value_uri"] else snap["value"]
                        
                        # Store property value
                        if predicate not in model_state:
                            model_state[predicate] = []
                        if val is not None and val not in model_state[predicate]:
                            model_state[predicate].append(val)
                            
                        # Store metadata
                        # We just overwrite metadata for the property (assuming uniform metadata for multi-values or last-win)
                        model_state["extraction_metadata"][predicate] = snap["metadata"]
                        
                history.append(model_state)
                
            return history
            
        except Exception as e:
            logger.error(f"Error fetching model history for {model_uri}: {e}", exc_info=True)
            return []

    def extract_related_entity_uris(
        self,
        state: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        Extract URIs from relationship properties in a state dict.

        Args:
            state: Dictionary containing property predicates and values

        Returns:
            Dictionary mapping relationship types to lists of entity URIs
        """
        relationship_uris: Dict[str, List[str]] = {}

        for predicate, values in state.items():
            # Process values - look for URIs
            if not isinstance(values, list):
                values = [values]

            uris = []
            for val in values:
                if isinstance(val, str) and val.startswith("https://"):
                    uris.append(val)

            if uris:
                relationship_uris[predicate] = uris

        return relationship_uris

    def build_related_entities_from_uris(
        self,
        relationship_uris: Dict[str, List[str]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Build related entities dictionary by fetching entity details from the graph.

        Args:
            relationship_uris: Dictionary mapping relationship types to entity URIs

        Returns:
            Dictionary mapping relationship types to entity detail lists
        """
        if not relationship_uris:
            return {}

        # Collect all unique URIs for batch fetch
        all_uris = set()
        for uris in relationship_uris.values():
            all_uris.update(uris)

        if not all_uris:
            return {}

        # Fetch entity properties in batch
        entity_properties = self.get_entities_properties_batch(
            entity_ids=list(all_uris),
            properties=None  # Fetch all properties
        )

        # Build related entities structure
        related_entities: Dict[str, List[Dict[str, Any]]] = {}

        for rel_type, uris in relationship_uris.items():
            related_entities[rel_type] = []

            for uri in uris:
                entity_dict = {"uri": uri}

                # Add properties if available
                if uri in entity_properties:
                    entity_dict.update(entity_properties[uri])

                related_entities[rel_type].append(entity_dict)

        return related_entities

# Global service instance
graph_service = GraphService()
