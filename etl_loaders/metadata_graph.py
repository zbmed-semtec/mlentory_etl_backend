"""
MLModel Metadata Property Graph.

Provides a parallel Neo4j property graph to track extraction metadata for all
MLModel properties and relations, enabling reconstruction of MLModel states
at specific points in time.

This graph tracks how and when each property was extracted, allowing for
provenance and temporal reconstruction of MLModel entities.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from etl_loaders.rdf_store import Neo4jConfig, _run_cypher
from etl_loaders.load_helpers import LoadHelpers
from rdflib import Graph, Literal, Namespace, URIRef, BNode
from rdflib.namespace import RDF, XSD
from datetime import datetime

logger = logging.getLogger(__name__)

# Metadata property alias to ignore when iterating model properties
METADATA_ALIAS = "https://w3id.org/mlentory/mlentory_graph/meta/"


def ensure_metadata_graph_constraints(cfg: Optional[Neo4jConfig] = None) -> None:
    """
    Ensure Neo4j constraints exist for the metadata property graph.

    Creates unique constraints on MLModelMeta.uri and MLModelProperty.iri
    to ensure data integrity and enable efficient lookups.

    Args:
        cfg: Neo4j configuration. If None, loads from environment.
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    # Create unique constraint for MLModelMeta nodes
    _run_cypher(
        """
        CREATE CONSTRAINT mlmodel_meta_unique IF NOT EXISTS
        FOR (m:MLModelMeta) REQUIRE m.uri IS UNIQUE
        """,
        cfg=env_cfg,
    )

    # Create unique constraint for MLModelProperty nodes
    _run_cypher(
        """
        CREATE CONSTRAINT mlmodel_property_unique IF NOT EXISTS
        FOR (p:MLModelProperty) REQUIRE p.iri IS UNIQUE
        """,
        cfg=env_cfg,
    )

    logger.info("Ensured metadata graph constraints exist")


def write_mlmodel_metadata(
    model: Dict[str, Any],
    extracted_at: datetime,
    cfg: Optional[Neo4jConfig] = None,
) -> int:
    """
    Write metadata for all properties of an MLModel to the property graph.

    For each property in the model (excluding metadata), creates or updates
    the metadata graph with extraction information including timestamp,
    method, confidence, and notes.

    Args:
        model: Normalized MLModel dictionary with FAIR4ML properties
        extracted_at: Timestamp when this extraction occurred
        cfg: Neo4j configuration. If None, loads from environment.

    Returns:
        Number of HAS_PROPERTY relationships created

    Raises:
        ValueError: If model is missing required identifier/name fields
    """

    env_cfg = cfg or Neo4jConfig.from_env()

    # Get the model URI using the same logic as RDF loader
    model_uri = LoadHelpers.mint_subject(model)

    # Get extraction metadata if available
    extraction_meta = model.get(METADATA_ALIAS, {})

    relationships_created = 0

    # Iterate through all model properties that look like IRIs (exclude metadata)
    for predicate_iri, value in model.items():
        if not isinstance(predicate_iri, str):
            continue
        if not predicate_iri.startswith("http"):  # Basic IRI check
            continue
        if predicate_iri == METADATA_ALIAS:  # Skip metadata alias
            continue

        # Get extraction metadata for this property
        prop_meta = extraction_meta.get(predicate_iri)
        if prop_meta:
            extraction_method = getattr(prop_meta, 'extraction_method', 'unknown')
            confidence = getattr(prop_meta, 'confidence', 1.0)
            notes = getattr(prop_meta, 'notes', None)
        else:
            extraction_method = 'unknown'
            confidence = 1.0
            notes = None

        # Handle both single values and lists
        if not isinstance(value, list):
            values = [value] if value is not None else []
        else:
            values = value

        # Write metadata for each value
        for val in values:
            if val is None:
                continue

            # Determine if value is an IRI or literal
            if LoadHelpers.is_iri(str(val)):
                value_param = None
                value_uri_param = str(val)
            else:
                value_param = str(val)
                value_uri_param = None

            # Create the HAS_PROPERTY relationship
            _run_cypher(
                """
                MERGE (m:MLModelMeta {uri: $model_uri})
                MERGE (p:MLModelProperty {iri: $predicate_iri})
                CREATE (m)-[:HAS_PROPERTY {
                    value: $value,
                    value_uri: $value_uri,
                    extracted_at: datetime($extracted_at),
                    extraction_method: $extraction_method,
                    confidence: $confidence,
                    notes: $notes
                }]->(p)
                """,
                {
                    "model_uri": model_uri,
                    "predicate_iri": predicate_iri,
                    "value": value_param,
                    "value_uri": value_uri_param,
                    "extracted_at": extracted_at.isoformat(),
                    "extraction_method": extraction_method,
                    "confidence": confidence,
                    "notes": notes,
                },
                cfg=env_cfg,
            )

            relationships_created += 1

    logger.debug(f"Created {relationships_created} metadata relationships for model {model_uri}")
    return relationships_created


