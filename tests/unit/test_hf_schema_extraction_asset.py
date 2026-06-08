"""
Unit tests for HF schema extraction Dagster asset helpers.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from etl.assets.hf_schema_extraction import (
    build_preprocessed_model_cards,
    run_llm_schema_extraction,
)
from etl_extractors.hf.hf_llm_schema_extractor import EXTRACTION_METADATA_KEY, HFLLMSchemaExtractor


SAMPLE_MODELS = [
    {
        "modelId": "org/demo-model",
        "card": """# Demo

## Description
A text-generation model.

```python
print("skip me")
```

## Training
Fine-tuned on custom data.
""",
    }
]


def test_build_preprocessed_model_cards_from_json(tmp_path: Path):
    models_path = tmp_path / "hf_models_with_ancestors.json"
    with open(models_path, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_MODELS, f)

    result = build_preprocessed_model_cards(models_path)

    assert "org/demo-model" in result
    text = result["org/demo-model"]
    assert "text-generation model" in text
    assert 'print("skip me")' not in text


@patch("etl.assets.hf_schema_extraction.HFLLMSchemaExtractor")
def test_run_llm_schema_extraction_uses_preprocessed_cards(mock_extractor_cls):
    mock_extractor = MagicMock()
    mock_extractor.extract_properties.return_value = {"org/a": {"fair4ml:domain": "finance"}}
    mock_extractor.client.close = MagicMock()
    mock_extractor_cls.return_value = mock_extractor

    cards = {"org/a": "already preprocessed"}
    result = run_llm_schema_extraction(cards)

    mock_extractor_cls.assert_called_once_with(preprocess_cards=False)
    mock_extractor.extract_properties.assert_called_once_with(cards)
    mock_extractor.client.close.assert_called_once()
    assert result["org/a"]["fair4ml:domain"] == "finance"


def test_extractor_continues_when_single_model_raises(prompt_builder_from_config):
    prompt_builder = prompt_builder_from_config
    mock_client = MagicMock()
    mock_client.model_name = "mock-model"

    def boom(model_id, card_text):
        if model_id == "org/bad":
            raise RuntimeError("boom")
        return {"fair4ml:domain": "ok", EXTRACTION_METADATA_KEY: {}}

    extractor = HFLLMSchemaExtractor(
        client=mock_client,
        prompt_builder=prompt_builder,
        preprocess_cards=False,
    )
    extractor._extract_model_properties = MagicMock(side_effect=boom)

    results = extractor.extract_properties(
        {"org/good": "card", "org/bad": "card"},
    )

    assert results["org/good"]["fair4ml:domain"] == "ok"
    assert results["org/bad"]["fair4ml:domain"] is None
    assert "model_extraction_error" in results["org/bad"][EXTRACTION_METADATA_KEY]["fair4ml:domain"]["notes"]


@pytest.fixture
def prompt_builder_from_config():
    from pathlib import Path

    from etl_extractors.hf.hf_llm_prompt_builder import LLMSchemaPromptBuilder

    metadata_dir = Path(__file__).resolve().parents[2] / "config" / "hf_schema_extraction"
    builder = LLMSchemaPromptBuilder()
    builder.load_metadata(metadata_dir)
    return builder
