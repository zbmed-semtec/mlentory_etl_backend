"""Language metadata client backed by pycountry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging

import pandas as pd
import pycountry

from etl.utils import generate_mlentory_entity_hash_id


logger = logging.getLogger(__name__)


class HFLanguagesClient:
    """Generate language metadata records using the pycountry dataset."""

    def get_languages_metadata(self, language_codes: List[str]) -> pd.DataFrame:
        """
        Build metadata entries for the provided ISO 639 language codes.

        Args:
            language_codes: List of ISO 639-1/639-2 language codes.

        Returns:
            DataFrame with metadata for each requested language code.
        """

        records: List[Dict[str, Any]] = []

        for code in language_codes:
            normalized_code = (code or "").strip()
            if not normalized_code:
                continue

            metadata = self._build_language_record(normalized_code)
            records.append(metadata)

        if not records:
            return pd.DataFrame(columns=[
                "code",
                "alpha_2",
                "alpha_3",
                "name",
                "scope",
                "type",
                "mlentory_id",
                "enriched",
                "entity_type",
                "platform",
                "extraction_metadata",
            ])

        return pd.DataFrame(records)

    def _build_language_record(self, code: str) -> Dict[str, Any]:
        """Construct a metadata record for a given language code."""

        language = self._lookup_language(code)

        record: Dict[str, Any] = {
            "code": code,
            "alpha_2": getattr(language, "alpha_2", None) if language else None,
            "alpha_3": getattr(language, "alpha_3", None) if language else None,
            "name": getattr(language, "name", None) if language else None,
            "scope": getattr(language, "scope", None) if language else None,
            "type": getattr(language, "type", None) if language else None,
            "mlentory_id": generate_mlentory_entity_hash_id("Language", code, platform="HF"),
            "enriched": language is not None,
            "entity_type": "Language",
            "platform": "HF",
            "extraction_metadata": {
                "extraction_method": "pycountry",
                "confidence": 1.0,
            },
        }

        if language is None:
            logger.debug("Language code '%s' not found in pycountry", code)

        return record

    def _lookup_language(self, code: str) -> Optional[Any]:
        """Attempt to resolve the provided language code using pycountry."""

        code_lower = code.lower()

        # Try ISO 639-1 (alpha_2) codes first
        language = pycountry.languages.get(alpha_2=code_lower)
        if language:
            return language

        # Fall back to ISO 639-2/3 (alpha_3) codes
        language = pycountry.languages.get(alpha_3=code_lower)
        if language:
            return language

        # Some tags might include region variants like "en-US"; try the prefix
        if "-" in code_lower:
            language = pycountry.languages.get(alpha_2=code_lower.split("-")[0])
            if language:
                return language

        return None


