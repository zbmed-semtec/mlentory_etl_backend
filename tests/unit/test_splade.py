"""SPLADE card text, encoder limits, and the search endpoint."""

import asyncio

from api.schemas.responses import VectorModelListItem
from api.routers import models as models_router
from etl_loaders.splade_encoder import (
    DOCUMENT_TERMS,
    QUERY_TERMS,
    get_splade_encoder,
    sanitize_feature_name,
)
from etl_loaders.vector_index_manager import (
    build_improved_searchable_text,
    build_splade_searchable_text,
)

_BERT = {
    "name": "bert-base-uncased",
    "shared_by": "google-bert",
    "ml_tasks": ["fill-mask"],
    "keywords": ["pytorch", "transformers"],
    "datasets": ["bookcorpus", "wikipedia"],
    "domain": "natural language processing",
    "architecture": "Bert",
    "modalities": ["text"],
    "description": "BERT base model, uncased.",
}

_IMPROVED = "\n".join(
    [
        "name: bert-base-uncased",
        "author: google-bert",
        "task: fill-mask",
        "keywords: pytorch, transformers",
        "datasets: bookcorpus, wikipedia",
        "domain: natural language processing",
        "architecture: Bert",
        "modalities: text",
        "description: BERT base model, uncased.",
    ]
)

_SPLADE = (
    "bert-base-uncased. google-bert. fill-mask. pytorch, transformers. "
    "bookcorpus, wikipedia. natural language processing. Bert. text. "
    "BERT base model, uncased."
)


def test_bert_card_matches_the_values_only_string():
    assert build_splade_searchable_text(_BERT) == _SPLADE
    assert build_improved_searchable_text(_BERT) == _IMPROVED


def test_missing_fields_leave_no_empty_separators():
    text = build_splade_searchable_text(
        {
            "name": "only-name",
            "shared_by": "Unknown",
            "keywords": [],
            "description": "A model.",
        }
    )
    assert text == "only-name. A model."
    assert ". ." not in text


def test_improved_card_is_unchanged_for_the_same_model():
    assert build_improved_searchable_text(_BERT) == _IMPROVED
    partial = {"name": "only-name", "description": "A model."}
    assert build_improved_searchable_text(partial) == "name: only-name\ndescription: A model."


def test_encoder_prunes_sanitizes_and_keeps_positive_weights():
    encoder = get_splade_encoder()
    document = encoder.encode_documents([_SPLADE])[0]
    query = encoder.encode_query("text classification models")
    assert document
    assert query
    assert len(document) <= DOCUMENT_TERMS
    assert len(query) <= QUERY_TERMS
    for weights in (document, query):
        assert all(weight > 0 for weight in weights.values())
        assert all("." not in key and key.strip() for key in weights)
    assert sanitize_feature_name(".") is None
    assert sanitize_feature_name("bert") == "bert"


def test_splade_endpoint_returns_db_identifier_and_respects_limit():
    import api.services.splade_search_service as service_module

    captured = {}

    class FakeEncoder:
        @staticmethod
        def encode_query(text: str):
            return {"bert": 1.5}

    def fake_search(**kwargs):
        captured["body"] = kwargs["body"]
        size = kwargs["body"]["size"]
        hits = []
        for index in range(size):
            hits.append(
                {
                    "_id": str(index),
                    "_score": 12.5 - index,
                    "_source": {
                        "name": f"model-{index}",
                        "db_identifier": [
                            f"https://w3id.org/mlentory/mlentory_graph/model-{index}"
                        ],
                        "source": "Hugging Face",
                        "splade_searchable_text": f"model-{index}",
                    },
                }
            )
        return {"hits": {"hits": hits, "total": {"value": 25}}, "aggregations": {}}

    original_get = service_module.get_splade_encoder
    original_search = models_router.splade_search_service.client.search
    service_module.get_splade_encoder = lambda: FakeEncoder()
    models_router.splade_search_service.client.search = fake_search
    try:
        result = asyncio.run(
            models_router.splade_search(
                query="bert",
                filters="{}",
                page=1,
                limit=20,
                facets='["mlTask"]',
                facet_size=20,
                facet_query="{}",
            )
        )
    finally:
        service_module.get_splade_encoder = original_get
        models_router.splade_search_service.client.search = original_search

    models = result["models"]
    assert len(models) == 20
    assert captured["body"]["size"] == 20
    assert all(model.db_identifier for model in models)
    assert models[0].db_identifier == [
        "https://w3id.org/mlentory/mlentory_graph/model-0"
    ]
    assert models[0].score == 12.5
    assert isinstance(models[0], VectorModelListItem)
