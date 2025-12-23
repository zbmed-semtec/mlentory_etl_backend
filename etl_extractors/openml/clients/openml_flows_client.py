"""
Client for fetching OpenML flow (model) metadata.
"""

from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

import pandas as pd
import openml

logger = logging.getLogger(__name__)


class OpenMLFlowsClient:
    """
    Client for interacting with OpenML flows API.

    Fetches flow (model) metadata by ID.
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

    def get_flow_metadata(self, flow_id: int) -> Optional[Dict]:
        """
        Fetch metadata for a single flow.
        """
        logger.info("Fetching metadata for flow_id=%s", flow_id)
        try:
            flow = openml.flows.get_flow(int(flow_id))

            # best-effort fields; some may be missing depending on API
            uploader = getattr(flow, "uploader", None)
            upload_date = None
            try:
                upload_date = (
                    flow.upload_date.isoformat()
                    if getattr(flow, "upload_date", None)
                    else None
                )
            except Exception:
                upload_date = None

            language = getattr(flow, "language", None)
            description = getattr(flow, "description", None)
            tags = list(flow.tags) if getattr(flow, "tags", None) else []

            metadata = {
                "flow_id": int(flow.flow_id) if getattr(flow, "flow_id", None) else int(flow_id),
                "name": getattr(flow, "name", None),
                "version": getattr(flow, "version", None),
                "description": description,
                "uploader": uploader,
                "upload_date": upload_date,
                "language": language,
                "tags": tags,
                "url": f"https://www.openml.org/f/{flow_id}",
            }

            return metadata
        except Exception as exc:
            logger.error("Error fetching flow %s: %s", flow_id, exc, exc_info=True)
            return None

    def get_specific_flows_metadata(
        self, flow_ids: List[int], threads: int = 4
    ) -> pd.DataFrame:
        """
        Fetch metadata for specific flows using multithreading.
        """
        logger.info(
            "Fetching metadata for %d flows with threads=%s",
            len(flow_ids),
            threads,
        )
        flow_metadata: List[Dict] = []

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(self.get_flow_metadata, fid): fid for fid in flow_ids}
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    flow_metadata.append(result)

        logger.info("Successfully fetched %d flows", len(flow_metadata))
        return pd.DataFrame(flow_metadata)

