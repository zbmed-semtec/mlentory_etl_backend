"""
MLModel Metadata Property Graph.

Provides a parallel Neo4j property graph to track extraction metadata for all
MLModel properties and relations, enabling reconstruction of MLModel states
at specific points in time using validity intervals.

This graph tracks how and when each property was extracted, allowing for
provenance and temporal reconstruction of MLModel entities.
"""

from __future__ import annotations

import hashlib
import json
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


def _generate_snapshot_hash(snapshot: Dict[str, Any]) -> str:
    """
    Generate a deterministic hash for a property snapshot.

    Args:
        snapshot: Dictionary containing snapshot properties

    Returns:
        SHA256 hash string representing the snapshot content
    """
    # Create a normalized representation for hashing
    hash_data = {
        "predicate_iri": snapshot["predicate_iri"],
        "value": snapshot.get("value"),
        "value_uri": snapshot.get("value_uri"),
        "extraction_method": snapshot.get("extraction_method"),
        "confidence": snapshot.get("confidence"),
        "notes": snapshot.get("notes"),
    }

    # Convert to JSON string with sorted keys for deterministic hashing
    hash_str = json.dumps(hash_data, sort_keys=True, default=str)
    return hashlib.sha256(hash_str.encode('utf-8')).hexdigest()


def ensure_metadata_graph_constraints(cfg: Optional[Neo4jConfig] = None) -> None:
    """
    Ensure Neo4j constraints exist for the temporal metadata property graph.

    Creates unique constraints on MLModel.uri and indexes on MLModelPropertySnapshot
    to ensure data integrity and enable efficient lookups.

    Args:
        cfg: Neo4j configuration. If None, loads from environment.
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    # Create unique constraint for MLModel nodes
    _run_cypher(
        """
        CREATE CONSTRAINT mlmodel_unique IF NOT EXISTS
        FOR (m:MLModel) REQUIRE m.uri IS UNIQUE
        """,
        cfg=env_cfg,
    )

    # Create index on MLModelPropertySnapshot predicate_iri for faster diffing
    _run_cypher(
        """
        CREATE INDEX mlmodel_property_snapshot_predicate IF NOT EXISTS
        FOR (p:MLModelPropertySnapshot) ON (p.predicate_iri)
        """,
        cfg=env_cfg,
    )

    # # Create index on MLModelPropertySnapshot value for faster diffing
    # _run_cypher(
    #     """
    #     CREATE INDEX mlmodel_property_snapshot_value IF NOT EXISTS
    #     FOR (p:MLModelPropertySnapshot) ON (p.value)
    #     """,
    #     cfg=env_cfg,
    # )

    # # Create index on MLModelPropertySnapshot value_uri for faster diffing
    # _run_cypher(
    #     """
    #     CREATE INDEX mlmodel_property_snapshot_value_uri IF NOT EXISTS
    #     FOR (p:MLModelPropertySnapshot) ON (p.value_uri)
    #     """,
    #     cfg=env_cfg,
    # )

    # Create index on MLModelPropertySnapshot snapshot_hash for fast change detection
    _run_cypher(
        """
        CREATE INDEX mlmodel_property_snapshot_hash IF NOT EXISTS
        FOR (p:MLModelPropertySnapshot) ON (p.snapshot_hash)
        """,
        cfg=env_cfg,
    )

    logger.info("Ensured temporal metadata graph constraints exist")


