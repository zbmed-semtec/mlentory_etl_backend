"""
Shared parsing of LLM schema:inLanguage answers (ISO codes + Language-entity predictions).

Used by the Hugging Face overlay mapping and by the AI4Life/Kaggle extract assets so all
three platforms share the same question, parser, and extraction_method.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pycountry

from etl_extractors.hf.clients.language_client import HFLanguagesClient

INLANGUAGE_PROPERTY = "schema:inLanguage"
LLM_INLANGUAGE_METHOD = "LLM_schema_extraction"
LLM_INLANGUAGE_CONFIDENCE = 0.85

_INLANGUAGE_SPLIT = re.compile(r"[,;/]|\band\b", re.IGNORECASE)
_language_client: Optional[HFLanguagesClient] = None


def _get_language_client() -> HFLanguagesClient:
    global _language_client
    if _language_client is None:
        _language_client = HFLanguagesClient()
    return _language_client


def _is_meaningful_llm_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.upper() != "NA"


def parse_llm_inlanguage_codes(value: Any, max_languages: int = 5) -> List[str]:
    """
    Parse schema:inLanguage LLM output into canonical ISO language codes.

    Accepts a comma-separated string (``en, zh``), language names (``English``),
    or a list. Unknown tokens are dropped. Codes are de-duplicated in order.
    """
    if isinstance(value, list):
        tokens = [str(item).strip() for item in value]
    elif _is_meaningful_llm_value(value):
        tokens = [part.strip() for part in _INLANGUAGE_SPLIT.split(str(value))]
    else:
        return []

    client = _get_language_client()
    seen: List[str] = []
    for raw in tokens:
        token = raw.strip().strip("[]'\"")
        if not token or token.upper() == "NA":
            continue
        code = client.normalize_language_code(token)
        if code is None:
            try:
                language = pycountry.languages.lookup(token)
            except LookupError:
                language = None
            if language is not None:
                hint = getattr(language, "alpha_2", None) or getattr(language, "alpha_3", None)
                code = client.normalize_language_code(str(hint or ""))
        if not code or code in seen:
            continue
        seen.append(code)
        if len(seen) >= max_languages:
            break
    return seen


def predictions_from_llm_output(
    parsed: Dict[str, Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Convert per-model LLM parse dicts into Lingua-shaped prediction lists."""
    detected: Dict[str, List[Dict[str, Any]]] = {}
    for model_id, record in (parsed or {}).items():
        if not isinstance(record, dict):
            detected[model_id] = []
            continue
        codes = parse_llm_inlanguage_codes(record.get(INLANGUAGE_PROPERTY))
        detected[model_id] = [
            {"code": code, "confidence": LLM_INLANGUAGE_CONFIDENCE} for code in codes
        ]
    return detected
