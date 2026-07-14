"""Tests for entity-link extraction metadata helpers."""

from etl_transformers.common.entity_link_metadata import (
    AI4LIFE_ENTITY_LINK_METADATA,
    HF_ENTITY_LINK_METADATA,
    apply_entity_link_extraction_metadata,
)


def test_hf_entity_link_metadata_covers_expected_fields():
    expected = {
        "license",
        "source",
        "evaluatedOn",
        "keywords",
        "baseModel",
        "supportedLanguages",
        "inLanguage",
        "mlTask",
        "sharedBy",
    }
    assert expected == set(HF_ENTITY_LINK_METADATA.keys())
    assert HF_ENTITY_LINK_METADATA["license"]["extraction_method"] == "SPDX_API"
    assert HF_ENTITY_LINK_METADATA["mlTask"]["extraction_method"] == "catalog_csv"


def test_ai4life_entity_link_metadata_covers_expected_fields():
    expected = {
        "license",
        "source",
        "evaluatedOn",
        "keywords",
        "mlTask",
        "sharedBy",
        "inLanguage",
    }
    assert expected == set(AI4LIFE_ENTITY_LINK_METADATA.keys())
    assert AI4LIFE_ENTITY_LINK_METADATA["license"]["extraction_method"] == "Hypha API"
    assert AI4LIFE_ENTITY_LINK_METADATA["mlTask"]["extraction_method"] == "ai4life_task_identifier"


def test_apply_hf_entity_link_metadata_on_merge_shape():
    merged = {
        "name": "test-model",
        "extraction_metadata": {
            "name": {
                "extraction_method": "Parsed_from_HF_dataset",
                "confidence": 1.0,
                "source_field": "modelId",
            }
        },
        "license": "https://w3id.org/mlentory/mlentory_graph/license-1",
        "mlTask": ["https://w3id.org/mlentory/mlentory_graph/task-1"],
        "keywords": ["https://w3id.org/mlentory/mlentory_graph/kw-1"],
    }

    apply_entity_link_extraction_metadata(
        merged,
        "hf",
        ["license", "mlTask", "keywords"],
    )

    meta = merged["extraction_metadata"]
    assert meta["name"]["extraction_method"] == "Parsed_from_HF_dataset"
    assert meta["license"]["extraction_method"] == "SPDX_API"
    assert meta["mlTask"]["extraction_method"] == "catalog_csv"
    assert meta["keywords"]["extraction_method"] == "Wikidata API + Semantic Search"


def test_apply_ai4life_entity_link_metadata_on_merge_shape():
    merged = {
        "name": "ai4life-model",
        "extraction_metadata": {
            "name": {
                "extraction_method": "Parsed_from_AI4Life_models_json",
                "confidence": 1.0,
                "source_field": "name",
            }
        },
        "license": "https://w3id.org/mlentory/mlentory_graph/license-1",
        "mlTask": ["https://w3id.org/mlentory/mlentory_graph/task-1"],
    }

    apply_entity_link_extraction_metadata(merged, "ai4life", ["license", "mlTask"])

    meta = merged["extraction_metadata"]
    assert meta["license"]["extraction_method"] == "Hypha API"
    assert meta["mlTask"]["extraction_method"] == "ai4life_task_identifier"
