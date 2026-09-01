from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
import logging

import pandas as pd

from etl_extractors.kaggle.kaggle_helper import KaggleHelper


logger = logging.getLogger(__name__)


class KaggleSharedByClient:
    """Build Kaggle sharedBy entity metadata from detected names.

    Kaggle reports the uploader as a bare display name on the models endpoint
    - there is no id, profile url or user/organization flag - so a sharedBy
    entity is the name plus its minted ``mlentory_id``.
    """

    def __init__(self, records_data=None) -> None:
        self.records_data = records_data or {}

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

    def get_sharedby_metadata(self, names: List[str]) -> pd.DataFrame:
        unique_names = sorted({str(name).strip() for name in names if str(name).strip()})
        extraction_time = self._extraction_time()

        records: List[Dict[str, Any]] = []
        for name in unique_names:
            records.append(
                {
                    "sharedById": name,
                    "mlentory_id": KaggleHelper.generate_mlentory_entity_hash_id(
                        "SharedBy", name, platform="Kaggle"
                    ),
                    "name": name,
                    "enriched": True,
                    # Kaggle does not distinguish users from organizations on
                    # this endpoint, so Organization matches the AI4Life
                    # treatment rather than guessing per record.
                    "entity_type": "Organization",
                    "platform": "Kaggle",
                    "extraction_metadata": {
                        "extraction_method": "kaggle_sharedby_identifier",
                        "confidence": 1.0,
                        "source_field": "sharedBy",
                        "extraction_time": extraction_time,
                    },
                }
            )

        logger.info("Prepared metadata for %d Kaggle sharedBy entities", len(records))
        return pd.DataFrame(records)