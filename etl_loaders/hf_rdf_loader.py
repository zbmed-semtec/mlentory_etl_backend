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
        # use the first id that starts with https://w3id.org/mlentory/mlentory_graph/
        for id in identifiers:
            if id.startswith("https://w3id.org/mlentory/mlentory_graph") or id.startswith("<https://w3id.org/mlentory/mlentory_graph"):
                return id
        return identifiers[0]
    
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
            if create_triple(graph, subject, predicate, item, datatype):
                added = True
        return added
    
    return create_triple(graph, subject, predicate, value, datatype)
    
    

def create_triple(graph: Graph, subject: URIRef, predicate: URIRef, value: Any, datatype: Optional[URIRef] = None) -> bool:
    """
    Create a triple with either a literal or IRI object.
    
    If value is a valid IRI, adds it as URIRef. Otherwise, adds as Literal.
    Handles lists by adding multiple triples.
    """
    
    
    # Convert value to string
    value_str = str(value) if not isinstance(value, str) else value
    
    if value is None or value == "" or value == []:
        return False
    
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
    
    string_properties_lst = [
        # Core identification properties
        "https://schema.org/identifier",
        "https://schema.org/name",
        "https://schema.org/url",
        
        # Authorship & provenance
        "https://schema.org/author",
        "https://w3id.org/fair4ml/sharedBy",
        
        # Description & documentation
        "https://schema.org/description",
        "https://schema.org/discussionUrl",
        "https://schema.org/archivedAt",
        "https://w3id.org/codemeta/readme",
        "https://w3id.org/codemeta/issueTracker",
    ]
    
    for string_property in string_properties_lst:
        add_literal_or_iri(graph, subject, string_property,
                           model.get(string_property), datatype=XSD.string)
    
    date_properties_lst = [
        "https://schema.org/dateCreated",
        "https://schema.org/dateModified",
        "https://schema.org/datePublished",
    ]
    for date_property in date_properties_lst:
        add_literal_or_iri(graph, subject, date_property,
                           model.get(date_property), datatype=XSD.dateTime)
    
    # add related entities
    related_entities_lst = [
        # Reference publication
        "https://w3id.org/codemeta/referencePublication",
        # License
        "https://w3id.org/codemeta/license",
        # Base models
        "https://w3id.org/fair4ml/fineTunedFrom",
        # Datasets
        "https://w3id.org/fair4ml/trainedOn",
        "https://w3id.org/fair4ml/testedOn",
        "https://w3id.org/fair4ml/validatedOn",
        "https://w3id.org/fair4ml/evaluatedOn",
    ]
    for related_entity in related_entities_lst:
        add_literal_or_iri(graph, subject, related_entity,
                           model.get(related_entity))
    
    triples_added = len(graph) - triples_before
    return triples_added


def mint_article_subject(article: Dict[str, Any]) -> str:
    """
    Mint a subject IRI for a scholarly article.
    
    Uses the first identifier if it's a valid IRI, otherwise creates
    a stable hash-based IRI using the article URL.
    
    Args:
        article: Article dictionary with Schema.org properties
        
    Returns:
        Subject IRI string
    """
    # Try to use first identifier if it's an IRI
    identifiers = article.get("https://schema.org/identifier", [])
    if isinstance(identifiers, str):
        identifiers = [identifiers]
    
    if identifiers and isinstance(identifiers, list):
        # use the first id that starts with https://w3id.org/mlentory/mlentory_graph/
        for id in identifiers:
            if id.startswith("https://w3id.org/mlentory/mlentory_graph/"):
                return id
        # Otherwise use first identifier if it's an IRI
        for id in identifiers:
            if is_iri(id):
                return id
    
    # Fallback: mint IRI from URL hash
    url = article.get("https://schema.org/url", "")
    if url:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        minted_iri = f"https://w3id.org/mlentory/article/{url_hash}"
        logger.debug(f"Minted article subject IRI from URL hash: {minted_iri}")
        return minted_iri
    
    # Last resort: use a random hash
    article_str = json.dumps(article, sort_keys=True)
    article_hash = hashlib.sha256(article_str.encode()).hexdigest()
    fallback_iri = f"https://w3id.org/mlentory/article/{article_hash}"
    logger.warning(f"No URL found, using fallback IRI: {fallback_iri}")
    return fallback_iri