def _extract_property_snapshots(
    model: Dict[str, Any],
    extraction_meta: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract property-value snapshots from a model dictionary.

    Args:
        model: Normalized MLModel dictionary
        extraction_meta: Metadata dictionary for properties

    Returns:
        List of snapshot dictionaries with keys: predicate_iri, value, value_uri,
        extraction_method, confidence, notes
    """
    snapshots = []

    for predicate_iri, value in model.items():
        if not isinstance(predicate_iri, str):
            continue
        if not predicate_iri.startswith("http"):  # Basic IRI check
            continue
        if predicate_iri == METADATA_ALIAS:  # Skip metadata alias
            continue

        # Get extraction metadata for this property
        prop_meta = extraction_meta.get(predicate_iri)
        if isinstance(prop_meta, dict):
            # Metadata provided as a plain dictionary
            extraction_method = prop_meta.get("extraction_method", "unknown")
            confidence = prop_meta.get("confidence", 1.0)
            notes = prop_meta.get("notes")
        elif prop_meta is not None:
            # Fallback for object-style metadata (with attributes)
            extraction_method = getattr(prop_meta, "extraction_method", "unknown")
            confidence = getattr(prop_meta, "confidence", 1.0)
            notes = getattr(prop_meta, "notes", None)
        else:
            extraction_method = "unknown"
            confidence = 1.0
            notes = None

        # Handle both single values and lists
        if not isinstance(value, list):
            values = [value] if value is not None else []
        else:
            values = value

        # Create snapshot for each value
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

            snapshot = {
                "predicate_iri": predicate_iri,
                "value": value_param,
                "value_uri": value_uri_param,
                "extraction_method": extraction_method,
                "confidence": confidence,
                "notes": notes,
            }
            snapshot["snapshot_hash"] = _generate_snapshot_hash(snapshot)
            snapshots.append(snapshot)

    return snapshots


def write_mlmodel_metadata(
    model: Dict[str, Any],
    extracted_at: datetime,
    cfg: Optional[Neo4jConfig] = None,
) -> int:
    """
    Write metadata for all properties of an MLModel to the temporal property graph.

    Only creates new property snapshots when properties actually change, using
    validity intervals to track temporal changes efficiently.

    Args:
        model: Normalized MLModel dictionary with FAIR4ML properties
        extracted_at: Timestamp when this extraction occurred
        cfg: Neo4j configuration. If None, loads from environment.

    Returns:
        Number of new HAS_PROPERTY_SNAPSHOT relationships created

    Raises:
        ValueError: If model is missing required identifier/name fields
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    # Get the model URI using the same logic as RDF loader
    model_uri = LoadHelpers.mint_subject(model)

    # Get extraction metadata if available
    extraction_meta = model.get(METADATA_ALIAS, {})

    # Extract current property snapshots
    current_snapshots = _extract_property_snapshots(model, extraction_meta)

    # Query existing active snapshots (valid_to is null) and their hashes
    existing_results = _run_cypher(
        """
        MATCH (m:MLModel {uri: $model_uri})-[r:HAS_PROPERTY_SNAPSHOT]->(p:MLModelPropertySnapshot)
        WHERE r.valid_to IS NULL
        RETURN p.snapshot_hash as snapshot_hash, id(p) as snapshot_id
        """,
        {"model_uri": model_uri},
        cfg=env_cfg,
    )

    # Create set of existing snapshot hashes for fast lookup
    existing_hashes = {record["snapshot_hash"] for record in existing_results}
    existing_snapshot_ids = {record["snapshot_hash"]: record["snapshot_id"] for record in existing_results}

    # Create set of current snapshot hashes
    current_hashes = {snapshot["snapshot_hash"] for snapshot in current_snapshots}

    relationships_created = 0

    # Process current snapshots
    for snapshot in current_snapshots:
        snapshot_hash = snapshot["snapshot_hash"]

        if snapshot_hash in existing_hashes:
            # Snapshot already exists and is identical, keep it active
            continue
        else:
            # Check if this exact snapshot existed before (but was closed)
            # If so, we need to close the old one first
            if snapshot_hash in existing_snapshot_ids:
                # Close the existing relationship for this hash
                _run_cypher(
                    """
                    MATCH (m:MLModel {uri: $model_uri})-[r:HAS_PROPERTY_SNAPSHOT]->(p:MLModelPropertySnapshot)
                    WHERE id(p) = $snapshot_id
                    SET r.valid_to = datetime($extracted_at)
                    """,
                    {
                        "model_uri": model_uri,
                        "snapshot_id": existing_snapshot_ids[snapshot_hash],
                        "extracted_at": extracted_at.isoformat(),
                    },
                    cfg=env_cfg,
                )

            # Create new snapshot node and relationship
            _run_cypher(
                """
                MERGE (m:MLModel {uri: $model_uri})
                CREATE (m)-[:HAS_PROPERTY_SNAPSHOT {
                    valid_from: datetime($extracted_at),
                    valid_to: null
                }]->(:MLModelPropertySnapshot {
                    predicate_iri: $predicate_iri,
                    value: $value,
                    value_uri: $value_uri,
                    extraction_method: $extraction_method,
                    confidence: $confidence,
                    notes: $notes,
                    snapshot_hash: $snapshot_hash
                })
                """,
                {
                    "model_uri": model_uri,
                    "predicate_iri": snapshot["predicate_iri"],
                    "value": snapshot["value"],
                    "value_uri": snapshot["value_uri"],
                    "extraction_method": snapshot["extraction_method"],
                    "confidence": snapshot["confidence"],
                    "notes": snapshot["notes"],
                    "snapshot_hash": snapshot_hash,
                    "extracted_at": extracted_at.isoformat(),
                },
                cfg=env_cfg,
            )
            relationships_created += 1

    # Close validity intervals for removed properties (snapshots that existed but are no longer present)
    for existing_hash in existing_hashes:
        if existing_hash not in current_hashes:
            _run_cypher(
                """
                MATCH (m:MLModel {uri: $model_uri})-[r:HAS_PROPERTY_SNAPSHOT]->(p:MLModelPropertySnapshot)
                WHERE p.snapshot_hash = $snapshot_hash AND r.valid_to IS NULL
                SET r.valid_to = datetime($extracted_at)
                """,
                {
                    "model_uri": model_uri,
                    "snapshot_hash": existing_hash,
                    "extracted_at": extracted_at.isoformat(),
                },
                cfg=env_cfg,
            )

    logger.debug(f"Created {relationships_created} new metadata snapshots for model {model_uri}")
    return relationships_created


def reconstruct_mlmodel_at(
    model_uri: str,
    at: datetime,
    cfg: Optional[Neo4jConfig] = None,
) -> Dict[str, List[str]]:
    """
    Reconstruct an MLModel's state at a specific point in time using validity intervals.

    For each property, finds all active HAS_PROPERTY_SNAPSHOT relationships
    where valid_from <= timestamp and (valid_to is null or valid_to > timestamp).

    Args:
        model_uri: URI of the MLModel to reconstruct
        at: Timestamp to reconstruct state at (inclusive for valid_from, exclusive for valid_to)
        cfg: Neo4j configuration. If None, loads from environment.

    Returns:
        Dictionary mapping predicate IRIs to lists of values as they existed
        at the given timestamp. Empty dict if no metadata found.
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    results = _run_cypher(
        """
        MATCH (m:MLModel {uri: $model_uri})-[r:HAS_PROPERTY_SNAPSHOT]->(p:MLModelPropertySnapshot)
        WHERE r.valid_from <= datetime($at) AND (r.valid_to IS NULL OR r.valid_to > datetime($at))
        RETURN p.predicate_iri AS predicate, collect(coalesce(p.value, p.value_uri)) AS values
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


def cleanup_model_metadata(model_uri: str, cfg: Optional[Neo4jConfig] = None) -> None:
    """
    Remove metadata graph nodes and relationships for a specific model.

    Used for testing to ensure a clean slate for specific model tests.

    Args:
        model_uri: URI of the model to clean up
        cfg: Neo4j configuration. If None, loads from environment.
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    # Delete all metadata relationships and nodes for this specific model
    _run_cypher(
        """
        MATCH (m:MLModel {uri: $model_uri})-[r:HAS_PROPERTY_SNAPSHOT]->(p:MLModelPropertySnapshot)
        DELETE r, p
        """,
        {"model_uri": model_uri},
        cfg=env_cfg,
    )

    # Delete the model node itself
    _run_cypher(
        """
        MATCH (m:MLModel {uri: $model_uri})
        DELETE m
        """,
        {"model_uri": model_uri},
        cfg=env_cfg,
    )

    logger.debug(f"Cleaned up metadata for model {model_uri}")


def cleanup_metadata_graph(cfg: Optional[Neo4jConfig] = None) -> None:
    """
    Remove all temporal metadata graph nodes and relationships.

    Used for testing - removes all MLModel and MLModelPropertySnapshot nodes
    and their HAS_PROPERTY_SNAPSHOT relationships. Does not affect the RDF graph.

    Args:
        cfg: Neo4j configuration. If None, loads from environment.
    """
    env_cfg = cfg or Neo4jConfig.from_env()

    # Delete all metadata relationships and nodes
    _run_cypher(
        """
        MATCH (m:MLModel)-[r:HAS_PROPERTY_SNAPSHOT]->(p:MLModelPropertySnapshot)
        DELETE r, m, p
        """,
        cfg=env_cfg,
    )

    # Also delete any orphaned nodes (though the above should handle it)
    _run_cypher("MATCH (m:MLModel) DELETE m", cfg=env_cfg)
    _run_cypher("MATCH (p:MLModelPropertySnapshot) DELETE p", cfg=env_cfg)

    logger.info("Cleaned up temporal metadata graph")


def build_and_export_metadata_rdf(
    output_ttl_path: Optional[str] = None,
    cfg: Optional[Neo4jConfig] = None,
) -> Dict[str, Any]:
    """
    Export the temporal metadata property graph as RDF triples.

    Queries the metadata graph and converts it to RDF triples using custom
    namespaces for the metadata schema, including validity intervals.

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

    # Query metadata snapshots with validity intervals
    results = _run_cypher(
        """
        MATCH (m:MLModel)-[r:HAS_PROPERTY_SNAPSHOT]->(p:MLModelPropertySnapshot)
        RETURN m.uri as model_uri, p.predicate_iri as property_iri,
               p.value as value, p.value_uri as value_uri,
               r.valid_from as valid_from, r.valid_to as valid_to,
               p.extraction_method as extraction_method,
               p.confidence as confidence,
               p.notes as notes,
               p.snapshot_hash as snapshot_hash
        """,
        cfg=env_cfg,
    )

    triples_added = 0

    for record in results:
        # Create blank node for the property snapshot
        snapshot_event = BNode()

        # Add the extraction event as a triple
        model_uri = URIRef(record["model_uri"])
        property_iri = URIRef(record["property_iri"])

        # Add the main property triple
        if record["value"] is not None:
            graph.add((model_uri, property_iri, Literal(record["value"])))
        elif record["value_uri"] is not None:
            graph.add((model_uri, property_iri, URIRef(record["value_uri"])))

        # Add metadata about the snapshot with validity intervals
        graph.add((model_uri, MLENTORY_META.propertySnapshot, snapshot_event))
        graph.add((snapshot_event, MLENTORY_META.property, property_iri))
        graph.add((snapshot_event, MLENTORY_META.validFrom,
                  Literal(record["valid_from"], datatype=XSD.dateTime)))
        graph.add((snapshot_event, MLENTORY_META.extractionMethod,
                  Literal(record["extraction_method"])))
        graph.add((snapshot_event, MLENTORY_META.confidence,
                  Literal(record["confidence"], datatype=XSD.decimal)))

        if record["notes"]:
            graph.add((snapshot_event, MLENTORY_META.notes, Literal(record["notes"])))

        # Add valid_to if not null
        if record["valid_to"] is not None:
            graph.add((snapshot_event, MLENTORY_META.validTo,
                      Literal(record["valid_to"], datatype=XSD.dateTime)))

        triples_added += 1

    logger.info(f"Exported {triples_added} temporal metadata triples as RDF")

    # Save Turtle file if requested
    ttl_path = None
    if output_ttl_path:
        ttl_file = Path(output_ttl_path)
        ttl_file.parent.mkdir(parents=True, exist_ok=True)

        graph.serialize(destination=str(ttl_file), format="turtle")
        ttl_path = str(ttl_file)
        logger.info(f"Saved temporal metadata RDF to Turtle file: {ttl_path}")

    return {
        "triples_added": triples_added,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }
