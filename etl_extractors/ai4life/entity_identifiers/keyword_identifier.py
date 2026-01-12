from __future__ import annotations

from typing import Set, Dict, List, Optional, Any
import pandas as pd
import logging
import json
import re

from .base import EntityIdentifier

logger = logging.getLogger(__name__)


class KeywordIdentifier(EntityIdentifier):
    @property
    def entity_type(self) -> str:
        return "keywords"

    def _get_keyword_value(self, row) -> Optional[Any]:
        # Include the columns you actually have
        for col in ("keywords", "schema.org:keywords", "tags"):
            if col in row and row.get(col) not in (None, "", []):
                return row.get(col)
        return None

    def _parse_string(self, s: str) -> List[str]:
        s = s.strip()
        if not s:
            return []

        # JSON list string: ["a","b"]
        if s.startswith("[") and s.endswith("]"):
            try:
                val = json.loads(s)
                if isinstance(val, list):
                    return [str(x).strip() for x in val if x and str(x).strip()]
            except Exception:
                pass

        # comma-separated: "a, b, c"
        return [p.strip() for p in re.split(r"\s*,\s*", s) if p.strip()]

    def _normalize_keywords(self, kw: Any) -> List[str]:
        if kw is None or kw == "" or kw == []:
            return []

        out: List[str] = []

        # list-like: also handle nested JSON-list strings inside a list
        if isinstance(kw, (list, tuple, set)):
            for item in kw:
                if item is None or item == "":
                    continue
                if isinstance(item, str):
                    out.extend(self._parse_string(item))
                else:
                    s = str(item).strip()
                    if s:
                        out.append(s)
            return [x for x in out if x]

        # string
        if isinstance(kw, str):
            return self._parse_string(kw)

        s = str(kw).strip()
        return [s] if s else []

    # ✅ REQUIRED by your abstract base class
    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        """
        Unique keywords across all models.
        """
        keywords: Set[str] = set()
        if models_df is None or models_df.empty:
            return keywords

        for _, row in models_df.iterrows():
            kw = self._get_keyword_value(row)
            for x in self._normalize_keywords(kw):
                keywords.add(x)

        logger.info("Identified %d unique keywords", len(keywords))
        return keywords

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        model_id -> [keyword(s)]
        """
        model_keywords: Dict[str, List[str]] = {}
        if models_df is None or models_df.empty:
            return model_keywords

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id") or row.get("model_id") or row.get("name")
            if not model_id:
                continue

            kw = self._get_keyword_value(row)
            model_keywords[str(model_id)] = self._normalize_keywords(kw)

        logger.info("Identified keywords for %d models", len(model_keywords))
        return model_keywords

    # Backwards-compat (optional)
    def identify_per_keyword(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        return self.identify_per_model(models_df)