def build_article_triples(graph: Graph, article: Dict[str, Any]) -> int:
    """
    Build RDF triples for a single Schema.org ScholarlyArticle.
    
    Creates triples for core identification, authorship, temporal, description,
    and publication context properties.
    
    Args:
        graph: RDFLib Graph to add triples to
        article: Article dictionary with Schema.org properties (using IRI aliases)
        
    Returns:
        Number of triples added
    """
    triples_before = len(graph)
    
    # Mint subject IRI
    subject_iri = mint_article_subject(article)
    subject = URIRef(subject_iri)
    
    # Add rdf:type
    graph.add((subject, namespaces["rdf"].type, namespaces["schema"].ScholarlyArticle))
    
    string_properties_lst = [
        "https://schema.org/identifier",
        "https://schema.org/name",
        "https://schema.org/url",
        "https://schema.org/sameAs",
        # Description & content
        "https://schema.org/description",
        "https://schema.org/about",
        # Authorship
        "https://schema.org/author",
        # Publication context
        "https://schema.org/isPartOf",
        "https://schema.org/comment",
    ]
    for string_property in string_properties_lst:
        add_literal_or_iri(graph, subject, string_property,
                           article.get(string_property), datatype=XSD.string)

    
    date_properties_lst = [
        "https://schema.org/datePublished",
        "https://schema.org/dateModified",
    ]
    for date_property in date_properties_lst:
        add_literal_or_iri(graph, subject, date_property,
                           article.get(date_property), datatype=XSD.dateTime)
    
    triples_added = len(graph) - triples_before
    return triples_added


