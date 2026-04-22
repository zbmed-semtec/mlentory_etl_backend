from __future__ import annotations

import re
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
