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
                "HAS_LICENSE",
                "license",
                "sharedBy",
                "author",
                # Data usage
                "USES_DATASET",
                "dataset",
                "trainingData",
                "trainedOn",
                "testedOn",
                "validatedOn",
                "evaluatedOn",
                # Publications
                "CITED_IN",
                "mentions",
                "describedBy",
                "referencePublication",
                # Keywords / tasks / categories
                "HAS_KEYWORD",
                "keyword",
                "tag",
                "PERFORMS_TASK",
                "mlTask",
                "applicationArea",
                "modelCategory",
                # Languages
                "SUPPORTS_LANGUAGE",
                "language",
                "inLanguage",
                # Lineage
                "fineTunedFrom",
            ],
            "License": ["APPLIES_TO", "DESCRIBES"],
            "Dataset": ["USED_BY", "HAS_CREATOR"],
            "DefinedTerm": ["RELATED_TO", "HAS_PARENT"],
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

        This method is intentionally kept simple and explicit:
        1. Validate and normalize inputs (depth, labels, relationship types).
        2. Build a Cypher pattern for direction and relationship filters.
        3. Run a single Cypher query that returns nodes and edges.
        4. Map raw Neo4j results into `GraphNode` and `GraphEdge` models.

        Args:
            entity_id: Compact identifier of the starting entity (no scheme).
            depth: Traversal depth (1-3).
            relationships: Optional list of relationship types to follow
                (e.g., ["HAS_LICENSE", "USES_DATASET"]).
            direction: Traversal direction ("outgoing", "incoming", "both").
            entity_label: Optional Neo4j label for the start node
                (e.g., "MLModel", "License", "DefinedTerm").

        Returns:
            GraphResponse containing nodes and edges.
        """
        # Clamp depth to a safe range
        depth = max(1, min(depth, 3))

        # Reconstruct full URI from compact ID when possible
        entity_uri = self._build_entity_uri(entity_id)

        # If no relationships provided, choose sensible defaults per entity type
        if not relationships and entity_label:
            relationships = self.default_relationships.get(entity_label, [])

        # Build label clause for the start node (if provided)
        label_clause = ""
        if entity_label:
            # Allow only alphanumeric and underscore to avoid injection
            safe_label = "".join(c for c in entity_label if c.isalnum() or c == "_")
            if safe_label:
                label_clause = f":{safe_label}"

        # Build relationship pattern (e.g., :HAS_LICENSE|USES_DATASET)
        rel_pattern = ""
        if relationships:
            sanitized_rels: List[str] = []
            for rel in relationships:
                rel = rel.strip()
                if not rel:
                    continue
                # Only keep alphanumeric and underscore characters
                safe_rel = "".join(c for c in rel if c.isalnum() or c == "_")
                if safe_rel:
                    sanitized_rels.append(safe_rel)

            if sanitized_rels:
                rel_types = "|".join(sanitized_rels)
                rel_pattern = f":{rel_types}"

        # Build variable-length path pattern based on direction
        # Examples:
        #   both:     -[r:REL*1..2]-
        #   outgoing: -[r:REL*1..2]->
        #   incoming: <-[r:REL*1..2]-
        path_pattern = f"-[r{rel_pattern}*1..{depth}]-"
        if direction == "outgoing":
            path_pattern = f"-[r{rel_pattern}*1..{depth}]->"
        elif direction == "incoming":
            path_pattern = f"<-[r{rel_pattern}*1..{depth}]-"

        # Single unified Cypher query:
        #  - Match the start node (optionally constrained by label).
        #  - Optionally match paths up to the given depth.
        #  - Collect distinct nodes and relationships from those paths.
        unified_query = f"""
        MATCH (start{label_clause} {{uri: $uri}})
        OPTIONAL MATCH path = (start){path_pattern}(end)
        WITH start, collect(path) AS paths
        // Filter out null paths before unwinding
        UNWIND [p IN paths WHERE p IS NOT NULL] AS p
        UNWIND nodes(p) AS n
        UNWIND relationships(p) AS r
        RETURN
            collect(DISTINCT {{
                id: coalesce(n.uri, elementId(n)),
                labels: labels(n),
                props: properties(n)
            }}) AS nodes,
            collect(DISTINCT {{
                id: elementId(r),
                source: startNode(r).uri,
                target: endNode(r).uri,
                type: type(r),
                props: properties(r)
            }}) AS edges,
            {{
                start_node: {{
                    id: start.uri,
                    labels: labels(start),
                    props: properties(start)
                }}
            }} AS metadata
        """

        try:
            results = _run_cypher(unified_query, {"uri": entity_uri}, self.config)

            # If the start node doesn't exist, Neo4j returns no rows
            if not results:
                return GraphResponse(nodes=[], edges=[], metadata={"error": "Entity not found"})

            data = results[0]

            graph_nodes: List[GraphNode] = []
            seen_nodes: Set[str] = set()

            # Always include the start node (if present)
            start_meta = data.get("metadata", {}).get("start_node")
            if start_meta and start_meta.get("id"):
                start_node = GraphNode(
                    id=start_meta["id"],
                    labels=start_meta.get("labels", []),
                    properties=start_meta.get("props") or {},
                )
                graph_nodes.append(start_node)
                seen_nodes.add(start_node.id)

            # Add all other nodes from the paths
            raw_nodes = data.get("nodes") or []
            for raw in raw_nodes:
                node_id = raw.get("id")
                if not node_id or node_id in seen_nodes:
                    continue
                node = GraphNode(
                    id=node_id,
                    labels=raw.get("labels", []),
                    properties=raw.get("props") or {},
                )
                graph_nodes.append(node)
                seen_nodes.add(node_id)

            # Parse edges
            graph_edges: List[GraphEdge] = []
            raw_edges = data.get("edges") or []
            for raw in raw_edges:
                edge_id = raw.get("id")
                if not edge_id:
                    continue
                edge = GraphEdge(
                    id=edge_id,
                    source=raw.get("source", ""),
                    target=raw.get("target", ""),
                    type=raw.get("type", ""),
                    properties=raw.get("props") or {},
                )
                graph_edges.append(edge)

            return GraphResponse(
                nodes=graph_nodes,
                edges=graph_edges,
                metadata={
                    "start_uri": entity_uri,
                    "depth": depth,
                    "direction": direction,
                    "node_count": len(graph_nodes),
                    "edge_count": len(graph_edges),
                    "relationships": relationships or [],
                    "entity_label": entity_label,
                },
            )

        except Exception as e:
            logger.error(f"Error traversing graph for {entity_uri}: {e}", exc_info=True)
            return GraphResponse(nodes=[], edges=[], metadata={"error": str(e)})

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
