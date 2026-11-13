"""Unit tests for LLM keyword parsing."""

from __future__ import annotations

from etl_transformers.common.llm_keywords import (
    parse_llm_keywords,
    predictions_from_llm_output,
)


def test_parse_comma_separated_keywords():
    assert parse_llm_keywords("text classification, NLP, transformers") == [
        "text classification",
        "NLP",
        "transformers",
    ]


def test_parse_rejects_na_and_long_sentences():
    assert parse_llm_keywords("NA") == []
    assert parse_llm_keywords(
        "This model is a very long description that should not become a keyword"
    ) == []


def test_parse_reuses_existing_catalog_spelling():
    existing = {"nlp", "text classification"}
    assert parse_llm_keywords(
        "NLP, Text Classification, vision",
        existing_refs=existing,
    ) == ["nlp", "text classification", "vision"]


def test_predictions_from_llm_output():
    parsed = {
        "owner/a": {"schema:keywords": "nlp, classification"},
        "owner/b": {"schema:keywords": "NA"},
    }
    assert predictions_from_llm_output(parsed) == {
        "owner/a": ["nlp", "classification"],
        "owner/b": [],
    }