def reconstruct_mlmodel_at(
    model_uri: str,
    at: datetime,
    cfg: Optional[Neo4jConfig] = None,
) -> Dict[str, List[str]]:
    """
    Reconstruct an MLModel's state at a specific point in time.

    For each property, finds all relationships with extracted_at <= the given
    timestamp and returns the values from the most recent extraction for each
    property at that time.

    Args:
        model_uri: URI of the MLModel to reconstruct
        at: Timestamp to reconstruct state at (inclusive)
        cfg: Neo4j configuration. If None, loads from environment.

    Returns:
        Dictionary mapping predicate IRIs to lists of values as they existed
        at the given timestamp. Empty dict if no metadata found.
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    results = _run_cypher(
        """
        MATCH (m:MLModelMeta {uri: $model_uri})-[r:HAS_PROPERTY]->(p:MLModelProperty)
        WHERE r.extracted_at <= datetime($at)
        WITH p, max(r.extracted_at) AS latest_ts
        MATCH (m:MLModelMeta {uri: $model_uri})-[r:HAS_PROPERTY]->(p:MLModelProperty)
        WHERE r.extracted_at = latest_ts
        RETURN p.iri AS predicate, collect(coalesce(r.value, r.value_uri)) AS values
        """,
        {
            "model_uri": model_uri,
            "at": at.isoformat(),
        },
        cfg=env_cfg,
    )

    # Convert results to dict
    reconstruction = {}
    for record in results:
        predicate = record["predicate"]
        values = record["values"]
        # Filter out None values that might result from collect(coalesce(...))
        reconstruction[predicate] = [v for v in values if v is not None]

    logger.debug(f"Reconstructed {len(reconstruction)} properties for model {model_uri} at {at}")
    return reconstruction


def cleanup_metadata_graph(cfg: Optional[Neo4jConfig] = None) -> None:
    """
    Remove all metadata graph nodes and relationships.

    Used for testing - removes all MLModelMeta and MLModelProperty nodes
    and their relationships. Does not affect the RDF graph.

    Args:
        cfg: Neo4j configuration. If None, loads from environment.
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    # Delete all metadata relationships and nodes
    _run_cypher(
        """
        MATCH (m:MLModelMeta)-[r:HAS_PROPERTY]->(p:MLModelProperty)
        DELETE r, m, p
        """,
        cfg=env_cfg,
    )

    # Also delete any orphaned nodes (though the above should handle it)
    _run_cypher("MATCH (m:MLModelMeta) DELETE m", cfg=env_cfg)
    _run_cypher("MATCH (p:MLModelProperty) DELETE p", cfg=env_cfg)

    logger.info("Cleaned up metadata graph")


def build_and_export_metadata_rdf(
    output_ttl_path: Optional[str] = None,
    cfg: Optional[Neo4jConfig] = None,
) -> Dict[str, Any]:
    """
    Export the metadata property graph as RDF triples.

    Queries the metadata graph and converts it to RDF triples using custom
    namespaces for the metadata schema.

    Args:
        output_ttl_path: Optional path to save Turtle file
        cfg: Neo4j configuration. If None, loads from environment.

    Returns:
        Dict with export statistics:
        - triples_added: Number of triples exported
        - ttl_path: Path to saved Turtle file (if requested)
        - timestamp: Export timestamp
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    # Define custom namespaces for metadata
    MLENTORY = Namespace("https://w3id.org/mlentory/")
    MLENTORY_META = Namespace("https://w3id.org/mlentory/mlentory_graph/meta/")

    # Create RDF graph
    graph = Graph()
    graph.bind("mlentory", MLENTORY)
    graph.bind("mlentory-meta", MLENTORY_META)
    graph.bind("rdf", RDF)
    graph.bind("xsd", XSD)

    # Query metadata relationships
    results = _run_cypher(
        """
        MATCH (m:MLModelMeta)-[r:HAS_PROPERTY]->(p:MLModelProperty)
        RETURN m.uri as model_uri, p.iri as property_iri,
               r.value as value, r.value_uri as value_uri,
               r.extracted_at as extracted_at,
               r.extraction_method as extraction_method,
               r.confidence as confidence,
               r.notes as notes
        """,
        cfg=env_cfg,
    )

    triples_added = 0

    for record in results:
        # Create blank node for the extraction event
        extraction_event = BNode()

        # Add the extraction event as a triple
        model_uri = URIRef(record["model_uri"])
        property_iri = URIRef(record["property_iri"])

        # Add the main property triple
        if record["value"] is not None:
            graph.add((model_uri, property_iri, Literal(record["value"])))
        elif record["value_uri"] is not None:
            graph.add((model_uri, property_iri, URIRef(record["value_uri"])))

        # Add metadata about the extraction
        graph.add((model_uri, MLENTORY_META.extractionEvent, extraction_event))
        graph.add((extraction_event, MLENTORY_META.property, property_iri))
        graph.add((extraction_event, MLENTORY_META.extractedAt,
                  Literal(record["extracted_at"], datatype=XSD.dateTime)))
        graph.add((extraction_event, MLENTORY_META.extractionMethod,
                  Literal(record["extraction_method"])))
        graph.add((extraction_event, MLENTORY_META.confidence,
                  Literal(record["confidence"], datatype=XSD.decimal)))

        if record["notes"]:
            graph.add((extraction_event, MLENTORY_META.notes, Literal(record["notes"])))

        triples_added += 1

    logger.info(f"Exported {triples_added} metadata triples as RDF")

    # Save Turtle file if requested
    ttl_path = None
    if output_ttl_path:
        ttl_file = Path(output_ttl_path)
        ttl_file.parent.mkdir(parents=True, exist_ok=True)

        graph.serialize(destination=str(ttl_file), format="turtle")
        ttl_path = str(ttl_file)
        logger.info(f"Saved metadata RDF to Turtle file: {ttl_path}")

    return {
        "triples_added": triples_added,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }
