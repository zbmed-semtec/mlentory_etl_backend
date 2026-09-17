"""
AI4Life-specific normalization of raw bibliographic fields into ``MLModel.citation``.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from etl_transformers.common.citation_text import (
    canonical_doi_uri,
    parse_creative_work_citations_from_text,
)
from etl_transformers.common.utils import extract_normalized_doi

from schemas.fair4ml.citation import ModelCitationWork


def normalize_citations_from_ai4life_raw(raw_record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build ``MLModel.citation`` from AI4Life raw ``citation`` (``manifest.cite``) and
    ``referencePublication`` (Zenodo DOI URL).

    Dedupes CreativeWorks by ``@id``. Entries without a DOI are omitted (same profile as HF).
    """
    seen_ids: set[str] = set()
    out: List[Dict[str, Any]] = []

    def append_unique(works: List[Dict[str, Any]]) -> None:
        for w in works:
            rid = w.get("@id")
            if rid:
                if rid in seen_ids:
                    continue
                seen_ids.add(str(rid))
            out.append(w)

    rp = raw_record.get("referencePublication")
    if isinstance(rp, str) and rp.strip():
        doi_url = extract_normalized_doi(
            {"referencePublication": rp.strip()},
            ("referencePublication",),
        )
        if doi_url:
            w = ModelCitationWork(
                resource_id=doi_url,
                name=None,
                author=[],
                publicationDate=None,
            )
            append_unique([w.model_dump(mode="json", by_alias=True)])

    cite_val = raw_record.get("citation")
    parsed_json: Any = None

    if isinstance(cite_val, str):
        s = cite_val.strip()
        if s:
            if s.startswith(("[", "{")):
                try:
                    parsed_json = json.loads(s)
                except json.JSONDecodeError:
                    parsed_json = None
            if parsed_json is None:
                append_unique(
                    parse_creative_work_citations_from_text(
                        s, log_context="ai4life manifest.cite"
                    )
                )
    elif isinstance(cite_val, list):
        parsed_json = cite_val
    elif isinstance(cite_val, dict):
        parsed_json = cite_val

    if isinstance(parsed_json, list):
        for item in parsed_json:
            if isinstance(item, dict):
                doi = str(item.get("doi", "")).strip()
                text = str(item.get("text", "")).strip()
                if doi:
                    w = ModelCitationWork(
                        resource_id=canonical_doi_uri(doi),
                        name=text or None,
                        author=[],
                        publicationDate=None,
                    )
                    append_unique([w.model_dump(mode="json", by_alias=True)])
                elif text:
                    append_unique(
                        parse_creative_work_citations_from_text(
                            text, log_context="ai4life citation item"
                        )
                    )
            elif isinstance(item, str) and item.strip():
                append_unique(
                    parse_creative_work_citations_from_text(
                        item.strip(), log_context="ai4life citation list item"
                    )
                )
    elif isinstance(parsed_json, dict):
        doi = str(parsed_json.get("doi", "")).strip()
        text = str(parsed_json.get("text", "")).strip()
        if doi:
            w = ModelCitationWork(
                resource_id=canonical_doi_uri(doi),
                name=text or None,
                author=[],
                publicationDate=None,
            )
            append_unique([w.model_dump(mode="json", by_alias=True)])
        elif text:
            append_unique(
                parse_creative_work_citations_from_text(
                    text, log_context="ai4life citation object"
                )
            )

    return out
