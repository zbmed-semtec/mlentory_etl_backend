"""
Unit tests for LLM schema property mapping into FAIR4ML partial dicts.
"""

from __future__ import annotations

from etl_transformers.hf.map_llm_schema_properties import map_llm_schema_properties


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

    def test_na_like_values_not_mapped_for_optional_fields(self):
        record = {
            "fair4ml:domain": "Healthcare",
            "insilico:dataSplits": None,
        }
        result = map_llm_schema_properties(record, {})

        assert result["domain"] == "Healthcare"
        assert "dataSplits" not in result

    def test_empty_record_returns_empty_dict(self):
        assert map_llm_schema_properties({}, {"description": "x"}) == {}
