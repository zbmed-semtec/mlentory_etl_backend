"""
Source-agnostic helpers to parse BibTeX-like / free-text bibliographic strings
into schema.org CreativeWork-shaped citation dicts (for ``MLModel.citation``).

Platform code (e.g. Hugging Face) should only supply the raw string; this module
does not depend on chunk shapes or catalog-specific fields.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Literal, Optional

from etl_transformers.common.utils import DOI_PATTERN

from schemas.fair4ml.citation import CitationAuthor, ModelCitationWork

logger = logging.getLogger(__name__)

_DOI_BRACE = re.compile(r"doi\s*=\s*\{([^}]+)\}", re.IGNORECASE)
_TITLE = re.compile(r"title\s*=\s*\{([^}]*)\}", re.IGNORECASE)
_AUTHOR = re.compile(r"author\s*=\s*\{([^}]*)\}", re.IGNORECASE)
_YEAR = re.compile(r"year\s*=\s*\{?(\d{4})\}?", re.IGNORECASE)

_ORG_HINTS = (
    "university",
    "institute",
    " inc",
    " ltd",
    " lab",
    "google",
    "microsoft",
    "meta ",
    "anthropic",
    "openai",
    "foundation",
    "corporation",
    " gmbh",
)


def canonical_doi_uri(slug: str) -> str:
    """
    Normalize a DOI or DOI-like fragment to ``https://doi.org/...``.

    Accepts bare ``10....``, ``https://doi.org/10....``, or strings containing a DOI.
    """
    s = slug.strip().rstrip(".,);")
    if not s:
        return s
    lower = s.lower()
    if lower.startswith("http"):
        return s
    if "doi.org/" in lower:
        tail = lower.split("doi.org/", 1)[1].strip().split()[0]
        m = DOI_PATTERN.search(tail)
        if m:
            return f"https://doi.org/{m.group(0)}"
        return f"https://doi.org/{tail}"
    m = DOI_PATTERN.search(s)
    if m:
        return f"https://doi.org/{m.group(0)}"
    return f"https://doi.org/{s}"


def collect_doi_slugs_from_text(text: str, max_count: int = 5) -> List[str]:
    """Return unique DOI registry IDs (``10.xxx/...``) found in ``text``, up to ``max_count``."""
    slugs: List[str] = []

    def add(candidate: Optional[str]) -> None:
        if not candidate:
            return
        c = candidate.strip().rstrip(".,);")
        m = DOI_PATTERN.search(c)
        if not m:
            return
        slug = m.group(0)
        if slug not in slugs:
            slugs.append(slug)

    for m in DOI_PATTERN.finditer(text):
        add(m.group(0))
        if len(slugs) >= max_count:
            return slugs

    for m in _DOI_BRACE.finditer(text):
        add(m.group(1))
        if len(slugs) >= max_count:
            break

    return slugs


def _author_kind(name: str) -> Literal["Person", "Organization"]:
    lower = name.lower()
    return "Organization" if any(h in lower for h in _ORG_HINTS) else "Person"


def split_bibtex_author_blob(blob: str) -> List[str]:
    """Split a BibTeX ``author={...}`` body into individual display names."""
    parts = re.split(r"\s+and\s+", blob.strip())
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        for sub in re.split(r"\s*,\s*", p):
            sub = sub.strip()
            if sub:
                out.append(sub)
    return out


def publication_date_from_year(year: Optional[str]) -> Optional[str]:
    """Map a four-digit year string to ``YYYY-01-01`` for ``publicationDate``."""
    if not year or not year.isdigit() or len(year) != 4:
        return None
    return f"{year}-01-01"


def parse_creative_work_citations_from_text(
    text: str,
    *,
    max_works: int = 5,
    log_context: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Parse ``text`` into a list of CreativeWork-shaped dicts (``@type``, ``@id``, …).

    Emits one entry per distinct DOI when any DOI is found; otherwise returns
    ``[]`` (no CreativeWork without a resolvable ``@id`` in this profile).
    """
    if not isinstance(text, str) or not text.strip():
        return []

    dois = collect_doi_slugs_from_text(text, max_count=max_works)

    title_m = _TITLE.search(text)
    title = title_m.group(1).strip() if title_m else None

    author_blob_m = _AUTHOR.search(text)
    authors: List[CitationAuthor] = []
    if author_blob_m:
        for raw_name in split_bibtex_author_blob(author_blob_m.group(1)):
            authors.append(
                CitationAuthor(json_ld_type=_author_kind(raw_name), name=raw_name)
            )

    year_m = _YEAR.search(text)
    pub_date = publication_date_from_year(year_m.group(1) if year_m else None)

    if not dois:
        if title or authors:
            logger.debug(
                "Citation text%s had title/authors but no DOI; skipping",
                f" ({log_context})" if log_context else "",
            )
        return []

    works: List[ModelCitationWork] = []
    for slug in dois:
        works.append(
            ModelCitationWork(
                resource_id=canonical_doi_uri(slug),
                name=title,
                author=authors,
                publicationDate=pub_date,
            )
        )

    if log_context:
        logger.debug("Normalized %d citation(s) for %s", len(works), log_context)

    return [w.model_dump(mode="json", by_alias=True) for w in works]
