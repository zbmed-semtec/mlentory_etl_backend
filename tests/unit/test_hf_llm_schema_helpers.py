"""
Unit tests for HF LLM schema extraction helpers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from etl.config import get_hf_config
from etl_extractors.hf.hf_card_preprocessor import preprocess_card_for_llm
from etl_extractors.hf.hf_llm_prompt_builder import LLMSchemaPromptBuilder
from etl_extractors.hf.hf_llm_response_parser import parse_llm_property_response


PROJECT_ROOT = Path(__file__).resolve().parents[2]
METADATA_DIR = PROJECT_ROOT / "config" / "hf_schema_extraction"

SAMPLE_CARD = """---
license: apache-2.0
---

# My Model

## Model Description

Llama 3.1 is an auto-regressive language model that uses an optimized transformer architecture.

```python
model = AutoModel.from_pretrained("org/model")
```

## Training

Supervised fine-tuning (SFT) and reinforcement learning with human feedback (RLHF).

## Data Splits

80/10/10 train/validation/test split with stratified sampling.
"""


class TestPreprocessCardForLlm:
    def test_strips_code_blocks_and_keeps_headings(self):
        text = preprocess_card_for_llm(SAMPLE_CARD)

        assert "Model Description" in text
        assert "optimized transformer architecture" in text
        assert "Supervised fine-tuning" in text
        assert "80/10/10" in text
        assert "AutoModel.from_pretrained" not in text

    def test_empty_card_returns_empty_string(self):
        assert preprocess_card_for_llm("") == ""
        assert preprocess_card_for_llm("   ") == ""


class TestParseLlmPropertyResponse:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ('{"result": "General purpose"}', "General purpose"),
            ('```json\n{"result": "Transformer"}\n```', "Transformer"),
            ('{"result": "NA"}', None),
            ('{"result": "na"}', None),
            ("", None),
            ("not json at all", None),
        ],
    )
    def test_parse_variants(self, raw, expected):
        assert parse_llm_property_response(raw) == expected


class TestLLMSchemaPromptBuilder:
    @pytest.fixture
    def builder(self) -> LLMSchemaPromptBuilder:
        prompt_builder = LLMSchemaPromptBuilder()
        prompt_builder.load_metadata(METADATA_DIR)
        return prompt_builder

    def test_loads_six_properties(self, builder: LLMSchemaPromptBuilder):
        assert len(builder.property_names) == 6
        assert "fair4ml:description" in builder.property_names
        assert "fair4ml:mlTask" in builder.property_names

    def test_build_instruction_includes_context(self, builder: LLMSchemaPromptBuilder):
        card_text = "A text-generation model for finance."
        instruction = builder.build_instruction("fair4ml:domain", card_text)

        assert "<context>" in instruction
        assert card_text in instruction
        assert "PROPERTY_DESCRIPTION" not in instruction
        assert "RETRIEVED_CONTEXT" not in instruction

    def test_build_property_prompt_messages(self, builder: LLMSchemaPromptBuilder):
        prompt = builder.build_property_prompt(
            "fair4ml:modelArchitecture",
            "Uses a decoder-only Transformer.",
        )
        messages = prompt.to_chat_messages()

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "decoder-only Transformer" in messages[1]["content"]

    def test_build_all_property_prompts_count(self, builder: LLMSchemaPromptBuilder):
        prompts = builder.build_all_property_prompts("Sample card text.")
        assert len(prompts) == 6

    def test_default_metadata_dir_from_config(self):
        cfg = get_hf_config()
        assert Path(cfg.llm_schema_metadata_dir).is_dir()
        assert (Path(cfg.llm_schema_metadata_dir) / "llm_questions.csv").is_file()
