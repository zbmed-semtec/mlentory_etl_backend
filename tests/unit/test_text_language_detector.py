"""Tests for shared text language detection helpers."""

import pytest

from etl_extractors.common.text_language_detector import (
    detect_language_codes,
    strip_markdown_frontmatter,
)


def test_strip_model_card_frontmatter_removes_yaml_block():
    text = "---\nlicense: apache-2.0\n---\n\n# Title\n\nHello world."
    assert strip_markdown_frontmatter(text).startswith("# Title")


def test_strip_model_card_frontmatter_empty():
    assert strip_markdown_frontmatter("") == ""


def test_detect_readme_language_codes_english_sentence():
    pytest.importorskip("lingua")
    text = (
        "This model performs natural language understanding tasks on English text "
        "for classification and regression benchmarks."
    )
    codes = detect_language_codes(text, min_confidence=0.75, max_languages=5)
    assert "en" in codes
    assert len(codes) <= 5


def test_detect_readme_language_codes_short_text_still_runs():
    pytest.importorskip("lingua")
    codes = detect_language_codes("Hello world.", min_confidence=0.75, max_languages=5)
    assert isinstance(codes, list)
    assert len(codes) <= 5


def test_constants_document_thresholds():
    codes = detect_language_codes("English text", min_confidence=0.75, max_languages=5)
    assert isinstance(codes, list)
