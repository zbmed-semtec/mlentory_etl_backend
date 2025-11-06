"""Identifier for Hugging Face tasks referenced in model metadata."""

from __future__ import annotations

from typing import Dict, List, Optional, Set
from pathlib import Path
import logging

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class TaskIdentifier(EntityIdentifier):
    """Detect Hugging Face tasks from model metadata tags and pipeline information."""

    TASKS_URL = "https://huggingface.co/tasks"
    DEFAULT_CSV_PATH = Path("/data/refs/hf_tasks.csv")

    def __init__(
        self,
        *,
        tasks_csv_path: Path | str | None = None,
        session: Optional[requests.Session] = None,
        timeout: int = 30,
    ) -> None:
        self.tasks_csv_path = Path(tasks_csv_path or self.DEFAULT_CSV_PATH)
        self.session = session or requests.Session()
        self.timeout = timeout
        self._tasks_df: Optional[pd.DataFrame] = None
        self._task_lookup: Optional[Dict[str, str]] = None

    @property
    def entity_type(self) -> str:
        return "tasks"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        tasks: Set[str] = set()

        if models_df.empty:
            return tasks

        for _, row in models_df.iterrows():
            tasks.update(self._extract_tasks_from_row(row))

        logger.info("Identified %d unique tasks", len(tasks))
        return tasks

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        model_tasks: Dict[str, List[str]] = {}

        if models_df.empty:
            return model_tasks

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id")
            if not model_id:
                continue

            tasks = sorted(self._extract_tasks_from_row(row))
            if tasks:
                model_tasks[str(model_id)] = tasks
            else:
                model_tasks[str(model_id)] = []

        logger.info("Identified tasks for %d models", len(model_tasks))
        return model_tasks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_tasks_from_row(self, row: pd.Series) -> Set[str]:
        task_slugs: Set[str] = set()
        lookup = self._get_task_lookup()

        candidates: List[str] = []

        pipeline_tag = row.get("pipeline_tag")
        if isinstance(pipeline_tag, str):
            candidates.append(pipeline_tag)

        tags = row.get("tags")
        if isinstance(tags, list):
            candidates.extend(tag for tag in tags if isinstance(tag, str))

        for candidate in candidates:
            normalized = self._normalize(candidate)
            slug = lookup.get(normalized)
            if slug:
                task_slugs.add(slug)

        return task_slugs

    def _get_task_lookup(self) -> Dict[str, str]:
        if self._task_lookup is not None:
            return self._task_lookup

        catalog_df = self._ensure_tasks_catalog()
        if catalog_df.empty:
            self._task_lookup = {}
            return self._task_lookup

        lookup: Dict[str, str] = {}

        for _, record in catalog_df.iterrows():
            slug = str(record.get("task", "")).strip().lower()

            candidates = {
                slug,
                slug.replace("-", "_"),
                self._normalize(str(record.get("task", ""))),
            }

            for candidate in candidates:
                if candidate:
                    lookup[candidate] = slug

        self._task_lookup = lookup
        logger.info("Loaded %d known HF tasks for lookup", len(self._task_lookup))
        return self._task_lookup

    # ------------------------------------------------------------------
    # Catalog management
    # ------------------------------------------------------------------

    def get_tasks_catalog(self) -> pd.DataFrame:
        catalog_df = self._ensure_tasks_catalog()
        return catalog_df.copy()

    def refresh_tasks_catalog(self) -> pd.DataFrame:
        logger.info("Refreshing Hugging Face tasks catalog from %s", self.TASKS_URL)
        self._tasks_df = self._scrape_tasks_catalog()
        self._persist_catalog(self._tasks_df)
        self._task_lookup = None
        return self.get_tasks_catalog()

    def _ensure_tasks_catalog(self) -> pd.DataFrame:
        if self._tasks_df is not None:
            return self._tasks_df

        if self.tasks_csv_path.exists():
            try:
                self._tasks_df = pd.read_csv(self.tasks_csv_path)
                return self._tasks_df
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to load HF tasks catalog from %s (%s); rebuilding",
                    self.tasks_csv_path,
                    exc,
                )

        self._tasks_df = self._scrape_tasks_catalog()
        self._persist_catalog(self._tasks_df)
        return self._tasks_df

    def _persist_catalog(self, df: pd.DataFrame) -> None:
        if df.empty:
            return

        self.tasks_csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(self.tasks_csv_path, index=False)
        logger.info("Saved HF tasks catalog to %s", self.tasks_csv_path)

    def _scrape_tasks_catalog(self) -> pd.DataFrame:
        html = self._fetch_tasks_html()
        if not html:
            return pd.DataFrame(columns=["task", "category"])

        soup = BeautifulSoup(html, "lxml")

        records: List[Dict[str, str]] = []
        seen_slugs: Set[str] = set()

        for header in soup.select("main h2"):
            category = header.get_text(strip=True)
            if not category:
                continue

            section = header.find_next_sibling()
            while section and section.name not in {"div", "section", "ul"}:
                section = section.find_next_sibling()

            if section is None:
                continue

            for link in section.select('a[href^="/tasks/"]'):
                task_name = link.get_text(strip=True)
                href = link.get("href")

                if not task_name or not href:
                    continue

                slug = href.rstrip("/").split("/")[-1]
                if not slug or slug in seen_slugs:
                    continue

                seen_slugs.add(slug)

                records.append(
                    {
                        "task": slug.replace("-", " "),
                        "category": category,
                    }
                )

        if not records:
            logger.warning("No tasks discovered from %s", self.TASKS_URL)
            return pd.DataFrame(columns=["task", "category"])

        df = pd.DataFrame(records)
        df = df.sort_values(["category", "task"]).reset_index(drop=True)
        return df

    def _fetch_tasks_html(self) -> str:
        try:
            response = self.session.get(self.TASKS_URL, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to fetch HF tasks catalog from %s: %s", self.TASKS_URL, exc)
            return ""

    @staticmethod
    def _normalize(value: str) -> str:
        if not value:
            return ""

        normalized = value.strip().lower()
        normalized = normalized.replace(" ", "-")
        normalized = normalized.replace("_", "-")
        return normalized


