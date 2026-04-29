from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple
import json
import logging
import re

import pandas as pd

from .base import EntityIdentifier


logger = logging.getLogger(__name__)


class TaskIdentifier(EntityIdentifier):
    """Identify AI4Life tasks from model tags, description, and documentation fields."""

    TASK_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
        ("instance-segmentation", re.compile(r"\binstance[\s_-]*segmentation\b", re.I)),
        ("semantic-segmentation", re.compile(r"\bsemantic[\s_-]*segmentation\b", re.I)),
        ("image-segmentation", re.compile(r"\bsegmentation\b", re.I)),
        ("image-classification", re.compile(r"\bclassification\b", re.I)),
        ("object-detection", re.compile(r"\b(object[\s_-]*)?detection\b", re.I)),
        ("image-restoration", re.compile(r"\brestoration\b", re.I)),
        ("image-denoising", re.compile(r"\bdenois\w*\b", re.I)),
        ("image-super-resolution", re.compile(r"\bsuper[\s_-]*resolution\b", re.I)),
        ("image-inpainting", re.compile(r"\binpaint\w*\b", re.I)),
        ("object-tracking", re.compile(r"\btracking\b", re.I)),
        ("image-registration", re.compile(r"\bregistration\b", re.I)),
        ("object-counting", re.compile(r"\bcounting\b", re.I)),
    ]

    @property
    def entity_type(self) -> str:
        return "tasks"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        tasks: Set[str] = set()
        if models_df is None or models_df.empty:
            return tasks

        for _, row in models_df.iterrows():
            tasks.update(self._extract_tasks_from_row(row))

        logger.info("Identified %d unique AI4Life tasks", len(tasks))
        return tasks

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, List[str]]:
        model_tasks: Dict[str, List[str]] = {}
        if models_df is None or models_df.empty:
            return model_tasks

        for _, row in models_df.iterrows():
            model_id = row.get("modelId") or row.get("id") or row.get("model_id") or row.get("name")
            if not model_id:
                continue
            model_tasks[str(model_id)] = sorted(self._extract_tasks_from_row(row))

        logger.info("Identified AI4Life tasks for %d models", len(model_tasks))
        return model_tasks

    def _extract_tasks_from_row(self, row: pd.Series) -> Set[str]:
        tasks_from_tags = self._tasks_from_text(" ".join(self._extract_tags(row)))
        if tasks_from_tags:
            return tasks_from_tags

        description = self._first_non_empty_text(
            row.get("description"),
            row.get("intendedUse"),
            row.get("intentedUse"),
        )
        tasks_from_description = self._tasks_from_text(description)
        if tasks_from_description:
            return tasks_from_description

        documentation = self._first_non_empty_text(
            row.get("documentation"),
            row.get("readme_file"),
            row.get("readme"),
        )
        return self._tasks_from_text(documentation)

    def _extract_tags(self, row: pd.Series) -> List[str]:
        candidates: List[Any] = [
            row.get("tags"),
            row.get("keywords"),
        ]

        tags: List[str] = []
        for candidate in candidates:
            parsed = self._safe_json_loads(candidate)
            if isinstance(parsed, list):
                tags.extend([str(x) for x in parsed if isinstance(x, (str, int, float))])
            elif isinstance(parsed, str):
                tags.extend([x.strip() for x in parsed.split(",") if x.strip()])

        normalized = [self._normalize_token(t) for t in tags if str(t).strip()]
        return list(dict.fromkeys([x for x in normalized if x]))

    @staticmethod
    def _safe_json_loads(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return value
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return value
        return value

    @staticmethod
    def _normalize_token(value: str) -> str:
        token = value.strip().lower()
        token = token.replace("_", "-").replace(" ", "-")
        token = re.sub(r"-{2,}", "-", token).strip("-")
        return token

    @staticmethod
    def _first_non_empty_text(*values: Any) -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    def _tasks_from_text(self, text: str) -> Set[str]:
        if not text:
            return set()

        out: List[str] = []
        for task_name, pattern in self.TASK_PATTERNS:
            if pattern.search(text):
                out.append(task_name)
        return set(out)
