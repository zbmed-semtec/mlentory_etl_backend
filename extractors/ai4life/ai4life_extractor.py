from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging

import requests


logger = logging.getLogger(__name__)


class AI4LifeExtractor:
    """Extractor for fetching raw model metadata from the AI4Life platform."""

    def __init__(
        self,
        base_url: str = "https://hypha.aicell.io",
        parent_id: str = "bioimage-io/bioimage.io",
    ) -> None:
        self.base_url = base_url
        self.parent_id = parent_id
        self.extraction_timestamp: str | None = None

    def fetch_records(self, num_models: int) -> Dict[str, Any]:
        """Fetch records from AI4Life API and set extraction timestamp."""
        try:
            response = requests.get(
                f"{self.base_url}/public/services/artifact-manager/list",
                params={"parent_id": self.parent_id, "limit": num_models},
                timeout=15,
            )
            self.extraction_timestamp = datetime.utcnow().isoformat()
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to fetch AI4Life records: {exc}") from exc

    def wrap_record_with_metadata(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Wrap each field in a record with extraction metadata following OpenML pattern."""
        wrapped: Dict[str, Any] = {}
        for key, value in record.items():
            wrapped[key] = [
                {
                    "data": value,
                    "extraction_method": "hypha_api",
                    "confidence": 1,
                    "extraction_time": self.extraction_timestamp,
                }
            ]
        return wrapped


