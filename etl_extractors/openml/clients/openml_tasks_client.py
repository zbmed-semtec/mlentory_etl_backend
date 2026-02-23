"""
Client for fetching OpenML task metadata.
"""

from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

import pandas as pd
import openml

logger = logging.getLogger(__name__)


class OpenMLTasksClient:
    """
    Client for interacting with OpenML tasks API.
    """

    def __init__(self):
        pass

    def _wrap_metadata(
        self, value, method: str = "openml_python_package"
    ) -> List[Dict]:
        return [
            {
                "data": value,
                "extraction_method": method,
                "confidence": 1,
                "extraction_time": datetime.utcnow().isoformat(),
            }
        ]

    def get_task_metadata(self, task_id: int) -> Optional[Dict]:
        """
        Fetch metadata for a single task.
        """
        logger.info("Fetching metadata for task_id=%s", task_id)
        try:
            task = openml.tasks.get_task(int(task_id))
            estimation = getattr(task, "estimation_procedure", None)

            metadata = {
                "task_id": int(task.task_id),
                "task_type": getattr(task, "task_type", None),
                "evaluation_measure": getattr(task, "evaluation_measure", None),
                "estimation_procedure": estimation,
                "input": getattr(task, "input", None),
                "creator": getattr(task, "creator", None),
                "tags": list(task.tags) if getattr(task, "tags", None) else [],
                "url": f"https://www.openml.org/t/{task_id}",
            }

            return metadata
        except Exception as exc:
            logger.error("Error fetching task %s: %s", task_id, exc, exc_info=True)
            return None

    def get_specific_tasks_metadata(
        self, task_ids: List[int], threads: int = 4
    ) -> pd.DataFrame:
        """
        Fetch metadata for specific tasks using multithreading.
        """
        logger.info(
            "Fetching metadata for %d tasks with threads=%s",
            len(task_ids),
            threads,
        )
        task_metadata: List[Dict] = []

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(self.get_task_metadata, tid): tid for tid in task_ids}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    task_metadata.append(result)

        logger.info("Successfully fetched %d tasks", len(task_metadata))
        return pd.DataFrame(task_metadata)

