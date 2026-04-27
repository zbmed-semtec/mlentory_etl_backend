from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Any, Dict, Iterable, List, Optional


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


def extract_normalized_doi(
    raw_record: Dict[str, Any],
    candidate_fields: Iterable[str],
) -> Optional[str]:
    """
    Extract a DOI from candidate fields and normalize it to doi.org URL.
    """
    for field in candidate_fields:
        value = raw_record.get(field)
        if not value or not isinstance(value, str):
            continue

        text = value.strip()
        if not text:
            continue

        lower_text = text.lower()
        if "doi.org/" in lower_text:
            doi_part = lower_text.split("doi.org/", 1)[1].strip()
            if doi_part:
                return f"https://doi.org/{doi_part}"

        match = DOI_PATTERN.search(text)
        if match:
            return f"https://doi.org/{match.group(0)}"

    return None


def build_identifier(doi: Optional[str], mlentory_id: str) -> List[str]:
    """
    Build identifier list containing only DOI and/or MLentory w3id.
    """
    identifiers: List[str] = []

    if doi:
        identifiers.append(doi)
    if mlentory_id:
        identifiers.append(mlentory_id)

    # Deduplicate while preserving order.
    return list(dict.fromkeys(identifiers))


def build_model_urls(platform_url: Optional[str], mlentory_id: Optional[str]) -> List[str]:
    """
    Build URL list with platform URL and MLentory UI URL.
    """
    urls: List[str] = []

    if platform_url:
        cleaned_platform_url = platform_url.strip()
        if cleaned_platform_url:
            urls.append(cleaned_platform_url)

    if mlentory_id:
        cleaned_mlentory_id = mlentory_id.strip()
        prefix = "https://w3id.org/mlentory/"
        if cleaned_mlentory_id.startswith(prefix):
            mlentory_ui_url = cleaned_mlentory_id.replace(
                prefix, "https://mlentory.zbmed.de/", 1
            )
            urls.append(mlentory_ui_url)

    return list(dict.fromkeys(urls))


def validate_optional_url(value: Any) -> Optional[str]:
    """
    Return a normalized URL string when valid, else None.

    A URL is considered valid when it is a non-empty string with
    an explicit http/https scheme and network location.
    """
    if not isinstance(value, str):
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None

    return cleaned
