"""
Unit tests for HuggingFace RDF loader.

These tests verify the core functionality of the RDF loader:
- IRI validation
- Datetime conversion
- Subject minting
- Triple building
- Full RDF graph construction
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch

import pytest
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, XSD

from etl_loaders.hf_rdf_loader import (
    is_iri,
    to_xsd_datetime,
    mint_subject,
    add_literal_or_iri,
    build_model_triples,
)

# Test fixtures

@pytest.fixture
def sample_model() -> Dict[str, Any]:
    """Sample FAIR4ML model for testing."""
    return {
        "https://schema.org/identifier": ["https://huggingface.co/bert-base-uncased"],
        "https://schema.org/name": "bert-base-uncased",
        "https://schema.org/url": "https://huggingface.co/bert-base-uncased",
        "https://schema.org/author": "google",
        "https://w3id.org/fair4ml/sharedBy": "Google Research",
        "https://schema.org/dateCreated": "2020-01-01T00:00:00",
        "https://schema.org/dateModified": "2020-06-01T00:00:00",
        "https://schema.org/datePublished": "2020-01-15T00:00:00",
        "https://schema.org/description": "BERT base model (uncased)",
        "https://schema.org/discussionUrl": "https://huggingface.co/bert-base-uncased/discussions",
        "https://schema.org/archivedAt": "https://archive.org/details/bert-base-uncased",
        "https://w3id.org/codemeta/readme": "https://huggingface.co/bert-base-uncased/blob/main/README.md",
        "https://w3id.org/codemeta/issueTracker": "https://github.com/google-research/bert/issues",
    }


@pytest.fixture
def minimal_model() -> Dict[str, Any]:
    """Minimal FAIR4ML model with only required fields."""
    return {
        "https://schema.org/name": "test-model",
        "https://schema.org/url": "https://example.com/test-model",
    }


@pytest.fixture
def empty_graph() -> Graph:
    """Empty RDFLib graph for testing."""
    return Graph()


# Tests for is_iri()

def test_is_iri_valid_http():
    assert is_iri("https://example.com/resource") is True
    assert is_iri("http://example.com/resource") is True


def test_is_iri_valid_schemes():
    assert is_iri("ftp://example.com/file") is True
    assert is_iri("urn:isbn:0451450523") is False  # No netloc


def test_is_iri_invalid():
    assert is_iri("not a url") is False
    assert is_iri("") is False
    assert is_iri(None) is False
    assert is_iri(123) is False


# Tests for to_xsd_datetime()

def test_to_xsd_datetime_iso_string():
    result = to_xsd_datetime("2020-01-01T00:00:00")
    assert result == "2020-01-01T00:00:00"


def test_to_xsd_datetime_iso_with_z():
    result = to_xsd_datetime("2020-01-01T00:00:00Z")
    assert result == "2020-01-01T00:00:00+00:00"


def test_to_xsd_datetime_date_only():
    result = to_xsd_datetime("2020-01-01")
    assert result == "2020-01-01T00:00:00"


def test_to_xsd_datetime_datetime_object():
    dt = datetime(2020, 1, 1, 12, 30, 45)
    result = to_xsd_datetime(dt)
    assert result == "2020-01-01T12:30:45"


def test_to_xsd_datetime_timestamp():
    timestamp = 1577836800  # 2020-01-01 00:00:00 UTC
    result = to_xsd_datetime(timestamp)
    assert result is not None
    assert "2020" in result


def test_to_xsd_datetime_invalid():
    assert to_xsd_datetime(None) is None
    assert to_xsd_datetime("") is None
    assert to_xsd_datetime("invalid") is None


# Tests for mint_subject()

def test_mint_subject_from_identifier_iri(sample_model):
    subject = mint_subject(sample_model)
    assert subject == "https://huggingface.co/bert-base-uncased"


def test_mint_subject_from_url_hash(minimal_model):
    subject = mint_subject(minimal_model)
    assert subject.startswith("https://w3id.org/mlentory/model/")
    assert len(subject) > 50  # Should include hash


def test_mint_subject_no_identifier_or_url():
    model = {"https://schema.org/name": "test"}
    subject = mint_subject(model)
    assert subject.startswith("https://w3id.org/mlentory/model/")


def test_mint_subject_identifier_as_string():
    model = {
        "https://schema.org/identifier": "https://example.com/model",
        "https://schema.org/name": "test",
    }
    subject = mint_subject(model)
    assert subject == "https://example.com/model"


# Tests for add_literal_or_iri()

def test_add_literal_or_iri_with_iri(empty_graph):
    subject = URIRef("https://example.com/subject")
    predicate = "https://schema.org/url"
    value = "https://example.com/resource"
    
    result = add_literal_or_iri(empty_graph, subject, predicate, value)
    
    assert result is True
    assert len(empty_graph) == 1
    # Check that it was added as URIRef
    triple = list(empty_graph)[0]
    assert isinstance(triple[2], URIRef)


def test_add_literal_or_iri_with_literal(empty_graph):
    subject = URIRef("https://example.com/subject")
    predicate = "https://schema.org/name"
    value = "Test Name"
    
    result = add_literal_or_iri(empty_graph, subject, predicate, value)
    
    assert result is True
    assert len(empty_graph) == 1
    # Check that it was added as Literal
    triple = list(empty_graph)[0]
    assert isinstance(triple[2], Literal)


def test_add_literal_or_iri_with_datatype(empty_graph):
    subject = URIRef("https://example.com/subject")
    predicate = "https://schema.org/dateCreated"
    value = "2020-01-01T00:00:00"
    
    result = add_literal_or_iri(empty_graph, subject, predicate, value, datatype=XSD.dateTime)
    
    assert result is True
    assert len(empty_graph) == 1
    triple = list(empty_graph)[0]
    assert isinstance(triple[2], Literal)
    assert triple[2].datatype == XSD.dateTime


def test_add_literal_or_iri_with_list(empty_graph):
    subject = URIRef("https://example.com/subject")
    predicate = "https://schema.org/identifier"
    values = ["https://example.com/id1", "https://example.com/id2"]
    
    result = add_literal_or_iri(empty_graph, subject, predicate, values)
    
    assert result is True
    assert len(empty_graph) == 2


def test_add_literal_or_iri_with_none(empty_graph):
    subject = URIRef("https://example.com/subject")
    predicate = "https://schema.org/name"
    
    result = add_literal_or_iri(empty_graph, subject, predicate, None)
    
    assert result is False
    assert len(empty_graph) == 0


def test_add_literal_or_iri_with_empty_string(empty_graph):
    subject = URIRef("https://example.com/subject")
    predicate = "https://schema.org/name"
    
    result = add_literal_or_iri(empty_graph, subject, predicate, "")
    
    assert result is False
    assert len(empty_graph) == 0


def test_add_literal_or_iri_with_empty_list(empty_graph):
    subject = URIRef("https://example.com/subject")
    predicate = "https://schema.org/identifier"
    
    result = add_literal_or_iri(empty_graph, subject, predicate, [])
    
    assert result is False
    assert len(empty_graph) == 0


# Tests for build_model_triples()

def test_build_model_triples_complete(empty_graph, sample_model):
    triples_added = build_model_triples(empty_graph, sample_model)
    
    assert triples_added > 0
    assert len(empty_graph) == triples_added
    
    # Verify rdf:type triple exists
    FAIR4ML = Namespace("https://w3id.org/fair4ml/")
    type_triples = list(empty_graph.triples((None, RDF.type, FAIR4ML.MLModel)))
    assert len(type_triples) == 1
    
    # Verify subject
    subject = type_triples[0][0]
    assert isinstance(subject, URIRef)


def test_build_model_triples_minimal(empty_graph, minimal_model):
    triples_added = build_model_triples(empty_graph, minimal_model)
    
    assert triples_added > 0
    
    # Should at least have rdf:type, name, and url
    assert len(empty_graph) >= 3


def test_build_model_triples_with_dates(empty_graph):
    model = {
        "https://schema.org/name": "test-model",
        "https://schema.org/url": "https://example.com/test",
        "https://schema.org/dateCreated": "2020-01-01T00:00:00",
        "https://schema.org/dateModified": "2020-06-01",
        "https://schema.org/datePublished": datetime(2020, 1, 15),
    }
    
    triples_added = build_model_triples(empty_graph, model)
    
    assert triples_added > 0
    
    # Check that dates were added with xsd:dateTime datatype
    SCHEMA = Namespace("https://schema.org/")
    date_created_triples = list(empty_graph.triples((None, SCHEMA.dateCreated, None)))
    assert len(date_created_triples) == 1
    assert date_created_triples[0][2].datatype == XSD.dateTime


def test_build_model_triples_subject_minting_priority(empty_graph):
    """Test that subject is minted from identifier IRI first."""
    model = {
        "https://schema.org/identifier": ["https://specific-id.com/model"],
        "https://schema.org/name": "test-model",
        "https://schema.org/url": "https://example.com/test",
    }
    
    build_model_triples(empty_graph, model)
    
    # Verify subject is the identifier IRI
    FAIR4ML = Namespace("https://w3id.org/fair4ml/")
    type_triples = list(empty_graph.triples((None, RDF.type, FAIR4ML.MLModel)))
    subject = type_triples[0][0]
    
    assert str(subject) == "https://specific-id.com/model"


@pytest.mark.integration
def test_build_model_triples_all_properties(empty_graph):
    """Integration test with all v1 properties."""
    model = {
        "https://schema.org/identifier": ["https://huggingface.co/test-model"],
        "https://schema.org/name": "test-model",
        "https://schema.org/url": "https://huggingface.co/test-model",
        "https://schema.org/author": "Test Author",
        "https://w3id.org/fair4ml/sharedBy": "Test Org",
        "https://schema.org/dateCreated": "2020-01-01T00:00:00",
        "https://schema.org/dateModified": "2020-06-01T00:00:00",
        "https://schema.org/datePublished": "2020-01-15T00:00:00",
        "https://schema.org/description": "Test description",
        "https://schema.org/discussionUrl": "https://example.com/discussions",
        "https://schema.org/archivedAt": "https://archive.org/test",
        "https://w3id.org/codemeta/readme": "https://example.com/README.md",
        "https://w3id.org/codemeta/issueTracker": "https://github.com/test/issues",
    }
    
    triples_added = build_model_triples(empty_graph, model)
    
    # Should have added all properties
    assert triples_added >= 13  # All properties + rdf:type
    
    # Verify key properties exist
    SCHEMA = Namespace("https://schema.org/")
    FAIR4ML = Namespace("https://w3id.org/fair4ml/")
    CODEMETA = Namespace("https://w3id.org/codemeta/")
    
    assert len(list(empty_graph.triples((None, RDF.type, FAIR4ML.MLModel)))) == 1
    assert len(list(empty_graph.triples((None, SCHEMA.name, None)))) >= 1
    assert len(list(empty_graph.triples((None, SCHEMA.url, None)))) >= 1
    assert len(list(empty_graph.triples((None, SCHEMA.author, None)))) >= 1
    assert len(list(empty_graph.triples((None, SCHEMA.description, None)))) >= 1
    assert len(list(empty_graph.triples((None, CODEMETA.readme, None)))) >= 1


# Mock tests for build_and_persist_models_rdf()

@pytest.mark.integration
def test_build_and_persist_models_rdf_file_not_found():
    """Test error handling for missing file."""
    from etl_loaders.hf_rdf_loader import build_and_persist_models_rdf
    from rdflib_neo4j import Neo4jStoreConfig
    
    config = Neo4jStoreConfig(
        uri="bolt://localhost:7687",
        database="neo4j",
        auth=("neo4j", "password"),
    )
    
    with pytest.raises(FileNotFoundError):
        build_and_persist_models_rdf("/nonexistent/path.json", config)


@pytest.mark.integration
def test_build_and_persist_models_rdf_invalid_json(tmp_path):
    """Test error handling for invalid JSON."""
    from etl_loaders.hf_rdf_loader import build_and_persist_models_rdf
    from rdflib_neo4j import Neo4jStoreConfig
    
    # Create invalid JSON file
    json_file = tmp_path / "invalid.json"
    json_file.write_text("not valid json")
    
    config = Neo4jStoreConfig(
        uri="bolt://localhost:7687",
        database="neo4j",
        auth=("neo4j", "password"),
    )
    
    with pytest.raises(json.JSONDecodeError):
        build_and_persist_models_rdf(str(json_file), config)

@pytest.mark.integration
@patch('etl_loaders.hf_rdf_loader.write_mlmodel_metadata_batch')
@patch('etl_loaders.hf_rdf_loader.open_graph')
@patch('etl_loaders.hf_rdf_loader.build_model_triples')
def test_build_and_persist_models_rdf_calls_batch_metadata(mock_build_triples, mock_open_graph, mock_write_batch, tmp_path):
    """Test that write_mlmodel_metadata_batch is called when write_metadata is True."""
    from etl_loaders.hf_rdf_loader import build_and_persist_models_rdf
    from rdflib_neo4j import Neo4jStoreConfig

    # Create a dummy JSON file with multiple models
    models = [
        {"https://schema.org/name": "model1"},
        {"https://schema.org/name": "model2"},
        {"https://schema.org/name": "model3"}
    ]
    json_file = tmp_path / "models.json"
    json_file.write_text(json.dumps(models))
    
    config = Mock(spec=Neo4jStoreConfig)
    mock_graph = Mock()
    mock_open_graph.return_value = mock_graph
    mock_build_triples.return_value = 5
    mock_write_batch.return_value = 3
    
    # Set batch size smaller than total models to force multiple batches
    result = build_and_persist_models_rdf(
        json_path=str(json_file),
        config=config,
        write_metadata=True,
        batch_size=2
    )
    
    assert result["models_processed"] == 3
    assert result["triples_added"] == 15 # 5 * 3
    assert result["metadata_relationships"] == 6 # 3 * 2 batches? No, mock_write_batch return value is summed.
    # If mock_write_batch returns 3, and it's called twice (once for 2 models, once for 1 model)
    # It should be 6.
    
    assert mock_write_batch.call_count == 2
    
    # Verify first batch
    args, _ = mock_write_batch.call_args_list[0]
    assert len(args[0]) == 2
    
    # Verify second batch
    args, _ = mock_write_batch.call_args_list[1]
    assert len(args[0]) == 1
