from __future__ import annotations

from typing import Any, Dict, List
import logging

import pandas as pd

from ..ai4life_helper import AI4LifeHelper


logger = logging.getLogger(__name__)


class AI4LifeTasksClient:
    """Create AI4Life task entity metadata from detected task names."""

    def get_tasks_metadata(self, task_names: List[str]) -> pd.DataFrame:
        unique_tasks = sorted({str(x).strip() for x in task_names if str(x).strip()})

        rows: List[Dict[str, Any]] = []
        for task_name in unique_tasks:
            rows.append(
                {
                    "task": task_name,
                    "name": task_name,
                    "url": None,
                    "term_code": task_name,
                    "mlentory_id": AI4LifeHelper.generate_mlentory_entity_hash_id("Task", task_name),
                    "entity_type": "Task",
                    "platform": "AI4Life",
                    "enriched": True,
                    "extraction_metadata": {
                        "extraction_method": "ai4life_task_identifier",
                        "confidence": 1.0,
                        "source_field": "tags|description|documentation",
                        "notes": "Task inferred from AI4Life model metadata with fallback priority",
                    },
                }
            )

        logger.info("Prepared metadata for %d AI4Life tasks", len(rows))
        return pd.DataFrame(rows)
