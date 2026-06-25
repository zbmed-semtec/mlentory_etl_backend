"""
Unit tests for HF LLM schema client and extractor (mocked vLLM).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from etl_extractors.hf.hf_llm_schema_client import VLLMSchemaClient, VLLMSchemaClientError
from etl_extractors.hf.hf_llm_schema_extractor import EXTRACTION_METADATA_KEY, HFLLMSchemaExtractor
from etl_extractors.hf.hf_llm_prompt_builder import LLMSchemaPromptBuilder


PROJECT_ROOT = Path(__file__).resolve().parents[2]
METADATA_DIR = PROJECT_ROOT / "config" / "hf_schema_extraction"

SAMPLE_CARD = """## Overview
Llama 3.1 is an auto-regressive language model that uses an optimized transformer architecture.
It is intended for general-purpose assistant chat.
"""


def _chat_response(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class TestVLLMSchemaClient:
    def test_chat_completion_returns_assistant_content(self):
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.post.return_value = httpx.Response(
            200,
            json=_chat_response('{"result": "Transformer"}'),
            request=httpx.Request("POST", "http://vllm:8000/v1/chat/completions"),
        )

        client = VLLMSchemaClient(
            base_url="http://vllm:8000",
            model_name="test-model",
            client=mock_http,
        )
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ]

        assert client.chat_completion(messages) == '{"result": "Transformer"}'
        mock_http.post.assert_called_once()
        payload = mock_http.post.call_args.kwargs["json"]
        assert payload["model"] == "test-model"
        assert payload["messages"] == messages

    def test_chat_completion_raises_on_http_error(self):
        mock_http = MagicMock(spec=httpx.Client)
        mock_http.post.return_value = httpx.Response(
            500,
            request=httpx.Request("POST", "http://vllm:8000/v1/chat/completions"),
        )

        client = VLLMSchemaClient(
            base_url="http://vllm:8000",
            model_name="test-model",
            max_retries=1,
            client=mock_http,
        )

        with pytest.raises(VLLMSchemaClientError):
            client.chat_completion([{"role": "user", "content": "hi"}])


class TestHFLLMSchemaExtractor:
    @pytest.fixture
    def prompt_builder(self) -> LLMSchemaPromptBuilder:
        builder = LLMSchemaPromptBuilder()
        builder.load_metadata(METADATA_DIR)
        return builder

    def test_extract_single_model_single_property_via_mock_client(
        self,
        prompt_builder: LLMSchemaPromptBuilder,
    ):
        mock_client = MagicMock()
        mock_client.model_name = "mock-model"
        mock_client.chat_completion.return_value = '{"result": "General purpose"}'

        extractor = HFLLMSchemaExtractor(
            client=mock_client,
            prompt_builder=prompt_builder,
            preprocess_cards=False,
            concurrency=1,
        )
        extractor.prompt_builder.questions = {
            "fair4ml:domain": prompt_builder.questions["fair4ml:domain"],
        }
        extractor.prompt_builder.prop_template_type_map = {
            "fair4ml:domain": prompt_builder.prop_template_type_map["fair4ml:domain"],
        }

        results = extractor.extract_properties(
            {"org/test-model": SAMPLE_CARD},
        )

        assert mock_client.chat_completion.call_count == 1
        model_result = results["org/test-model"]
        assert model_result["fair4ml:domain"] == "General purpose"
        assert EXTRACTION_METADATA_KEY in model_result
        assert model_result[EXTRACTION_METADATA_KEY]["fair4ml:domain"]["extraction_method"] == (
            "LLM_schema_extraction"
        )

    def test_extract_all_six_properties_for_one_model(
        self,
        prompt_builder: LLMSchemaPromptBuilder,
    ):
        responses = [
            '{"result": "A helpful chat model."}',
            '{"result": "Transformer"}',
            '{"result": "General purpose"}',
            '{"result": "NA"}',
            '{"result": "Supervised fine-tuning (SFT)"}',
            '{"result": "text generation"}',
        ]
        mock_client = MagicMock()
        mock_client.model_name = "mock-model"
        mock_client.chat_completion.side_effect = responses

        extractor = HFLLMSchemaExtractor(
            client=mock_client,
            prompt_builder=prompt_builder,
            preprocess_cards=True,
            concurrency=1,
        )

        results = extractor.extract_properties({"org/test-model": SAMPLE_CARD})
        model_result = results["org/test-model"]

        assert mock_client.chat_completion.call_count == 6
        assert model_result["fair4ml:description"] == "A helpful chat model."
        assert model_result["fair4ml:modelArchitecture"] == "Transformer"
        assert model_result["fair4ml:domain"] == "General purpose"
        assert model_result["insilico:dataSplits"] is None
        assert model_result["insilico:adaptionTechniques"] == "Supervised fine-tuning (SFT)"
        assert model_result["fair4ml:mlTask"] == "text generation"

    def test_empty_card_skips_llm_calls(
        self,
        prompt_builder: LLMSchemaPromptBuilder,
    ):
        mock_client = MagicMock()
        mock_client.model_name = "mock-model"

        extractor = HFLLMSchemaExtractor(
            client=mock_client,
            prompt_builder=prompt_builder,
            preprocess_cards=True,
            concurrency=1,
        )

        results = extractor.extract_properties({"org/empty": "   "})
        model_result = results["org/empty"]

        mock_client.chat_completion.assert_not_called()
        assert model_result["fair4ml:description"] is None

    def test_concurrent_property_extraction_uses_thread_pool(
        self,
        prompt_builder: LLMSchemaPromptBuilder,
    ):
        mock_client = MagicMock()
        mock_client.model_name = "mock-model"
        mock_client.chat_completion.return_value = '{"result": "ok"}'

        extractor = HFLLMSchemaExtractor(
            client=mock_client,
            prompt_builder=prompt_builder,
            preprocess_cards=False,
            concurrency=4,
        )

        results = extractor.extract_properties({"org/test-model": SAMPLE_CARD})
        model_result = results["org/test-model"]

        assert mock_client.chat_completion.call_count == len(prompt_builder.property_names)
        for property_name in prompt_builder.property_names:
            assert model_result[property_name] == "ok"
