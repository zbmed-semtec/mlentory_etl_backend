"""
Unit tests for LLM schema property mapping into FAIR4ML partial dicts.
"""

from __future__ import annotations

from etl_transformers.hf.map_llm_schema_properties import (
    map_llm_schema_properties,
    parse_llm_inlanguage_codes,
)
from etl_transformers.common.llm_inlanguage import predictions_from_llm_output
from etl_extractors.hf.hf_helper import HFHelper


def _sample_llm_record() -> dict:
    return {
        "fair4ml:description": "A helpful chat model.",
        "fair4ml:modelArchitecture": "Transformer",
        "fair4ml:domain": "General purpose",
        "insilico:dataSplits": "NA",
        "insilico:adaptionTechniques": "Supervised fine-tuning (SFT)",
        "fair4ml:mlTask": "text generation",
        "_extraction_metadata": {
            "fair4ml:description": {
                "extraction_method": "LLM_schema_extraction",
                "confidence": 0.85,
                "source_field": "card",
                "notes": "model=test",
            }
        },
    }


class TestMapLlmSchemaProperties:
    def test_description_overrides_existing(self):
        existing = {"description": "raw readme text"}
        result = map_llm_schema_properties(_sample_llm_record(), existing)

        assert result["description"] == "A helpful chat model."
        assert result["abstract"] == "raw readme text"

    def test_description_override_skips_abstract_when_unchanged(self):
        existing = {"description": "A helpful chat model."}
        result = map_llm_schema_properties(_sample_llm_record(), existing)

        assert result["description"] == "A helpful chat model."
        assert "abstract" not in result

    def test_description_override_preserves_existing_abstract(self):
        existing = {
            "description": "raw readme text",
            "abstract": "already archived",
        }
        result = map_llm_schema_properties(_sample_llm_record(), existing)

        assert result["description"] == "A helpful chat model."
        assert "abstract" not in result

    def test_ml_task_kept_when_existing_tasks_present(self):
        existing = {"mlTask": ["text-generation"]}
        result = map_llm_schema_properties(_sample_llm_record(), existing)

        assert "mlTask" not in result

    def test_ml_task_used_when_existing_tasks_empty(self):
        existing = {"mlTask": []}
        result = map_llm_schema_properties(_sample_llm_record(), existing)

        assert result["mlTask"] == ["text generation"]

    def test_architecture_appended_to_model_category(self):
        existing = {"modelCategory": ["llm"]}
        result = map_llm_schema_properties(_sample_llm_record(), existing)

        assert result["modelCategory"] == ["llm", "Transformer"]

    def test_na_values_skipped(self):
        record = {
            "fair4ml:domain": "Healthcare",
            "insilico:dataSplits": "NA",
            "fair4ml:modelArchitecture": "NA",
        }
        result = map_llm_schema_properties(record, {})

        assert result["domain"] == "Healthcare"
        assert "dataSplits" not in result
        assert "modelCategory" not in result

    def test_empty_record_returns_empty_dict(self):
        assert map_llm_schema_properties({}, {"description": "x"}) == {}

    def test_inlanguage_codes_become_language_iris(self):
        record = {"schema:inLanguage": "en, zh"}
        result = map_llm_schema_properties(record, {})

        assert result["inLanguage"] == [
            HFHelper.generate_mlentory_entity_hash_id("Language", "en"),
            HFHelper.generate_mlentory_entity_hash_id("Language", "zh"),
        ]
        assert result["extraction_metadata"]["inLanguage"]["extraction_method"] == (
            "LLM_schema_extraction"
        )

    def test_inlanguage_names_and_na_are_normalized(self):
        record = {"schema:inLanguage": "English and NA"}
        result = map_llm_schema_properties(record, {})

        assert result["inLanguage"] == [
            HFHelper.generate_mlentory_entity_hash_id("Language", "en"),
        ]

    def test_inlanguage_na_skipped(self):
        result = map_llm_schema_properties({"schema:inLanguage": "NA"}, {})
        assert "inLanguage" not in result


class TestParseLlmInlanguageCodes:
    def test_comma_separated_iso_codes(self):
        assert parse_llm_inlanguage_codes("en, zh, de") == ["en", "zh", "de"]

    def test_language_names(self):
        assert parse_llm_inlanguage_codes("English, Chinese") == ["en", "zh"]

    def test_empty_and_na(self):
        assert parse_llm_inlanguage_codes("NA") == []
        assert parse_llm_inlanguage_codes("") == []
        assert parse_llm_inlanguage_codes(None) == []


class TestPredictionsFromLlmOutput:
    def test_converts_codes_to_lingua_shaped_predictions(self):
        parsed = {
            "model-a": {"schema:inLanguage": "en, zh"},
            "model-b": {"schema:inLanguage": "NA"},
        }
        detected = predictions_from_llm_output(parsed)
        assert detected["model-a"] == [
            {"code": "en", "confidence": 0.85},
            {"code": "zh", "confidence": 0.85},
        ]
        assert detected["model-b"] == []
