"""
Shared LLM keyword extraction from model-card / documentation text.

Used to fill schema:keywords when a Kaggle parent has no curated tags.
Returns short keyword refs suitable for DefinedTerm nodes (same shape as
Kaggle tag ``ref`` / ``name`` strings).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

KEYWORDS_PROPERTY = "schema:keywords"
LLM_KEYWORDS_METHOD = "LLM_keyword_extraction"
LLM_KEYWORDS_CONFIDENCE = 0.8
MAX_KEYWORDS_PER_MODEL = 8

_KEYWORD_QUESTION = (
    "Extract up to 8 short topical keywords or tags that describe the model "
    "(tasks, domains, techniques, or modalities). Prefer common ML catalog "
    "terms (e.g. text classification, nlp, image generation, transformers). "
    "Return a comma-separated list of short phrases only. Do not invent "
    "organization names or version numbers. If the context has no usable "
    "signal, return NA."
)

_SPLIT = re.compile(r"[,;|/]|\band\b", re.IGNORECASE)

logger = logging.getLogger(__name__)


def _is_meaningful_llm_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.upper() != "NA"


def normalize_keyword_ref(raw: str) -> str:
    """Normalize a keyword phrase to a stable catalog ref."""
    text = str(raw or "").strip().strip("[]'\"")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_llm_keywords(
    value: Any,
    *,
    max_keywords: int = MAX_KEYWORDS_PER_MODEL,
    existing_refs: Optional[Set[str]] = None,
) -> List[str]:
    """
    Parse LLM keyword output into ordered, de-duplicated refs.

    When ``existing_refs`` is provided, case-insensitive matches reuse the
    catalog spelling so LLM tags link to existing Keyword nodes.
    """
    if isinstance(value, list):
        tokens = [str(item).strip() for item in value]
    elif _is_meaningful_llm_value(value):
        tokens = [part.strip() for part in _SPLIT.split(str(value))]
    else:
        return []

    existing_by_lower: Dict[str, str] = {}
    if existing_refs:
        for ref in existing_refs:
            key = str(ref).strip()
            if key:
                existing_by_lower[key.lower()] = key

    seen: List[str] = []
    seen_lower: Set[str] = set()
    for raw in tokens:
        ref = normalize_keyword_ref(raw)
        if not ref or ref.upper() == "NA":
            continue
        # Drop long sentences; keywords should stay facet-sized.
        if len(ref) > 64 or " " in ref and len(ref.split()) > 6:
            continue
        matched = existing_by_lower.get(ref.lower(), ref)
        lower = matched.lower()
        if lower in seen_lower:
            continue
        seen_lower.add(lower)
        seen.append(matched)
        if len(seen) >= max_keywords:
            break
    return seen


def predictions_from_llm_output(
    parsed: Dict[str, Dict[str, Any]],
    *,
    existing_refs: Optional[Set[str]] = None,
) -> Dict[str, List[str]]:
    """Convert per-model LLM parse dicts into ``{model_id: [keyword_refs]}``."""
    out: Dict[str, List[str]] = {}
    for model_id, record in (parsed or {}).items():
        if not isinstance(record, dict):
            out[model_id] = []
            continue
        out[model_id] = parse_llm_keywords(
            record.get(KEYWORDS_PROPERTY),
            existing_refs=existing_refs,
        )
    return out


def extract_keywords_with_llm(
    texts_by_model_id: Dict[str, str],
    *,
    existing_refs: Optional[Set[str]] = None,
    log: Optional[logging.Logger] = None,
) -> Dict[str, List[str]]:
    """
    Run a single-property LLM extract for ``schema:keywords``.

    Empty texts skip the model. Returns ``{model_id: [keyword_refs]}`` for
    every input id (empty list when skipped or NA).
    """
    from etl import LLMConfig
    from etl_extractors.hf.hf_llm_extraction import HFLLMSchemaPropertyExtractor

    log = log or logger
    detected: Dict[str, List[str]] = {
        model_id: [] for model_id in texts_by_model_id
    }
    nonempty = {
        model_id: text.strip()
        for model_id, text in texts_by_model_id.items()
        if str(text or "").strip()
    }
    if not nonempty:
        log.info("No documentation text for LLM keyword extraction")
        return detected

    config = LLMConfig()
    extractor = HFLLMSchemaPropertyExtractor(logger=log, config=config)
    extractor.load_metadata()
    # Override to a single keyword question (do not require CSV changes for HF).
    extractor.questions = {KEYWORDS_PROPERTY: _KEYWORD_QUESTION}
    extractor.prop_template_type_map = {KEYWORDS_PROPERTY: "free_summarize"}
    extractor.load_llm()
    batch_size = extractor.estimate_max_concurrent_cards(
        nonempty, typical_visible_output_tokens=120
    )
    extractor.extract_properties(
        nonempty, return_result=False, batch_size=batch_size
    )
    parsed = extractor.parse_llm_output()
    for model_id, refs in predictions_from_llm_output(
        parsed, existing_refs=existing_refs
    ).items():
        detected[model_id] = refs

    filled = sum(1 for refs in detected.values() if refs)
    log.info(
        "LLM keyword extraction finished for %d/%d texts (%d with keywords)",
        len(nonempty),
        len(texts_by_model_id),
        filled,
    )
    return detected
