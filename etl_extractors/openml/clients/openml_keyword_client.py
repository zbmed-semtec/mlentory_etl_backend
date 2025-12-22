"""
OpenML keyword client: collects keywords/tags from flows and runs and returns a
deduplicated list with minimal metadata. Unlike HF, this client does not call
external enrichment services (e.g., Wikipedia).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import json
import logging

import pandas as pd

from ..openml_helper import OpenMLHelper


logger = logging.getLogger(__name__)


class OpenMLKeywordClient:
    """
    Collects keywords/tags from flows and their runs, returning a unique set with
    minimal metadata (no Wikipedia/Wikidata enrichment).
    """

    def __init__(self, csv_path: Path | str = "/data/refs/keywords.csv") -> None:
        self.csv_path = Path(csv_path)
        self.curated_definitions: Dict[str, Dict[str, Any]] = {}

        # Load curated CSV if it exists (optional enrichment source)
        if self.csv_path.exists():
            self._load_curated_csv()
        else:
            logger.info("Curated keywords CSV not found at %s (optional)", self.csv_path)

    def _load_curated_csv(self) -> None:
        """Load the curated keywords CSV into memory."""
        try:
            df = pd.read_csv(self.csv_path)
            for _, row in df.iterrows():
                keyword = row["keyword"]
                aliases = row.get("aliases", "[]")
                if isinstance(aliases, str):
                    try:
                        aliases = json.loads(aliases)
                    except json.JSONDecodeError:
                        aliases = []

                self.curated_definitions[keyword] = {
                    "keyword": keyword,
                    "mlentory_id": OpenMLHelper.generate_mlentory_entity_hash_id("Keyword", keyword),
                    "definition": row.get("definition"),
                    "aliases": aliases,
                    "source": "curated_csv",
                    "url": None,
                    "wikidata_qid": None,
                    "enriched": True,
                    "entity_type": "Keyword",
                    "platform": "OpenML",
                    "extraction_metadata": {
                        "extraction_method": "Curated CSV",
                        "confidence": 1.0,
                    },
                }
            logger.info("Loaded %d curated keywords from CSV", len(self.curated_definitions))
        except Exception as exc:  # noqa: BLE001
            logger.error("Error loading curated keywords CSV: %s", exc)

    @staticmethod
    def _collect_from_iterable(target: List[str], seen: set[str], values: Optional[Iterable[Any]]) -> None:
        """Collect unique, non-empty string-ish values preserving order."""
        if not values:
            return
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            target.append(text)

    def collect_keywords(
        self,
        keywords: Optional[List[str]] = None,
        flows: Optional[List[Dict[str, Any]]] = None,
        runs: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Combine keywords/tags from flows and runs into a unique list.

        Args:
            keywords: Precomputed keywords to include.
            flows: Flow records (expects optional ``tags`` field).
            runs: Run records (expects ``tags``, ``flow_tags`` or ``keywords`` fields).

        Returns:
            Ordered list of unique keyword strings.
        """
        collected: List[str] = []
        seen: set[str] = set()

        self._collect_from_iterable(collected, seen, keywords)

        if flows:
            for flow in flows:
                self._collect_from_iterable(collected, seen, flow.get("tags"))

        if runs:
            for run in runs:
                self._collect_from_iterable(collected, seen, run.get("tags"))
                self._collect_from_iterable(collected, seen, run.get("flow_tags"))
                self._collect_from_iterable(collected, seen, run.get("keywords"))

        return collected

    def get_keywords_metadata(
        self,
        keywords: Optional[List[str]] = None,
        flows: Optional[List[Dict[str, Any]]] = None,
        runs: Optional[List[Dict[str, Any]]] = None,
    ) -> pd.DataFrame:
        """
        Build keyword metadata without external enrichment, deduping across flows/runs.

        Args:
            keywords: List of keywords to include.
            flows: Flow records contributing tags.
            runs: Run records contributing tags and keywords.

        Returns:
            DataFrame with minimal keyword metadata.
        """
        unique_keywords = self.collect_keywords(keywords=keywords, flows=flows, runs=runs)
        keyword_rows: List[Dict[str, Any]] = []

        for keyword in unique_keywords:
            if keyword in self.curated_definitions:
                keyword_rows.append(self.curated_definitions[keyword])
                continue

            keyword_rows.append(
                {
                    "keyword": keyword,
                    "mlentory_id": OpenMLHelper.generate_mlentory_entity_hash_id("Keyword", keyword),
                    "definition": None,
                    "aliases": [],
                    "source": "openml_tags",
                    "url": None,
                    "wikidata_qid": None,
                    "enriched": False,
                    "entity_type": "Keyword",
                    "platform": "OpenML",
                    "extraction_metadata": {
                        "extraction_method": "OpenML tags",
                        "confidence": 1.0,
                    },
                }
            )

        return pd.DataFrame(keyword_rows)
