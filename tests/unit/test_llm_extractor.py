"""Core tests for the shared async LLM extractor, with a fake vLLM client (no server, no GPU)."""

import logging
import re
from types import SimpleNamespace
from unittest.mock import patch

from etl_extractors.common import llm as llm_package
from etl_extractors.common.llm import LLMConfig, LLMSchemaPropertyExtractor
from etl_extractors.common.llm import llm_extractor
from etl_extractors.hf import HFLLMSchemaPropertyExtractor
from etl_transformers.common.llm_keywords import _KEYWORD_QUESTION, extract_keywords_with_llm


def fake_load_llm(self):
    self.model_name = "fake-model"
    self.llm_len = 8192
    self.kv_cache_tokens = 100_000


def fake_load_tokenizer(self):
    self.tokenizer = SimpleNamespace(encode=str.split)


def no_vllm():
    """Builds extractors without contacting vLLM or downloading a tokenizer."""
    return patch.multiple(
        LLMSchemaPropertyExtractor, _load_llm=fake_load_llm, _load_tokenizer=fake_load_tokenizer
    )


def make_extractor(structured_outputs: bool) -> HFLLMSchemaPropertyExtractor:
    with no_vllm():
        return HFLLMSchemaPropertyExtractor(
            logger=logging.getLogger("test"),
            config=LLMConfig(structured_outputs=structured_outputs),
        )


def document_in(prompt: str) -> str:
    return re.search(r"<context> (.*) </context>", prompt, re.S).group(1)


def make_fake_client(answer):
    """A stand-in for AsyncOpenAI that replies answer(prompt) to every request."""

    class FakeCompletions:
        async def create(self, model, messages, max_tokens, extra_body, stream=False):
            text = answer(messages[-1]["content"])
            if not stream:
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])

            async def chunks():  # streamed in two pieces, like real tokens
                for piece in (text[:3], text[3:]):
                    yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=piece))])
            return chunks()

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    return FakeAsyncOpenAI


def test_extract_gives_each_document_its_own_answers():
    extractor = make_extractor(structured_outputs=False)
    props = ["fair4ml:description", "fair4ml:mlTask"]  # first is streamed (opener), second is a plain request
    documents = {"model-a": "card A", "model-b": "card B", "model-empty": "   "}

    def answer(prompt):  # "<document text> <property>"
        prop = next(p for p, q in extractor.questions.items() if q in prompt)
        return f"{document_in(prompt)} {prop}\n"

    with patch.object(llm_extractor, "AsyncOpenAI", make_fake_client(answer)):
        results = extractor.extract(documents, properties=props)

    assert results == {
        "model-a": {"fair4ml:description": "card A fair4ml:description", "fair4ml:mlTask": "card A fair4ml:mlTask"},
        "model-b": {"fair4ml:description": "card B fair4ml:description", "fair4ml:mlTask": "card B fair4ml:mlTask"},
        "model-empty": {"fair4ml:description": "NA", "fair4ml:mlTask": "NA"},
    }


def test_parse_value_plain_text_and_structured_outputs():
    plain = make_extractor(structured_outputs=False)
    assert plain._parse_value("  Transformer\n") == "Transformer"
    assert plain._parse_value("   ") is None

    structured = make_extractor(structured_outputs=True)
    assert structured._parse_value('{"result": "Transformer"}') == "Transformer"
    assert structured._parse_value('{"result": ["en", "de"]}') == '["en", "de"]'
    assert structured._parse_value('{"result": "Transf') is None  # truncated
    assert structured._parse_value('{"other": "x"}') is None


def test_extract_keywords_with_llm_uses_keywords_template():
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return "Text Classification, nlp, transformers\n"

    with no_vllm(), \
         patch.object(llm_extractor, "AsyncOpenAI", make_fake_client(answer)), \
         patch.object(llm_package, "LLMConfig", lambda: LLMConfig(structured_outputs=False)):
        keywords = extract_keywords_with_llm(
            {"kaggle/model-a": "card A", "kaggle/model-empty": "  "},
            existing_refs={"text classification"},
        )

    assert keywords == {
        "kaggle/model-a": ["text classification", "nlp", "transformers"],  # catalog spelling reused
        "kaggle/model-empty": [],
    }
    assert len(prompts) == 1  # the empty text is never sent
    assert document_in(prompts[0]) == "card A"
    assert _KEYWORD_QUESTION in prompts[0]
    assert "SHORT KEYWORDS ONLY" in prompts[0]
