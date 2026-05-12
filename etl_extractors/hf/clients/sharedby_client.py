"""Hugging Face sharedBy metadata client."""

from __future__ import annotations

from typing import Any, Dict, List
import logging

import pandas as pd

from ..hf_helper import HFHelper


logger = logging.getLogger(__name__)


class HFSharedByClient:
    """Build lightweight sharedBy entity metadata from detected names."""

    def get_sharedby_metadata(self, names: List[str]) -> pd.DataFrame:
        unique_names = sorted({str(name).strip() for name in names if str(name).strip()})

        records: List[Dict[str, Any]] = []
        for name in unique_names:
            records.append(
                {
                    "name": name,
                    "mlentory_id": HFHelper.generate_mlentory_entity_hash_id("SharedBy", name),
                    "entity_type": "Organization",
                    "platform": "HF",
                    "enriched": True,
                    "extraction_metadata": {
                        "extraction_method": "hf_sharedby_identifier",
                        "confidence": 1.0,
                        "source_field": "sharedBy",
                    },
                }
            )

        logger.info("Prepared metadata for %d sharedBy entities", len(records))
        return pd.DataFrame(records)

