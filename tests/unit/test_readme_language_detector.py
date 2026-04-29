"""Tests for readme / model-card language detection helpers."""

import pytest

from etl_extractors.hf.readme_language_detector import (
    README_LANGUAGE_MAX,
    README_LANGUAGE_MIN_CONFIDENCE,
    detect_readme_language_codes,
    strip_model_card_frontmatter,
)


def test_strip_model_card_frontmatter_removes_yaml_block():
    text = "---\nlicense: apache-2.0\n---\n\n# Title\n\nHello world."
    assert strip_model_card_frontmatter(text).startswith("# Title")


def test_strip_model_card_frontmatter_empty():
    assert strip_model_card_frontmatter("") == ""


def test_detect_readme_language_codes_english_sentence():
    pytest.importorskip("lingua")
    text = (
        "This model performs natural language understanding tasks on English text "
        "for classification and regression benchmarks."
    )
    codes = detect_readme_language_codes(text)
    assert "en" in codes
    assert len(codes) <= README_LANGUAGE_MAX


def test_detect_readme_language_codes_short_text_still_runs():
    pytest.importorskip("lingua")
    codes = detect_readme_language_codes("Hello world.")
    assert isinstance(codes, list)
    assert len(codes) <= README_LANGUAGE_MAX


def test_constants_document_thresholds():
    assert README_LANGUAGE_MIN_CONFIDENCE == 0.75
    assert README_LANGUAGE_MAX == 5
