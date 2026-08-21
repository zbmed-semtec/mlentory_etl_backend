from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from etl_extractors.kaggle.kaggle_helper import KaggleHelper

logger = logging.getLogger(__name__)


class KaggleFrameworkClient:
    """
    Client for interacting with Kaggle Model frameworks.

    Kaggle reports a framework as a bare name on each model instance
    ("PyTorch", "Keras", "TensorFlow2", "ScikitLearn", "Transformers") - there
    is no id, version or url in the response - so a framework entity is the
    name plus its minted ``mlentory_id``.

    These are frameworks, not architectures: they describe the format an
    instance ships in, not the model's design.
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

    def get_frameworks_metadata(self, framework_names: List[str]) -> pd.DataFrame:
        # make unique + deterministic
        framework_names = sorted(
            {str(x).strip() for x in framework_names if x and str(x).strip()}
        )
        extraction_time = self._extraction_time()

        all_framework_data: List[Dict[str, Any]] = []

        for framework_name in framework_names:
            framework_data: Dict[str, Any] = {
                "frameworkId": framework_name,
                "mlentory_id": KaggleHelper.generate_mlentory_entity_hash_id(
                    "Framework", framework_name, platform="Kaggle"
                ),
                "name": framework_name,
                "enriched": True,
                "entity_type": "Framework",
                "platform": "Kaggle",
                "extraction_metadata": {
                    "extraction_method": "Kaggle_models_endpoint",
                    "confidence": 1.0,
                    "extraction_time": extraction_time,
                },
            }
            all_framework_data.append(framework_data)

        logger.info("Extracted %d distinct frameworks", len(all_framework_data))
        return pd.DataFrame(all_framework_data)