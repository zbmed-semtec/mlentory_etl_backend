"""Tests for LLM schema fields in Elasticsearch index loader."""

from etl_loaders.index_loader import build_model_document
from etl_loaders.vector_index_manager import (
    _extracted_data_from_indexed_model,
    VectorIndexManager,
)


def test_build_model_document_includes_llm_fields():
    model = {
        "https://schema.org/identifier": ["https://w3id.org/mlentory/model/hf/test-model"],
        "https://schema.org/name": "test-model",
        "https://schema.org/description": "LLM summary",
        "https://w3id.org/fair4ml/domain": "healthcare",
        "https://w3id.org/fair4ml/modelCategory": ["transformer"],
        "https://w3id.org/insilico/dataSplits": "80/10/10 train/val/test",
        "https://w3id.org/insilico/adaptionTechniques": "fine-tuning",
        "https://w3id.org/fair4ml/parameterCount": "7B",
    }
    doc = build_model_document(model, "hf_models", {})
    assert doc.domain == "healthcare"
    assert doc.model_category == ["transformer"]
    assert doc.data_splits == "80/10/10 train/val/test"
    assert doc.adaption_techniques == "fine-tuning"
    assert doc.parameter_count == "7B"
    assert doc.db_identifier == ["https://w3id.org/mlentory/model/hf/test-model"]
    assert doc.mlentory_id
    assert doc.meta.id == doc.mlentory_id


def test_build_model_document_sets_mlentory_graph_id():
    graph_id = "https://w3id.org/mlentory/mlentory_graph/abc123"
    model = {
        "https://schema.org/identifier": [
            "https://doi.org/10.1234/example",
            graph_id,
        ],
        "https://schema.org/name": "test-model",
    }
    doc = build_model_document(model, "hf_models", {})
    assert doc.mlentory_id == graph_id
    assert doc.db_identifier == [
        "https://doi.org/10.1234/example",
        graph_id,
    ]
    assert doc.meta.id == graph_id


def test_extracted_data_from_indexed_model():
    model_data = {
        "name": "test-model",
        "domain": "nlp",
        "model_category": ["bert", "encoder"],
        "adaption_techniques": "pre-training",
        "data_splits": "train/test",
        "parameter_count": "110M",
    }
    extracted = _extracted_data_from_indexed_model(model_data)
    assert extracted["domain"] == "nlp"
    assert extracted["architecture"] == "bert, encoder"
    assert extracted["trainingType"] == "pre-training"
    assert extracted["data_splits"] == "train/test"


def test_prepare_searchable_text_includes_llm_fields():
    manager = VectorIndexManager(es_client=None, index_name="hf_models")
    model_data = {
        "name": "test-model",
        "description": "A test model",
        "domain": "computer vision",
        "model_category": ["cnn"],
        "adaption_techniques": "transfer learning",
        "data_splits": "70/30",
    }
    text = manager.prepare_searchable_text(
        model_data, _extracted_data_from_indexed_model(model_data)
    )
    assert "computer vision" in text
    assert "cnn" in text
    assert "transfer learning" in text
    assert "70/30" in text
