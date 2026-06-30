"""
Hugging Face model-card citation helpers.

- Pick which chunk per model is most likely to contain a bibliography (HF chunk AST).
- Map that chunk's ``phtext`` to normalized ``citation`` JSON (CreativeWork list).

BibTeX / DOI parsing lives in :mod:`etl_transformers.common.citation_text`.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from etl_transformers.common.citation_text import parse_creative_work_citations_from_text

_CHUNK_HAS_CITATION = re.compile(r"\bcitation\b", re.IGNORECASE)


def select_citation_chunk_per_model(
    chunks_dict: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    For each ``model_id``, return the best chunk dict to scan for citations, or ``None``.

    Prefers a ``code``-typed chunk that mentions "citation"; otherwise the first
    chunk that mentions "citation".
    """
    result: Dict[str, Optional[Dict[str, Any]]] = {}

    for model_id, chunks_list in chunks_dict.items():
        chosen: Optional[Dict[str, Any]] = None
        for chunk in chunks_list or []:
            phtext = chunk.get("phtext")
            if not phtext or not isinstance(phtext, str):
                continue
            if not _CHUNK_HAS_CITATION.search(phtext):
                continue
            if chunk.get("type") == "code":
                chosen = chunk
                break
            if chosen is None:
                chosen = chunk
        result[model_id] = chosen

    return result


def normalize_citations_from_chunk(
    model_id: str,
    chunk: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build normalized ``citation`` entries for one HF model from its selected chunk.

    Returns ``[]`` when there is no chunk or no usable ``phtext``.
    """
    if not chunk:
        return []

    text = chunk.get("phtext")
    if not isinstance(text, str) or not text.strip():
        return []

    return parse_creative_work_citations_from_text(text, log_context=model_id)
