"""
Shared LLM schema:inLanguage detection (ISO codes + Language-entity predictions).

Used by Hugging Face overlay mapping and by AI4Life/Kaggle extract assets so all
three platforms share the same question, parser, and extraction_method.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

import pycountry

from etl_extractors.hf.clients.language_client import HFLanguagesClient

INLANGUAGE_PROPERTY = "schema:inLanguage"
LLM_INLANGUAGE_METHOD = "LLM_schema_extraction"
LLM_INLANGUAGE_CONFIDENCE = 0.85

_INLANGUAGE_SPLIT = re.compile(r"[,;/]|\band\b", re.IGNORECASE)
_language_client: Optional[HFLanguagesClient] = None

logger = logging.getLogger(__name__)


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


def detect_inlanguage_with_llm(
    texts_by_model_id: Dict[str, str],
    *,
    log: Optional[logging.Logger] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Run the shared LLM schema extractor for ``schema:inLanguage`` only.

    Empty texts skip the model (no vLLM call). Return shape matches the former
    Lingua assets: ``{model_id: [{code, confidence}, ...]}``.
    """
    from etl import LLMConfig
    from etl_extractors.hf.hf_llm_extraction import HFLLMSchemaPropertyExtractor

    log = log or logger
    detected: Dict[str, List[Dict[str, Any]]] = {
        model_id: [] for model_id in texts_by_model_id
    }
    nonempty = {
        model_id: text.strip()
        for model_id, text in texts_by_model_id.items()
        if str(text or "").strip()
    }
    if not nonempty:
        log.info("No documentation text for LLM inLanguage detection")
        return detected

    config = LLMConfig()
    extractor = HFLLMSchemaPropertyExtractor(logger=log, config=config)
    extractor.load_metadata()
    if not extractor.questions or INLANGUAGE_PROPERTY not in extractor.questions:
        raise KeyError(
            f"{INLANGUAGE_PROPERTY} is not defined in llm_questions.csv"
        )
    extractor.questions = {
        INLANGUAGE_PROPERTY: extractor.questions[INLANGUAGE_PROPERTY]
    }
    extractor.prop_template_type_map = {
        INLANGUAGE_PROPERTY: extractor.prop_template_type_map[INLANGUAGE_PROPERTY]
    }
    extractor.load_llm()
    batch_size = extractor.estimate_max_concurrent_cards(
        nonempty, typical_visible_output_tokens=150
    )
    extractor.extract_properties(
        nonempty, return_result=False, batch_size=batch_size
    )
    parsed = extractor.parse_llm_output()
    for model_id, predictions in predictions_from_llm_output(parsed).items():
        detected[model_id] = predictions

    log.info(
        "LLM inLanguage detection finished for %d/%d texts",
        len(nonempty),
        len(texts_by_model_id),
    )
    return detected
