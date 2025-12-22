"""
Builds RDF triples from normalized FAIR4ML models and persists them
to Neo4j using rdflib-neo4j integration.

This v1 implementation focuses on core identification, provenance, temporal,
description, and documentation properties.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
import traceback
from typing import Any, Dict, List, Optional

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD
from rdflib_neo4j import Neo4jStoreConfig

from etl_loaders.rdf_store import namespaces, open_graph, export_graph_neosemantics_batched
from etl_loaders.metadata_graph import ensure_metadata_graph_constraints, write_mlmodel_metadata_batch
from etl_loaders.load_helpers import LoadHelpers

logger = logging.getLogger(__name__)


    

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
    subject_iri = LoadHelpers.mint_subject(model)
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
        "https://schema.org/license",
        # Keywords
        "https://schema.org/keywords",
        # In Language
        "https://schema.org/inLanguage",
        # ML Task
        "https://w3id.org/fair4ml/mlTask",
        # Model Category
        "https://w3id.org/fair4ml/modelCategory",
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

def build_and_persist_models_rdf(
    json_path: str,
    config: Neo4jStoreConfig,
    output_ttl_path: Optional[str] = None,
    write_metadata: bool = True,
    batch_size: int = 20,
) -> Dict[str, Any]:
    """
    Build RDF triples from normalized models and persist to Neo4j.

    Args:
        json_path: Path to normalized models JSON (mlmodels.json)
        config: Neo4jStoreConfig for connecting to Neo4j
        output_ttl_path: Optional path to save Turtle file
        write_metadata: Whether to write metadata to parallel property graph (default: True)
        batch_size: Number of models to process before logging progress (default: 100)

    Returns:
        Dict with loading statistics:
        - models_processed: Number of models processed
        - triples_added: Total number of triples added
        - errors: Number of errors encountered
        - ttl_path: Path to saved Turtle file (if requested)
        - metadata_relationships: Number of metadata relationships created (if write_metadata=True)

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

    # Ensure metadata graph constraints exist if writing metadata
    if write_metadata:
        logger.info("Ensuring metadata graph constraints...")
        ensure_metadata_graph_constraints()

    # Build triples for each model and collect subject URIs
    total_triples = 0
    errors = 0
    graph_closed = False
    subject_uris = []
    total_metadata_relationships = 0
    run_timestamp = datetime.now()
    
    try:
        models_batches = [models[i:i + batch_size] for i in range(0, len(models), batch_size)]
        
        for batch_idx, batch in enumerate(models_batches):
            try:
                for model in batch:
                    subject_uri = LoadHelpers.mint_subject(model)
                    subject_uris.append(subject_uri)
                    triples_added = build_model_triples(graph, model)
                    total_triples += triples_added

                # Write metadata to parallel property graph if enabled
                if write_metadata:
                    metadata_relationships = write_mlmodel_metadata_batch(batch, run_timestamp)
                    total_metadata_relationships += metadata_relationships

                if (batch_idx + 1) % 100 == 0:
                    logger.info(f"Processed {batch_idx + 1}/{len(models_batches)} batches, "
                              f"added {total_triples} triples")
            except Exception as e:
                errors += 1
                model_ids = [model.get("https://schema.org/identifier") for model in batch]
                logger.error(f"Error building triples for models {model_ids}: {e}", 
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
            
            if subject_uris:
                logger.info(f"Exporting {len(subject_uris)} model subjects to Turtle via neosemantics: {output_ttl_path}")
                export_graph_neosemantics_batched(subject_uris=subject_uris, file_path=str(ttl_file), format="Turtle")
                ttl_path = str(ttl_file)
                logger.info(f"Saved Turtle file: {ttl_path}")
            else:
                logger.warning("No model subjects to export, skipping TTL generation")
        
    finally:
        # Close graph and flush commits to Neo4j if not already closed
        if not graph_closed:
            logger.info("Closing graph and flushing commits to Neo4j...")
            graph.close(True)
            logger.info("Graph closed, commits flushed")
    
    result = {
        "models_processed": len(models),
        "triples_added": total_triples,
        "errors": errors,
        "ttl_path": ttl_path,
        "timestamp": run_timestamp.isoformat(),
    }

    if write_metadata:
        result["metadata_relationships"] = total_metadata_relationships

    return result

def mint_article_subject(article: Dict[str, Any]) -> str:
    """
    Mint a subject IRI for a scholarly article.

    Uses centralized logic shared across entity types.
    """
    return LoadHelpers.mint_article_subject(article)


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
    
    # Build triples for each article and collect subject URIs
    total_triples = 0
    errors = 0
    graph_closed = False
    subject_uris = []
    
    try:
        for idx, article in enumerate(articles):
            try:
                subject_uri = mint_article_subject(article)
                subject_uris.append(subject_uri)
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
            
            if subject_uris:
                logger.info(f"Exporting {len(subject_uris)} article subjects to Turtle via neosemantics: {output_ttl_path}")
                export_graph_neosemantics_batched(subject_uris=subject_uris, file_path=str(ttl_file), format="Turtle")
                ttl_path = str(ttl_file)
                logger.info(f"Saved Turtle file: {ttl_path}")
            else:
                logger.warning("No article subjects to export, skipping TTL generation")
        
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
    return LoadHelpers.mint_license_subject(license_data)


def build_license_triples(graph: Graph, license_data: Dict[str, Any]) -> int:
    """
    Build RDF triples for a Schema.org CreativeWork representing a license.
    """
    triples_before = len(graph)

    subject_iri = mint_license_subject(license_data)
    subject = URIRef(subject_iri)

    graph.add((subject, namespaces["rdf"].type, namespaces["schema"].CreativeWork))
    
    string_properties_lst = [
        "https://schema.org/identifier",
        "https://schema.org/name",
        "https://schema.org/url",
        "https://schema.org/sameAs",
        "https://schema.org/alternateName",
        "https://schema.org/description",
        "https://schema.org/abstract",
        "https://schema.org/text",
        "https://schema.org/license",
        "https://schema.org/version",
        "https://schema.org/copyrightNotice",
        "https://schema.org/legislationJurisdiction",
        "https://schema.org/legislationType",
        "https://schema.org/isBasedOn",
        "https://schema.org/subjectOf",
    ]
    for string_property in string_properties_lst:
        add_literal_or_iri(graph, subject, string_property,
                           license_data.get(string_property), datatype=XSD.string)
        
    
    date_properties_lst = [
        "https://schema.org/dateCreated",
        "https://schema.org/dateModified",
        "https://schema.org/datePublished",
    ]
    for date_property in date_properties_lst:
        add_literal_or_iri(graph, subject, date_property,
                           license_data.get(date_property), datatype=XSD.dateTime)
        
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
    subject_uris = []

    try:
        for idx, license_entry in enumerate(licenses):
            try:
                subject_uri = mint_license_subject(license_entry)
                subject_uris.append(subject_uri)
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
            
            if subject_uris:
                logger.info("Exporting %s license subjects to Turtle via neosemantics: %s", len(subject_uris), output_ttl_path)
                export_graph_neosemantics_batched(subject_uris=subject_uris, file_path=str(ttl_file), format="Turtle")
                ttl_path = str(ttl_file)
                logger.info("Saved license Turtle file: %s", ttl_path)
            else:
                logger.warning("No license subjects to export, skipping TTL generation")

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

    Uses centralized logic shared across entity types.
    """
    return LoadHelpers.mint_dataset_subject(dataset_data)


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
    
    string_properties_lst = [
        "https://schema.org/identifier",
        "https://schema.org/name",
        "https://schema.org/url",
        "https://schema.org/sameAs",
        "https://schema.org/description",
        "https://schema.org/license",
    ]
    for string_property in string_properties_lst:
        add_literal_or_iri(graph, subject, string_property,
                           dataset_data.get(string_property), datatype=XSD.string)

    # Croissant conformance (Dublin Core Terms)
    optional_properties_lst = [
        "http://purl.org/dc/terms/conformsTo",
        "http://mlcommons.org/croissant/citeAs",
        "https://schema.org/creator"
    ]
    for optional_property in optional_properties_lst:
        if optional_property in dataset_data:
            add_literal_or_iri(graph, subject, optional_property,
                           dataset_data.get(optional_property), datatype=XSD.string)
    
    external_properties_lst = [
        "https://schema.org/keywords",
        "https://schema.org/license",
    ]
    for external_property in external_properties_lst:
        add_literal_or_iri(graph, subject, external_property,
                           dataset_data.get(external_property))
    
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
    subject_uris = []

    try:
        for idx, dataset_entry in enumerate(datasets):
            try:
                subject_uri = mint_dataset_subject(dataset_entry)
                subject_uris.append(subject_uri)
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
            
            if subject_uris:
                logger.info("Exporting %s dataset subjects to Turtle via neosemantics: %s", len(subject_uris), output_ttl_path)
                export_graph_neosemantics_batched(subject_uris=subject_uris, file_path=str(ttl_file), format="Turtle")
                ttl_path = str(ttl_file)
                logger.info("Saved dataset Turtle file: %s", ttl_path)
            else:
                logger.warning("No dataset subjects to export, skipping TTL generation")

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
    if LoadHelpers.is_iri(value_str):
        graph.add((subject, predicate, URIRef(value_str)))
        # logger.debug(f"Added IRI triple: <{subject}> <{predicate}> <{value_str}>")
    else:
        # Add as literal
        if datatype:
            graph.add((subject, predicate, Literal(value_str, datatype=datatype)))
        else:
            graph.add((subject, predicate, Literal(value_str, datatype=XSD.string)))
        # logger.debug(f"Added literal triple: <{subject}> <{predicate}> \"{value_str}\"")
    
    return True


def mint_defined_term_subject(term_data: Dict[str, Any]) -> str:
    """
    Mint a subject IRI for a DefinedTerm entity.

    Uses centralized logic shared across entity types.
    """
    return LoadHelpers.mint_defined_term_subject(term_data)


def build_defined_term_triples(graph: Graph, term_data: Dict[str, Any]) -> int:
    """
    Build RDF triples for a Schema.org DefinedTerm.
    
    Args:
        graph: RDFLib graph to add triples to
        term_data: Normalized term dictionary with Schema.org properties
        
    Returns:
        Number of triples added
    """
    triples_before = len(graph)

    subject_iri = mint_defined_term_subject(term_data)
    subject = URIRef(subject_iri)

    # rdf:type
    graph.add((subject, namespaces["rdf"].type, namespaces["schema"].DefinedTerm))

    string_properties_lst = [
        "https://schema.org/identifier",
        "https://schema.org/name",
        "https://schema.org/url",
        "https://schema.org/sameAs",
        "https://schema.org/description",
        "https://schema.org/termCode",
        "https://schema.org/alternateName",
    ]
    for string_property in string_properties_lst:
        add_literal_or_iri(graph, subject, string_property,
                           term_data.get(string_property), datatype=XSD.string)

    # inDefinedTermSet can be either URL or literal
    in_defined_term_set = term_data.get("https://schema.org/inDefinedTermSet")
    if in_defined_term_set:
        add_literal_or_iri(graph, subject, "https://schema.org/inDefinedTermSet",
                           in_defined_term_set)

    triples_added = len(graph) - triples_before
    return triples_added


def build_and_persist_tasks_rdf(
    json_path: str,
    config: Neo4jStoreConfig,
    output_ttl_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build RDF triples from normalized DefinedTerm tasks and persist to Neo4j.
    
    Args:
        json_path: Path to normalized tasks JSON (tasks.json)
        config: Neo4j store configuration
        output_ttl_path: Optional path to export RDF as Turtle
        
    Returns:
        Dictionary with load statistics
    """
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized tasks file not found: {json_path}")

    logger.info("Loading normalized tasks from %s", json_path)
    with open(json_file, "r", encoding="utf-8") as f:
        tasks = json.load(f)

    if not isinstance(tasks, list):
        raise ValueError(f"Expected list of tasks, got {type(tasks)}")

    logger.info("Loaded %s tasks", len(tasks))

    logger.info("Opening RDF graph with Neo4j backend...")
    graph = open_graph(config=config)

    total_triples = 0
    errors = 0
    graph_closed = False
    subject_uris = []

    try:
        for idx, task_entry in enumerate(tasks):
            try:
                subject_uri = mint_defined_term_subject(task_entry)
                subject_uris.append(subject_uri)
                triples_added = build_defined_term_triples(graph, task_entry)
                total_triples += triples_added

                if (idx + 1) % 50 == 0:
                    logger.info("Processed %s/%s tasks, added %s triples",
                                idx + 1, len(tasks), total_triples)
            except Exception as exc:
                errors += 1
                identifier = task_entry.get("https://schema.org/identifier", f"unknown_{idx}")
                logger.error("Error building triples for task %s: %s", identifier, exc, exc_info=True)
                logger.error("Stack trace: %s", traceback.format_exc())

        logger.info("Finished building task triples: %s triples for %s tasks (%s errors)",
                    total_triples, len(tasks), errors)

        ttl_path = None
        if output_ttl_path:
            ttl_file = Path(output_ttl_path)
            ttl_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Flushing graph writes before TTL export...")
            graph.close(True)
            graph_closed = True
            
            if subject_uris:
                logger.info("Exporting %s task subjects to Turtle via neosemantics: %s", len(subject_uris), output_ttl_path)
                export_graph_neosemantics_batched(subject_uris=subject_uris, file_path=str(ttl_file), format="Turtle")
                ttl_path = str(ttl_file)
                logger.info("Saved task Turtle file: %s", ttl_path)
            else:
                logger.warning("No task subjects to export, skipping TTL generation")

    finally:
        if not graph_closed:
            logger.info("Closing graph and flushing commits to Neo4j...")
            graph.close(True)
            logger.info("Graph closed, commits flushed")

    return {
        "tasks_processed": len(tasks),
        "triples_added": total_triples,
        "errors": errors,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }


def build_and_persist_defined_terms_rdf(
    json_path: str,
    config: Neo4jStoreConfig,
    output_ttl_path: Optional[str] = None,
    entity_label: str = "terms",
) -> Dict[str, Any]:
    """
    Generic function to build RDF triples from normalized DefinedTerm entities and persist to Neo4j.
    
    This function can be used for any entity type that uses the DefinedTerm schema (tasks, keywords, etc.).
    
    Args:
        json_path: Path to normalized terms JSON file
        config: Neo4j store configuration
        output_ttl_path: Optional path to export RDF as Turtle
        entity_label: Label for logging (e.g., "keywords", "tasks")
        
    Returns:
        Dictionary with load statistics
    """
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized {entity_label} file not found: {json_path}")

    logger.info("Loading normalized %s from %s", entity_label, json_path)
    with open(json_file, "r", encoding="utf-8") as f:
        terms = json.load(f)

    if not isinstance(terms, list):
        raise ValueError(f"Expected list of {entity_label}, got {type(terms)}")

    logger.info("Loaded %s %s", len(terms), entity_label)

    logger.info("Opening RDF graph with Neo4j backend...")
    graph = open_graph(config=config)

    total_triples = 0
    errors = 0
    graph_closed = False
    subject_uris = []

    try:
        for idx, term_entry in enumerate(terms):
            try:
                subject_uri = mint_defined_term_subject(term_entry)
                subject_uris.append(subject_uri)
                triples_added = build_defined_term_triples(graph, term_entry)
                total_triples += triples_added

                if (idx + 1) % 50 == 0:
                    logger.info("Processed %s/%s %s, added %s triples",
                                idx + 1, len(terms), entity_label, total_triples)
            except Exception as exc:
                errors += 1
                identifier = term_entry.get("https://schema.org/identifier", f"unknown_{idx}")
                logger.error("Error building triples for %s %s: %s", entity_label, identifier, exc, exc_info=True)
                logger.error("Stack trace: %s", traceback.format_exc())

        logger.info("Finished building %s triples: %s triples for %s %s (%s errors)",
                    entity_label, total_triples, len(terms), entity_label, errors)

        ttl_path = None
        if output_ttl_path:
            ttl_file = Path(output_ttl_path)
            ttl_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Flushing graph writes before TTL export...")
            graph.close(True)
            graph_closed = True
            
            if subject_uris:
                logger.info("Exporting %s %s subjects to Turtle via neosemantics: %s", len(subject_uris), entity_label, output_ttl_path)
                export_graph_neosemantics_batched(subject_uris=subject_uris, file_path=str(ttl_file), format="Turtle")
                ttl_path = str(ttl_file)
                logger.info("Saved %s Turtle file: %s", entity_label, ttl_path)
            else:
                logger.warning("No %s subjects to export, skipping TTL generation", entity_label)

    finally:
        if not graph_closed:
            logger.info("Closing graph and flushing commits to Neo4j...")
            graph.close(True)
            logger.info("Graph closed, commits flushed")

    return {
        f"{entity_label}_processed": len(terms),
        "triples_added": total_triples,
        "errors": errors,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }


def mint_language_subject(language_data: Dict[str, Any]) -> str:
    """
    Mint a subject IRI for a Language entity.

    Uses centralized logic shared across entity types.
    """
    return LoadHelpers.mint_language_subject(language_data)


def build_language_triples(graph: Graph, language_data: Dict[str, Any]) -> int:
    """
    Build RDF triples for a Schema.org Language.
    
    Args:
        graph: RDFLib graph to add triples to
        language_data: Normalized language dictionary with Schema.org properties
        
    Returns:
        Number of triples added
    """
    triples_before = len(graph)

    subject_iri = mint_language_subject(language_data)
    subject = URIRef(subject_iri)

    # rdf:type
    graph.add((subject, namespaces["rdf"].type, namespaces["schema"].Language))

    string_properties_lst = [
        "https://schema.org/identifier",
        "https://schema.org/name",
        "https://schema.org/url",
        "https://schema.org/sameAs",
        "https://schema.org/alternateName",
        "https://schema.org/description",
    ]
    for string_property in string_properties_lst:
        add_literal_or_iri(graph, subject, string_property,
                           language_data.get(string_property), datatype=XSD.string)

    triples_added = len(graph) - triples_before
    return triples_added


def build_and_persist_languages_rdf(
    json_path: str,
    config: Neo4jStoreConfig,
    output_ttl_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build RDF triples from normalized Language entities and persist to Neo4j.
    
    Args:
        json_path: Path to normalized languages JSON (languages.json)
        config: Neo4j store configuration
        output_ttl_path: Optional path to export RDF as Turtle
        
    Returns:
        Dictionary with load statistics
    """
    json_file = Path(json_path)
    if not json_file.exists():
        raise FileNotFoundError(f"Normalized languages file not found: {json_path}")

    logger.info("Loading normalized languages from %s", json_path)
    with open(json_file, "r", encoding="utf-8") as f:
        languages = json.load(f)

    if not isinstance(languages, list):
        raise ValueError(f"Expected list of languages, got {type(languages)}")

    logger.info("Loaded %s languages", len(languages))

    logger.info("Opening RDF graph with Neo4j backend...")
    graph = open_graph(config=config)

    total_triples = 0
    errors = 0
    graph_closed = False
    subject_uris = []

    try:
        for idx, language_entry in enumerate(languages):
            try:
                subject_uri = mint_language_subject(language_entry)
                subject_uris.append(subject_uri)
                triples_added = build_language_triples(graph, language_entry)
                total_triples += triples_added

                if (idx + 1) % 50 == 0:
                    logger.info("Processed %s/%s languages, added %s triples",
                                idx + 1, len(languages), total_triples)
            except Exception as exc:
                errors += 1
                identifier = language_entry.get("https://schema.org/identifier", f"unknown_{idx}")
                logger.error("Error building triples for language %s: %s", identifier, exc, exc_info=True)
                logger.error("Stack trace: %s", traceback.format_exc())

        logger.info("Finished building language triples: %s triples for %s languages (%s errors)",
                    total_triples, len(languages), errors)

        ttl_path = None
        if output_ttl_path:
            ttl_file = Path(output_ttl_path)
            ttl_file.parent.mkdir(parents=True, exist_ok=True)
            logger.info("Flushing graph writes before TTL export...")
            graph.close(True)
            graph_closed = True
            
            if subject_uris:
                logger.info("Exporting %s language subjects to Turtle via neosemantics: %s", len(subject_uris), output_ttl_path)
                export_graph_neosemantics_batched(subject_uris=subject_uris, file_path=str(ttl_file), format="Turtle")
                ttl_path = str(ttl_file)
                logger.info("Saved language Turtle file: %s", ttl_path)
            else:
                logger.warning("No language subjects to export, skipping TTL generation")

    finally:
        if not graph_closed:
            logger.info("Closing graph and flushing commits to Neo4j...")
            graph.close(True)
            logger.info("Graph closed, commits flushed")

    return {
        "languages_processed": len(languages),
        "triples_added": total_triples,
        "errors": errors,
        "ttl_path": ttl_path,
        "timestamp": datetime.now().isoformat(),
    }