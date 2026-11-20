"""Query shape for the improved keyword endpoint."""

import json

from api.services.improved_keyword_query import build_improved_keyword_query


def _dump(query: str) -> str:
    return json.dumps(build_improved_keyword_query(query))


def test_exact_name_is_a_strong_term_on_the_raw_field():
    body = _dump("bert-base-uncased")
    assert '"value": "bert-base-uncased"' in body
    assert '"case_insensitive": true' in body
    assert '"boost": 200' in body
    assert "wildcard" not in body


def test_spaced_name_matches_the_hyphenated_slug():
    body = _dump("Mistral 7B")
    assert '"value": "mistral-7b"' in body
    assert '"case_insensitive": true' in body
    assert '"boost": 200' in body


def test_direction_follows_source_then_target():
    labels = (
        "automatic-speech-recognition",
        "speech recognition",
        "text-to-speech",
        "text-to-image",
        "text-to-image generation",
        "image-to-text",
        "image-text-to-text",
        "text-classification",
    )
    speech = json.dumps(build_improved_keyword_query("speech to text", task_labels=labels))
    assert '"ml_tasks": "speech-to-text"' in speech
    assert "automatic-speech-recognition" not in speech
    assert "text-to-speech" not in speech
    assert "wildcard" not in speech

    image = json.dumps(build_improved_keyword_query("text to image", task_labels=labels))
    assert '"ml_tasks": "text-to-image"' in image
    assert "text-to-image generation" in image
    assert "image-to-text" not in image
    assert "image-text-to-text" not in image

    spoken = json.dumps(build_improved_keyword_query("text to speech", task_labels=labels))
    assert '"ml_tasks": "text-to-speech"' in spoken
    assert "automatic-speech-recognition" not in spoken

    recognition = json.dumps(
        build_improved_keyword_query("speech recognition", task_labels=labels)
    )
    assert '"ml_tasks": "automatic-speech-recognition"' in recognition
    assert '"boost": 40.0' in recognition


def test_task_slug_and_author_are_exact_terms():
    encoded = _dump("text classification")
    assert '"ml_tasks": "text-classification"' in encoded
    author = _dump("google-bert")
    assert '"shared_by": "google-bert"' in author
    assert '"datasets": "google-bert"' in author
    assert "license" not in author
    assert "readme" not in author
    assert "parameter_count" not in author


def test_empty_query_is_not_a_match_all():
    assert build_improved_keyword_query("  ") is None
