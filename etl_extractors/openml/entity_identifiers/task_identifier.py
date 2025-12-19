"""
Identifier for OpenML tasks referenced in run metadata.
"""

from __future__ import annotations
from typing import Set
import pandas as pd
import logging

from .base import EntityIdentifier

logger = logging.getLogger(__name__)


class TaskIdentifier(EntityIdentifier):
    """
    Extracts task IDs from OpenML run metadata.

    Looks for task_id field in run records.
    """

    @property
    def entity_type(self) -> str:
        return "tasks"

    def identify(self, runs_df: pd.DataFrame) -> Set[int]:
        tasks = set()

        if runs_df.empty:
            return tasks

        # Extract task IDs from the task_id column
        tasks = self.extract_ids_from_column(runs_df, "task_id")

        logger.info("Identified %d unique tasks", len(tasks))
        return tasks