def build_and_persist_articles_rdf(
    json_path: str,
    config: Neo4jStoreConfig,
    output_ttl_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build RDF triples from normalized articles and persist to Neo4j.
    
    Args:
        json_path: Path to normalized articles JSON (articles.json)
        config: Neo4jStoreConfig for connecting to Neo4j
        output_ttl_path: Optional path to save Turtle file
        
    Returns:
        Dict with loading statistics:
        - articles_processed: Number of articles processed
        - triples_added: Total number of triples added
        - errors: Number of errors encountered
        - ttl_path: Path to saved Turtle file (if requested)
        
    Raises:
        FileNotFoundError: If json_path doesn't exist
        ValueError: If JSON is invalid
    """
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized articles file not found: {json_path}")
    
    logger.info(f"Loading normalized articles from {json_path}")
    with open(json_file, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    if not isinstance(articles, list):
        raise ValueError(f"Expected list of articles, got {type(articles)}")
    
    logger.info(f"Loaded {len(articles)} articles")
    
    # Open graph with Neo4j backend
    logger.info("Opening RDF graph with Neo4j backend...")
    graph = open_graph(config=config)
    
    # Build triples for each article
    total_triples = 0
    errors = 0
    graph_closed = False
    
    try:
        for idx, article in enumerate(articles):
            try:
                triples_added = build_article_triples(graph, article)
                total_triples += triples_added
                
                if (idx + 1) % 50 == 0:
                    logger.info(f"Processed {idx + 1}/{len(articles)} articles, "
                              f"added {total_triples} triples")
            except Exception as e:
                errors += 1
                article_id = article.get("https://schema.org/identifier", f"unknown_{idx}")
                logger.error(f"Error building triples for article {article_id}: {e}", 
                           exc_info=True)
                logger.error(f"Stack trace: {traceback.format_exc()}")
        
        logger.info(f"Finished building triples: {total_triples} triples for "
                   f"{len(articles)} articles ({errors} errors)")
        
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
        "articles_processed": len(articles),
        "triples_added": total_triples,
        "errors": errors,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }


def mint_license_subject(license_data: Dict[str, Any]) -> str:
    """
    Mint a subject IRI for a CreativeWork license entity.
    """
    identifiers = license_data.get("https://schema.org/identifier", [])
    if isinstance(identifiers, str):
        identifiers = [identifiers]

    if identifiers and isinstance(identifiers, list):
        for identifier in identifiers:
            if identifier.startswith("https://w3id.org/mlentory/mlentory_graph/"):
                return identifier
        for identifier in identifiers:
            if is_iri(identifier):
                return identifier

    url = license_data.get("https://schema.org/url", "")
    if url:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        minted_iri = f"https://w3id.org/mlentory/license/{url_hash}"
        logger.debug("Minted license subject IRI from URL hash: %s", minted_iri)
        return minted_iri

    payload_hash = hashlib.sha256(json.dumps(license_data, sort_keys=True).encode()).hexdigest()
    fallback_iri = f"https://w3id.org/mlentory/license/{payload_hash}"
    logger.warning("No identifiers found for license, using fallback IRI: %s", fallback_iri)
    return fallback_iri


def build_license_triples(graph: Graph, license_data: Dict[str, Any]) -> int:
    """
    Build RDF triples for a Schema.org CreativeWork representing a license.
    """
    triples_before = len(graph)

    subject_iri = mint_license_subject(license_data)
    subject = URIRef(subject_iri)

    graph.add((subject, namespaces["rdf"].type, namespaces["schema"].CreativeWork))

    add_literal_or_iri(graph, subject, "https://schema.org/identifier",
                       license_data.get("https://schema.org/identifier"))
    add_literal_or_iri(graph, subject, "https://schema.org/name",
                       license_data.get("https://schema.org/name"))
    add_literal_or_iri(graph, subject, "https://schema.org/url",
                       license_data.get("https://schema.org/url"))
    add_literal_or_iri(graph, subject, "https://schema.org/sameAs",
                       license_data.get("https://schema.org/sameAs"))
    add_literal_or_iri(graph, subject, "https://schema.org/alternateName",
                       license_data.get("https://schema.org/alternateName"))

    add_literal_or_iri(graph, subject, "https://schema.org/description",
                       license_data.get("https://schema.org/description"))
    add_literal_or_iri(graph, subject, "https://schema.org/abstract",
                       license_data.get("https://schema.org/abstract"))
    add_literal_or_iri(graph, subject, "https://schema.org/text",
                       license_data.get("https://schema.org/text"))

    add_literal_or_iri(graph, subject, "https://schema.org/license",
                       license_data.get("https://schema.org/license"))
    add_literal_or_iri(graph, subject, "https://schema.org/version",
                       license_data.get("https://schema.org/version"))
    add_literal_or_iri(graph, subject, "https://schema.org/copyrightNotice",
                       license_data.get("https://schema.org/copyrightNotice"))
    add_literal_or_iri(graph, subject, "https://schema.org/legislationJurisdiction",
                       license_data.get("https://schema.org/legislationJurisdiction"))
    add_literal_or_iri(graph, subject, "https://schema.org/legislationType",
                       license_data.get("https://schema.org/legislationType"))

    for temporal_predicate in (
        "https://schema.org/dateCreated",
        "https://schema.org/dateModified",
        "https://schema.org/datePublished",
    ):
        date_value = license_data.get(temporal_predicate)
        if date_value:
            dt_str = to_xsd_datetime(date_value)
            if dt_str:
                add_literal_or_iri(graph, subject, temporal_predicate, dt_str, datatype=XSD.dateTime)

    add_literal_or_iri(graph, subject, "https://schema.org/isBasedOn",
                       license_data.get("https://schema.org/isBasedOn"))
    add_literal_or_iri(graph, subject, "https://schema.org/subjectOf",
                       license_data.get("https://schema.org/subjectOf"))

    triples_added = len(graph) - triples_before
    return triples_added


def build_and_persist_licenses_rdf(
    json_path: str,
    config: Neo4jStoreConfig,
    output_ttl_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build RDF triples from normalized licenses and persist to Neo4j.
    """
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized licenses file not found: {json_path}")

    logger.info("Loading normalized licenses from %s", json_path)
    with open(json_file, "r", encoding="utf-8") as f:
        licenses = json.load(f)

    if not isinstance(licenses, list):
        raise ValueError(f"Expected list of licenses, got {type(licenses)}")

    logger.info("Loaded %s licenses", len(licenses))

    logger.info("Opening RDF graph with Neo4j backend...")
    graph = open_graph(config=config)

    total_triples = 0
    errors = 0
    graph_closed = False

    try:
        for idx, license_entry in enumerate(licenses):
            try:
                triples_added = build_license_triples(graph, license_entry)
                total_triples += triples_added

                if (idx + 1) % 50 == 0:
                    logger.info("Processed %s/%s licenses, added %s triples",
                                idx + 1, len(licenses), total_triples)
            except Exception as exc:
                errors += 1
                identifier = license_entry.get("https://schema.org/identifier", f"unknown_{idx}")
                logger.error("Error building triples for license %s: %s", identifier, exc, exc_info=True)
                logger.error("Stack trace: %s", traceback.format_exc())

        logger.info("Finished building license triples: %s triples for %s licenses (%s errors)",
                    total_triples, len(licenses), errors)

        ttl_path = None
        if output_ttl_path:
            ttl_file = Path(output_ttl_path)
            ttl_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Flushing graph writes before TTL export...")
            graph.close(True)
            graph_closed = True
            logger.info("Exporting license graph to Turtle via neosemantics: %s", output_ttl_path)
            export_graph_neosemantics(file_path=str(ttl_file), format="Turtle")
            ttl_path = str(ttl_file)
            logger.info("Saved license Turtle file: %s", ttl_path)

    finally:
        if not graph_closed:
            logger.info("Closing graph and flushing commits to Neo4j...")
            graph.close(True)
            logger.info("Graph closed, commits flushed")

    return {
        "licenses_processed": len(licenses),
        "triples_added": total_triples,
        "errors": errors,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }


def mint_dataset_subject(dataset_data: Dict[str, Any]) -> str:
    """
    Mint a subject IRI for a Croissant Dataset entity.
    
    Prefers identifiers in this order:
    1. MLentory IRI from identifier list
    2. Any other valid IRI from identifier list
    3. Hash-based IRI from URL
    4. Fallback hash-based IRI from payload
    
    Args:
        dataset_data: Dataset dictionary with Croissant properties
        
    Returns:
        Subject IRI string
    """
    identifiers = dataset_data.get("https://schema.org/identifier", [])
    if isinstance(identifiers, str):
        identifiers = [identifiers]

    if identifiers and isinstance(identifiers, list):
        # Prefer MLentory IRI
        for identifier in identifiers:
            if identifier.startswith("https://w3id.org/mlentory/mlentory_graph/"):
                return identifier
        # Otherwise use any valid IRI
        for identifier in identifiers:
            if is_iri(identifier):
                return identifier

    # Fall back to URL-based hash
    url = dataset_data.get("https://schema.org/url", "")
    if url:
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        minted_iri = f"https://w3id.org/mlentory/dataset/{url_hash}"
        logger.debug("Minted dataset subject IRI from URL hash: %s", minted_iri)
        return minted_iri

    # Ultimate fallback: hash of entire payload
    payload_hash = hashlib.sha256(json.dumps(dataset_data, sort_keys=True).encode()).hexdigest()
    fallback_iri = f"https://w3id.org/mlentory/dataset/{payload_hash}"
    logger.warning("No identifiers found for dataset, using fallback IRI: %s", fallback_iri)
    return fallback_iri


def build_dataset_triples(graph: Graph, dataset_data: Dict[str, Any]) -> int:
    """
    Build RDF triples for a Croissant Dataset (schema:Dataset).
    
    Args:
        graph: RDFLib graph to add triples to
        dataset_data: Normalized dataset dictionary with Croissant properties
        
    Returns:
        Number of triples added
    """
    triples_before = len(graph)

    subject_iri = mint_dataset_subject(dataset_data)
    subject = URIRef(subject_iri)

    # rdf:type
    graph.add((subject, namespaces["rdf"].type, namespaces["schema"].Dataset))

    # Core identification
    add_literal_or_iri(graph, subject, "https://schema.org/identifier",
                       dataset_data.get("https://schema.org/identifier"))
    add_literal_or_iri(graph, subject, "https://schema.org/name",
                       dataset_data.get("https://schema.org/name"))
    add_literal_or_iri(graph, subject, "https://schema.org/url",
                       dataset_data.get("https://schema.org/url"))
    add_literal_or_iri(graph, subject, "https://schema.org/sameAs",
                       dataset_data.get("https://schema.org/sameAs"))

    # Description
    add_literal_or_iri(graph, subject, "https://schema.org/description",
                       dataset_data.get("https://schema.org/description"))

    # Licensing
    add_literal_or_iri(graph, subject, "https://schema.org/license",
                       dataset_data.get("https://schema.org/license"))

    # Croissant conformance (Dublin Core Terms)
    conforms_to = dataset_data.get("http://purl.org/dc/terms/conformsTo")
    if conforms_to:
        add_literal_or_iri(graph, subject, "http://purl.org/dc/terms/conformsTo", conforms_to)

    # Citation (Croissant)
    cite_as = dataset_data.get("http://mlcommons.org/croissant/citeAs")
    if cite_as:
        add_literal_or_iri(graph, subject, "http://mlcommons.org/croissant/citeAs", cite_as)

    # Keywords
    add_literal_or_iri(graph, subject, "https://schema.org/keywords",
                       dataset_data.get("https://schema.org/keywords"))

    # Creator
    add_literal_or_iri(graph, subject, "https://schema.org/creator",
                       dataset_data.get("https://schema.org/creator"))

    # Temporal properties
    for temporal_predicate in (
        "https://schema.org/datePublished",
        "https://schema.org/dateModified",
    ):
        date_value = dataset_data.get(temporal_predicate)
        if date_value:
            dt_str = to_xsd_datetime(date_value)
            if dt_str:
                add_literal_or_iri(graph, subject, temporal_predicate, dt_str, datatype=XSD.dateTime)

    triples_added = len(graph) - triples_before
    return triples_added


def build_and_persist_datasets_rdf(
    json_path: str,
    config: Neo4jStoreConfig,
    output_ttl_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build RDF triples from normalized Croissant datasets and persist to Neo4j.
    
    Args:
        json_path: Path to normalized datasets JSON (datasets.json)
        config: Neo4j store configuration
        output_ttl_path: Optional path to export RDF as Turtle
        
    Returns:
        Dictionary with load statistics
    """
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized datasets file not found: {json_path}")

    logger.info("Loading normalized datasets from %s", json_path)
    with open(json_file, "r", encoding="utf-8") as f:
        datasets = json.load(f)

    if not isinstance(datasets, list):
        raise ValueError(f"Expected list of datasets, got {type(datasets)}")

    logger.info("Loaded %s datasets", len(datasets))

    logger.info("Opening RDF graph with Neo4j backend...")
    graph = open_graph(config=config)

    total_triples = 0
    errors = 0
    graph_closed = False

    try:
        for idx, dataset_entry in enumerate(datasets):
            try:
                triples_added = build_dataset_triples(graph, dataset_entry)
                total_triples += triples_added

                if (idx + 1) % 50 == 0:
                    logger.info("Processed %s/%s datasets, added %s triples",
                                idx + 1, len(datasets), total_triples)
            except Exception as exc:
                errors += 1
                identifier = dataset_entry.get("https://schema.org/identifier", f"unknown_{idx}")
                logger.error("Error building triples for dataset %s: %s", identifier, exc, exc_info=True)
                logger.error("Stack trace: %s", traceback.format_exc())

        logger.info("Finished building dataset triples: %s triples for %s datasets (%s errors)",
                    total_triples, len(datasets), errors)

        ttl_path = None
        if output_ttl_path:
            ttl_file = Path(output_ttl_path)
            ttl_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Flushing graph writes before TTL export...")
            graph.close(True)
            graph_closed = True
            logger.info("Exporting dataset graph to Turtle via neosemantics: %s", output_ttl_path)
            export_graph_neosemantics(file_path=str(ttl_file), format="Turtle")
            ttl_path = str(ttl_file)
            logger.info("Saved dataset Turtle file: %s", ttl_path)

    finally:
        if not graph_closed:
            logger.info("Closing graph and flushing commits to Neo4j...")
            graph.close(True)
            logger.info("Graph closed, commits flushed")

    return {
        "datasets_processed": len(datasets),
        "triples_added": total_triples,
        "errors": errors,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }


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

