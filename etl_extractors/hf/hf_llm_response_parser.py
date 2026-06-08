"""
Parse LLM responses for HF schema property extraction.

Expected model output is a JSON object: ``{"result": "<value>"}``.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
_RESULT_JSON_RE = re.compile(r'\{[^{}]*"result"\s*:\s*".*?"[^{}]*\}', re.DOTALL)
_NA_VALUES = frozenset({"na", "n/a", "none", "null", ""})


def _normalize_extracted_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        value = value[0]
    text = str(value).strip()
    if text.lower() in _NA_VALUES:
        return None
    return text or None


def _parse_json_payload(raw: str) -> Optional[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _extract_result_from_dict(payload: dict) -> Optional[str]:
    if "result" not in payload:
        return None
    return _normalize_extracted_value(payload.get("result"))


def parse_llm_property_response(raw_text: str) -> Optional[str]:
    """
    Parse a single LLM property extraction response.

    Args:
        raw_text: Raw model output text.

    Returns:
        Extracted property value, or ``None`` if missing/NA/unparseable.
    """
    if not raw_text or not str(raw_text).strip():
        return None

    text = str(raw_text).strip()

    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        payload = _parse_json_payload(fenced.group(1))
        if payload is not None:
            result = _extract_result_from_dict(payload)
            if result is not None:
                return result

    payload = _parse_json_payload(text)
    if payload is not None:
        result = _extract_result_from_dict(payload)
        if result is not None:
            return result

    loose = _RESULT_JSON_RE.search(text)
    if loose:
        payload = _parse_json_payload(loose.group(0))
        if payload is not None:
            return _extract_result_from_dict(payload)

    return None
