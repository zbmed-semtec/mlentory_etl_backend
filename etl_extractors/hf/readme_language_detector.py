"""
Detect natural languages in Hugging Face model cards for schema:inLanguage.

Uses Lingua for probabilistic detection and pycountry for normalization, matching
``HFLanguagesClient`` / ``supportedLanguages`` hashing semantics.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Set

from etl_extractors.hf.clients.language_client import HFLanguagesClient

logger = logging.getLogger(__name__)

# Confidence threshold on Lingua scores (0.0–1.0); readme languages sorted by score descending.
README_LANGUAGE_MIN_CONFIDENCE = 0.75
README_LANGUAGE_MAX = 5

_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\r?\n.*?\r?\n---\s*\r?\n", re.DOTALL)

_language_client = HFLanguagesClient()
_detector = None


def strip_model_card_frontmatter(text: str) -> str:
    """
    Remove a YAML ``---`` frontmatter block from markdown model card content.

    Matches the convention used for ``schema:description`` extraction.
    """
    if not text:
        return ""
    stripped = _FRONTMATTER_PATTERN.sub("", text, count=1)
    return stripped.strip()


def _get_detector():
    """Lazy-init Lingua detector (expensive to construct)."""
    global _detector
    if _detector is None:
        try:
            from lingua import LanguageDetectorBuilder  # type: ignore[import-untyped]
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Missing dependency 'lingua-language-detector'. "
                "Install project dependencies in the Dagster runtime image "
                "before running hf_detected_readme_languages."
            )
        _detector = LanguageDetectorBuilder.from_all_languages().build()
    return _detector


def _confidence_score(cv: object) -> float:
    """Read Lingua confidence value across minor API variants."""
    for attr in ("value", "confidence"):
        if hasattr(cv, attr):
            raw = getattr(cv, attr)
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    return 0.0


def _iso_hints_from_lingua_language(language: object) -> List[str]:
    """Produce candidate tags for pycountry from a Lingua ``Language`` enum."""
    hints: List[str] = []

    iso1 = getattr(language, "iso_code_639_1", None)
    if iso1 is not None:
        code = getattr(iso1, "name", None)
        if isinstance(code, str) and len(code) == 2:
            hints.append(code.lower())
        else:
            raw = str(iso1).strip().lower()
            if len(raw) == 2 and raw.isalpha():
                hints.append(raw)

    iso3 = getattr(language, "iso_code_639_3", None)
    if iso3 is not None:
        code = getattr(iso3, "name", None)
        if isinstance(code, str) and len(code) == 3:
            hints.append(code.lower())
        else:
            raw = str(iso3).strip().lower()
            if len(raw) == 3 and raw.isalpha():
                hints.append(raw)

    return hints


def detect_readme_language_codes(card: str) -> List[str]:
    """
    Detect documentation languages for model card markdown.

    Strips frontmatter, runs Lingua, filters by confidence, normalizes with pycountry,
    deduplicates (order preserved by descending confidence), caps at ``README_LANGUAGE_MAX``.

    Args:
        card: Raw model card markdown.

    Returns:
        Up to ``README_LANGUAGE_MAX`` canonical ISO codes (alpha-2 preferred).
    """
    body = strip_model_card_frontmatter(card or "")
    if not body.strip():
        return []

    detector = _get_detector()

    try:
        if hasattr(detector, "compute_language_confidence_values"):
            confidence_values = detector.compute_language_confidence_values(body)
        else:
            confidence_values = detector.compute_language_confidences(body)
    except Exception as exc:
        logger.warning("Lingua failed on model card snippet: %s", exc)
        return []

    # Already descending per Lingua; sort defensively by score.
    scored = [(cv, _confidence_score(cv)) for cv in confidence_values]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    seen: Set[str] = set()
    results: List[str] = []

    for cv, score in scored:
        if score < README_LANGUAGE_MIN_CONFIDENCE:
            continue

        lingua_lang = getattr(cv, "language", None)
        if lingua_lang is None:
            continue

        canonical: Optional[str] = None
        for hint in _iso_hints_from_lingua_language(lingua_lang):
            canonical = _language_client.normalize_language_code(hint)
            if canonical:
                break

        if not canonical:
            logger.debug(
                "Skipping Lingua language without pycountry mapping: %s",
                lingua_lang,
            )
            continue

        key = canonical.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(key)

        if len(results) >= README_LANGUAGE_MAX:
            break

    return results
