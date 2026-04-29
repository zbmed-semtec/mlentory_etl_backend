"""
Shared text language detection helpers (Lingua + pycountry).
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Set

import pycountry

logger = logging.getLogger(__name__)

_FRONTMATTER_PATTERN = re.compile(r"\A---\s*\r?\n.*?\r?\n---\s*\r?\n", re.DOTALL)
_detector = None


def strip_markdown_frontmatter(text: str) -> str:
    """Remove a YAML frontmatter block from markdown text."""
    if not text:
        return ""
    stripped = _FRONTMATTER_PATTERN.sub("", text, count=1)
    return stripped.strip()


def _get_detector():
    """Lazy-init Lingua detector."""
    global _detector
    if _detector is None:
        try:
            from lingua import LanguageDetectorBuilder  # type: ignore[import-untyped]
        except ModuleNotFoundError:
            raise ModuleNotFoundError(
                "Missing dependency 'lingua-language-detector'. "
                "Install project dependencies in the Dagster runtime image "
                "before running language detection assets."
            )
        _detector = LanguageDetectorBuilder.from_all_languages().build()
    return _detector


def _normalize_language_code(code: str) -> Optional[str]:
    """Normalize tag/code to canonical alpha-2 (preferred) or alpha-3."""
    code = (code or "").strip().lower()
    if not code:
        return None

    language = pycountry.languages.get(alpha_2=code)
    if language is None:
        language = pycountry.languages.get(alpha_3=code)
    if language is None and "-" in code:
        language = pycountry.languages.get(alpha_2=code.split("-")[0])
    if language is None:
        return None

    if getattr(language, "alpha_2", None):
        return language.alpha_2.lower()
    if getattr(language, "alpha_3", None):
        return language.alpha_3.lower()
    return None


def _confidence_score(confidence_value: object) -> float:
    for attr in ("value", "confidence"):
        if hasattr(confidence_value, attr):
            try:
                return float(getattr(confidence_value, attr))
            except (TypeError, ValueError):
                continue
    return 0.0


def _iso_hints_from_lingua_language(language: object) -> List[str]:
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


def detect_language_codes(
    text: str,
    min_confidence: float = 0.75,
    max_languages: int = 5,
) -> List[str]:
    """
    Detect language codes from text with Lingua and normalize via pycountry.

    Returns canonical ISO codes ordered by descending confidence.
    """
    body = (text or "").strip()
    if not body:
        return []

    detector = _get_detector()

    try:
        if hasattr(detector, "compute_language_confidence_values"):
            confidence_values = detector.compute_language_confidence_values(body)
        else:
            confidence_values = detector.compute_language_confidences(body)
    except Exception as exc:
        logger.warning("Lingua failed on text snippet: %s", exc)
        return []

    scored = [(cv, _confidence_score(cv)) for cv in confidence_values]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    seen: Set[str] = set()
    results: List[str] = []
    for confidence_value, score in scored:
        if score < min_confidence:
            continue

        language = getattr(confidence_value, "language", None)
        if language is None:
            continue

        canonical: Optional[str] = None
        for hint in _iso_hints_from_lingua_language(language):
            canonical = _normalize_language_code(hint)
            if canonical:
                break

        if not canonical:
            continue

        if canonical in seen:
            continue
        seen.add(canonical)
        results.append(canonical)

        if len(results) >= max_languages:
            break

    return results

