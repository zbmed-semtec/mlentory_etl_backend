"""Unit tests for wiring Kaggle LLM schema extraction into transform merge."""

from __future__ import annotations

from etl.assets.kaggle_transformation import (
    inherit_parent_catalog_fields,
    merge_kaggle_partial_schemas,
)


def test_merge_applies_llm_mltask_when_catalog_has_none():
    basic = {
        "owner/model": {
            "_model_id": "owner/model",
            "name": "model",
            "identifier": ["iri:model"],
            "intendedUse": "A text classifier for reviews.",
        }
    }
    llm = {
        "owner/model": {
            "fair4ml:mlTask": "text classification",
            "fair4ml:description": "Classifies product reviews.",
            "_extraction_metadata": {
                "fair4ml:mlTask": {
                    "extraction_method": "LLM_schema_extraction",
                    "confidence": 0.85,
                    "source_field": "card",
                }
            },
        }
    }

    merged = merge_kaggle_partial_schemas(
        basic_by_id=basic,
        entity_linking_data={},
        all_model_ids=["owner/model"],
        llm_by_model_id=llm,
    )

    assert len(merged) == 1
    _model_id, data = merged[0]
    assert _model_id == "owner/model"
    assert data["mlTask"] == ["text classification"]
    assert data["description"] == "Classifies product reviews."
    assert data["extraction_metadata"]["mlTask"]["extraction_method"] == (
        "LLM_schema_extraction"
    )


def test_merge_keeps_existing_kaggle_inlanguage_iris():
    existing_lang = ["https://w3id.org/mlentory/kaggle/lang/en"]
    basic = {
        "owner/model": {
            "_model_id": "owner/model",
            "name": "model",
            "identifier": ["iri:model"],
        }
    }
    linking = {
        "owner/model": {
            "inLanguage": existing_lang,
            "keywords": [],
            "licenses": [],
            "frameworks": [],
            "sharedby": [],
            "sources": [],
        }
    }
    llm = {
        "owner/model": {
            "schema:inLanguage": "en",
            "fair4ml:mlTask": "image classification",
        }
    }

    _model_id, data = merge_kaggle_partial_schemas(
        basic_by_id=basic,
        entity_linking_data=linking,
        all_model_ids=["owner/model"],
        llm_by_model_id=llm,
    )[0]

    assert data["inLanguage"] == existing_lang
    assert data["mlTask"] == ["image classification"]


def test_variation_inherits_parent_mltask():
    mapped = {"name": "pytorch/v1", "extraction_metadata": {}}
    parent = {
        "mlTask": ["text generation"],
        "description": "A generative model.",
        "extraction_metadata": {
            "mlTask": {
                "extraction_method": "LLM_schema_extraction",
                "confidence": 0.85,
            }
        },
    }

    inherit_parent_catalog_fields(mapped, parent)

    assert mapped["mlTask"] == ["text generation"]
    assert mapped["description"] == "A generative model."
    assert mapped["extraction_metadata"]["mlTask"]["extraction_method"] == (
        "LLM_schema_extraction"
    )
