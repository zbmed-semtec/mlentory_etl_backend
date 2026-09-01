from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from etl_extractors.kaggle.kaggle_helper import KaggleHelper

logger = logging.getLogger(__name__)


class KaggleLicenseClient:
    """
    Client for interacting with Kaggle Model licenses.

    Kaggle reports a license as a bare name ("MIT", "Apache 2.0") on each
    model instance - there is no id, url or SPDX identifier in the response -
    so a license entity is the name plus its minted ``mlentory_id``.

    A model can carry instances under different licenses, so one model may
    map to several license entities.
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

    def get_licenses_metadata(self, license_ids: List[str]) -> pd.DataFrame:
        # make unique + deterministic
        license_ids = sorted({str(x).strip() for x in license_ids if x and str(x).strip()})
        extraction_time = self._extraction_time()

        all_license_data: List[Dict[str, Any]] = []

        for license_id in license_ids:
            license_data: Dict[str, Any] = {
                "licenseId": license_id,
                "mlentory_id": KaggleHelper.generate_mlentory_entity_hash_id(
                    "License", license_id, platform="Kaggle"
                ),
                "name": license_id,
                "enriched": True,
                "entity_type": "License",
                "platform": "Kaggle",
                "extraction_metadata": {
                    "extraction_method": "Kaggle_models_endpoint",
                    "confidence": 1.0,
                    "extraction_time": extraction_time,
                },
            }
            all_license_data.append(license_data)

        logger.info("Extracted %d distinct licenses", len(all_license_data))
        return pd.DataFrame(all_license_data)