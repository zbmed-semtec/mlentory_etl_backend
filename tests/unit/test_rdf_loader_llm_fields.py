"""Tests for LLM schema fields in RDF loader."""

from rdflib import Graph, Literal, Namespace
from rdflib.namespace import RDF

from etl_loaders.rdf_loader import build_model_triples


def test_build_model_triples_includes_llm_string_properties():
    graph = Graph()
    model = {
        "https://schema.org/name": "test-model",
        "https://schema.org/url": "https://huggingface.co/test-model",
        "https://w3id.org/fair4ml/domain": "healthcare",
        "https://w3id.org/insilico/dataSplits": "80/10/10",
        "https://w3id.org/insilico/adaptionTechniques": "fine-tuning",
    }
    build_model_triples(graph, model)

    FAIR4ML = Namespace("https://w3id.org/fair4ml/")
    INSILICO = Namespace("https://w3id.org/insilico/")

    assert len(list(graph.triples((None, RDF.type, FAIR4ML.MLModel)))) == 1
    assert list(graph.objects(None, FAIR4ML.domain)) == [Literal("healthcare")]
    assert list(graph.objects(None, INSILICO.dataSplits)) == [Literal("80/10/10")]
    assert list(graph.objects(None, INSILICO.adaptionTechniques)) == [Literal("fine-tuning")]
