"""
HuggingFace RDF Loader.

Builds RDF triples from normalized HF FAIR4ML models and persists them
to Neo4j using rdflib-neo4j integration.

This v1 implementation focuses on core identification, provenance, temporal,
description, and documentation properties.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
import traceback
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
from rdflib_neo4j import Neo4jStoreConfig

from etl_loaders.rdf_store import namespaces, open_graph, export_graph_neosemantics

logger = logging.getLogger(__name__)


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


def to_xsd_datetime(value: Any) -> Optional[str]:
    """
    Convert various datetime formats to xsd:dateTime string.
    
    Args:
        value: Datetime value (string, datetime, or timestamp)
        
    Returns:
        ISO 8601 datetime string or None if conversion fails
    """
    if not value:
        return None
    
    try:
        if isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, str):
            # Try parsing and re-formatting to ensure ISO format
            # Handle various formats: "2021-01-01T00:00:00Z", "2021-01-01", etc.
            if 'T' in value:
                # Already ISO format, potentially with Z suffix
                return value.replace('Z', '+00:00') if value.endswith('Z') else value
            else:
                # Date only, add time
                return f"{value}T00:00:00"
        elif isinstance(value, (int, float)):
            # Unix timestamp
            return datetime.fromtimestamp(value).isoformat()
        else:
            logger.warning(f"Unsupported datetime type: {type(value)}")
            return None
    except Exception as e:
        logger.warning(f"Failed to convert to xsd:dateTime: {value} - {e}")
        return None


def mint_subject(model: Dict[str, Any]) -> str:
    """
    Mint a subject IRI for a model.
    
    Uses the first identifier if it's a valid IRI, otherwise creates
    a stable hash-based IRI using the model URL.
    
    Args:
        model: Model dictionary with FAIR4ML properties
        
    Returns:
        Subject IRI string
    """
    # Try to use first identifier if it's an IRI
    identifiers = model.get("https://schema.org/identifier", [])
    if isinstance(identifiers, str):
        identifiers = [identifiers]
    
    if identifiers and isinstance(identifiers, list):
        first_id = identifiers[0]
        if is_iri(first_id):
            logger.debug(f"Using identifier as subject IRI: {first_id}")
            return first_id
    
    # Fallback: mint IRI from URL hash
    url = model.get("https://schema.org/url", "")
    if url:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        minted_iri = f"https://w3id.org/mlentory/model/{url_hash}"
        logger.debug(f"Minted subject IRI from URL hash: {minted_iri}")
        return minted_iri
    
    # Last resort: use a random hash
    model_str = json.dumps(model, sort_keys=True)
    model_hash = hashlib.sha256(model_str.encode()).hexdigest()
    fallback_iri = f"https://w3id.org/mlentory/model/{model_hash}"
    logger.warning(f"No URL found, using fallback IRI: {fallback_iri}")
    return fallback_iri


def add_literal_or_iri(
    graph: Graph,
    subject: URIRef,
    predicate_iri: str,
    value: Any,
    datatype: Optional[URIRef] = None,
) -> bool:
    """
    Add a triple with either a literal or IRI object.
    
    If value is a valid IRI, adds it as URIRef. Otherwise, adds as Literal.
    Handles lists by adding multiple triples.
    
    Args:
        graph: RDFLib Graph
        subject: Subject URIRef
        predicate_iri: Full predicate IRI string
        value: Value to add (string, list, or other)
        datatype: Optional XSD datatype for literals
        
    Returns:
        True if at least one triple was added, False otherwise
    """
    if value is None or value == "" or value == []:
        return False
    
    predicate = URIRef(predicate_iri)
    
    # Handle lists by recursing
    if isinstance(value, list):
        added = False
        for item in value:
            if add_literal_or_iri(graph, subject, predicate_iri, item, datatype):
                added = True
        return added
    
    # Convert value to string
    value_str = str(value) if not isinstance(value, str) else value
    
    # Check if it's an IRI
    if is_iri(value_str):
        graph.add((subject, predicate, URIRef(value_str)))
        logger.debug(f"Added IRI triple: <{subject}> <{predicate}> <{value_str}>")
    else:
        # Add as literal
        if datatype:
            graph.add((subject, predicate, Literal(value_str, datatype=datatype)))
        else:
            graph.add((subject, predicate, Literal(value_str, datatype=XSD.string)))
        logger.debug(f"Added literal triple: <{subject}> <{predicate}> \"{value_str}\"")
    
    return True


def build_model_triples(graph: Graph, model: Dict[str, Any]) -> int:
    """
    Build RDF triples for a single FAIR4ML model.
    
    Creates triples for core identification, provenance, temporal, description,
    and documentation URL properties.
    
    Args:
        graph: RDFLib Graph to add triples to
        model: Model dictionary with FAIR4ML properties (using IRI aliases)
        
    Returns:
        Number of triples added
    """
    triples_before = len(graph)
    
    # Mint subject IRI
    subject_iri = mint_subject(model)
    subject = URIRef(subject_iri)
    
    # Add rdf:type
    graph.add((subject, namespaces["rdf"].type, namespaces["fair4ml"].MLModel))
    
    # Core identification properties
    add_literal_or_iri(graph, subject, "https://schema.org/identifier", 
                      model.get("https://schema.org/identifier"))
    add_literal_or_iri(graph, subject, "https://schema.org/name", 
                      model.get("https://schema.org/name"))
    add_literal_or_iri(graph, subject, "https://schema.org/url", 
                      model.get("https://schema.org/url"))
    
    # Authorship & provenance
    add_literal_or_iri(graph, subject, "https://schema.org/author", 
                      model.get("https://schema.org/author"))
    add_literal_or_iri(graph, subject, "https://w3id.org/fair4ml/sharedBy", 
                      model.get("https://w3id.org/fair4ml/sharedBy"))
    
    # Temporal information (with xsd:dateTime conversion)
    date_created = model.get("https://schema.org/dateCreated")
    if date_created:
        dt_str = to_xsd_datetime(date_created)
        if dt_str:
            add_literal_or_iri(graph, subject, "https://schema.org/dateCreated", 
                             dt_str, datatype=XSD.dateTime)
    
    date_modified = model.get("https://schema.org/dateModified")
    if date_modified:
        dt_str = to_xsd_datetime(date_modified)
        if dt_str:
            add_literal_or_iri(graph, subject, "https://schema.org/dateModified", 
                             dt_str, datatype=XSD.dateTime)
    
    date_published = model.get("https://schema.org/datePublished")
    if date_published:
        dt_str = to_xsd_datetime(date_published)
        if dt_str:
            add_literal_or_iri(graph, subject, "https://schema.org/datePublished", 
                             dt_str, datatype=XSD.dateTime)
    
    # Description & documentation
    add_literal_or_iri(graph, subject, "https://schema.org/description", 
                      model.get("https://schema.org/description"))
    add_literal_or_iri(graph, subject, "https://schema.org/discussionUrl", 
                      model.get("https://schema.org/discussionUrl"))
    add_literal_or_iri(graph, subject, "https://schema.org/archivedAt", 
                      model.get("https://schema.org/archivedAt"))
    add_literal_or_iri(graph, subject, "https://w3id.org/codemeta/readme", 
                      model.get("https://w3id.org/codemeta/readme"))
    add_literal_or_iri(graph, subject, "https://w3id.org/codemeta/issueTracker", 
                      model.get("https://w3id.org/codemeta/issueTracker"))
    
    triples_added = len(graph) - triples_before
    return triples_added


def build_and_persist_models_rdf(
    json_path: str,
    config: Neo4jStoreConfig,
    output_ttl_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build RDF triples from normalized HF models and persist to Neo4j.
    
    Args:
        json_path: Path to normalized models JSON (mlmodels.json)
        config: Neo4jStoreConfig for connecting to Neo4j
        output_ttl_path: Optional path to save Turtle file
        
    Returns:
        Dict with loading statistics:
        - models_processed: Number of models processed
        - triples_added: Total number of triples added
        - errors: Number of errors encountered
        - ttl_path: Path to saved Turtle file (if requested)
        
    Raises:
        FileNotFoundError: If json_path doesn't exist
        ValueError: If JSON is invalid
    """
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized models file not found: {json_path}")
    
    logger.info(f"Loading normalized models from {json_path}")
    with open(json_file, 'r', encoding='utf-8') as f:
        models = json.load(f)
    
    if not isinstance(models, list):
        raise ValueError(f"Expected list of models, got {type(models)}")
    
    logger.info(f"Loaded {len(models)} models")
    
    # Open graph with Neo4j backend
    logger.info("Opening RDF graph with Neo4j backend...")
    graph = open_graph(config=config)
    
    # Build triples for each model
    total_triples = 0
    errors = 0
    graph_closed = False
    
    try:
        for idx, model in enumerate(models):
            try:
                triples_added = build_model_triples(graph, model)
                total_triples += triples_added
                
                if (idx + 1) % 100 == 0:
                    logger.info(f"Processed {idx + 1}/{len(models)} models, "
                              f"added {total_triples} triples")
            except Exception as e:
                errors += 1
                model_id = model.get("https://schema.org/identifier", f"unknown_{idx}")
                logger.error(f"Error building triples for model {model_id}: {e}", 
                           exc_info=True)
                logger.error(f"Stack trace: {traceback.format_exc()}")
        
        logger.info(f"Finished building triples: {total_triples} triples for "
                   f"{len(models)} models ({errors} errors)")
        
        # Save Turtle file via neosemantics export after flushing writes
        ttl_path = None
        if output_ttl_path:
            ttl_file = Path(output_ttl_path)
            ttl_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Flushing graph writes before TTL export...")
            graph.close(True)
            graph_closed = True
            logger.info(f"Exporting graph to Turtle via neosemantics: {output_ttl_path}")
            export_graph_neosemantics(file_path=str(ttl_file), format="Turtle")
            ttl_path = str(ttl_file)
            logger.info(f"Saved Turtle file: {ttl_path}")
        
    finally:
        # Close graph and flush commits to Neo4j if not already closed
        if not graph_closed:
            logger.info("Closing graph and flushing commits to Neo4j...")
            graph.close(True)
            logger.info("Graph closed, commits flushed")
    
    return {
        "models_processed": len(models),
        "triples_added": total_triples,
        "errors": errors,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }

