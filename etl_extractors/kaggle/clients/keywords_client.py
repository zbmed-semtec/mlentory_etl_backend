from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from etl_extractors.kaggle.kaggle_helper import KaggleHelper

logger = logging.getLogger(__name__)


class KaggleKeywordsClient:
    """Extractor for keyword (tag) metadata from the Kaggle platform.

    Kaggle curates its tags, so each carries a stable ``ref``, a human
    description and a ``fullPath`` placing it in a taxonomy
    ("analysis > nlp", "task > classification", "technique > random forest",
    "packages > sklearn"). The same tag object repeats identically on every
    model that uses it, so keywords are de-duplicated by ``ref``: one node,
    many edges.
    """

    def __init__(self, records_data: Dict[str, Any]):
        # expected: {"data": [...], "timestamp": "..."}
        self.records_data = records_data or {}

    def get_keywords_metadata(
        self, keyword_names: Optional[Iterable[str]] = None
    ) -> pd.DataFrame:
        """
        Build one row per distinct keyword found across all models.

        Args:
            keyword_names: Optional refs to keep. When omitted, every keyword
                found is returned.
        """
        records = self.records_data.get("data", []) or []
        wanted = {str(k) for k in keyword_names} if keyword_names is not None else None

        by_ref: Dict[str, Dict[str, Any]] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            for tag in self._tags_of(record):
                ref = str(tag.get("ref") or tag.get("name") or "").strip()
                if not ref or (wanted is not None and ref not in wanted):
                    continue
                # Later copies carry the same content; keep the first but let
                # a richer one (with a description) win.
                existing = by_ref.get(ref)
                if existing is None or (
                    not existing.get("description") and tag.get("description")
                ):
                    by_ref[ref] = tag

        keywords_metadata = [
            self.fetch_keyword_metadata(ref, tag) for ref, tag in sorted(by_ref.items())
        ]
        logger.info(
            "Extracted %d distinct keywords from %d models",
            len(keywords_metadata), len(records),
        )
        return pd.DataFrame(keywords_metadata)

    # ---------- helpers for normalization ----------

    def _extraction_time(self) -> str:
        """
        Extraction time in the run-folder format (``2026-01-30_05-03-47``).

        ``records_data["timestamp"]`` is an ISO string set at fetch, so it is
        reformatted here to match the convention used by the other platforms.
        """
        raw = str(self.records_data.get("timestamp", "") or "").strip()
        if not raw:
            return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        try:
            return datetime.fromisoformat(
                raw.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d_%H-%M-%S")
        except ValueError:
            return raw

    @staticmethod
    def _to_str(value: Any) -> str:
        """Convert any value to string; missing/None becomes empty string."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _tags_of(record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Read the tag list off a raw record, tolerating a JSON-string form."""
        tags = record.get("tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (ValueError, TypeError):
                return []
        if not isinstance(tags, list):
            return []
        return [t for t in tags if isinstance(t, dict)]

    @staticmethod
    def _split_full_path(full_path: str) -> tuple[str, str]:
        """
        Split "analysis > nlp" into ("analysis", "nlp").

        The prefix is Kaggle's own grouping - task, analysis, technique,
        packages - and makes a useful facet above the keyword itself.
        """
        if not full_path or ">" not in full_path:
            return "", full_path.strip()
        head, _, tail = full_path.rpartition(">")
        return head.strip(), tail.strip()

    def fetch_keyword_metadata(self, ref: str, tag: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a single keyword, missing values as ''."""
        out: Dict[str, Any] = {}

        # fullPath places the tag in Kaggle's taxonomy ("analysis > nlp",
        # "task > classification"). Only the category prefix is kept: it is
        # what distinguishes kinds of tag - a task from a technique from a
        # package - and the leaf is the tag name we already have.
        category, _ = self._split_full_path(self._to_str(tag.get("fullPath", "")))

        out["keywordId"] = ref
        out["mlentory_id"] = KaggleHelper.generate_mlentory_entity_hash_id(
            "Keyword", ref, platform="Kaggle"
        )
        out["name"] = self._to_str(tag.get("name") or ref)
        out["category"] = category
        out["description"] = self._to_str(tag.get("description", ""))
        out["enriched"] = True
        out["entity_type"] = "Keyword"
        out["platform"] = "Kaggle"
        out["extraction_metadata"] = {
            "extraction_method": "Kaggle_models_endpoint",
            "confidence": 1.0,
            "extraction_time": self._extraction_time(),
        }

        for key, value in list(out.items()):
            if key == "extraction_metadata":
                continue  # stays a nested object, as in the other platforms
            if value is None:
                out[key] = ""
            elif isinstance(value, (list, dict)):
                out[key] = json.dumps(value, ensure_ascii=False)

        return out