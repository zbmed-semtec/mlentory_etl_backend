from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import pandas as pd
from ..ai4life_helper import AI4LifeHelper
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
class AI4LifeDatasetsClient:
    """
    Client for interacting with HuggingFace datasets (Croissant metadata).
    """
    def __init__(self, records_data) -> None:
        self.records_data = records_data
        self.dataset_records = None
    def get_datasets_metadata(self, dataset_names):
        """get records from AI4Life API and set extraction timestamp."""
        # Filter records by type
        dataset_records = [r for r in self.records_data['data'] if r.get("type") == "dataset"]
        self.dataset_records = dataset_records
        dataset_metadata = [self.get_dataset_metadata(dataset_name) for dataset_name in dataset_names]
        # Filter out None values (datasets that weren't found)
        dataset_metadata = [d for d in dataset_metadata if d is not None]
        if not dataset_metadata:
            # Return empty DataFrame with correct structure
            return pd.DataFrame()
        dataset_metadata_df = pd.DataFrame(dataset_metadata)
        return dataset_metadata_df
    def get_dataset_metadata(self, dataset_name):
        if not self.dataset_records:
            return None
        for record in self.dataset_records:
            record_id = record.get('id', '')
            manifest = record.get('manifest', {})
            manifest_id = manifest.get('id', '')
            if record_id == "bioimage-io/"+str(dataset_name) or manifest_id == dataset_name:
                # Extract dataset_id (last part after "/" if exists)
                raw_id = record.get('id') or ""
                dataset_id = str(raw_id).split("/", 1)[-1]  # keep last part
                # Safe date conversion helper
                def safe_iso_date(ts):
                    if isinstance(ts, (int, float)):
                        try:
                            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                        except Exception:
                            return ""
                    return ""
                # Convert extraction timestamp to format YYYY-MM-DD_HH-MM-SS for extraction_time
                extraction_timestamp = self.records_data.get("timestamp", "")
                extraction_time = ""
                if extraction_timestamp:
                    try:
                        # Parse ISO format timestamp and convert to YYYY-MM-DD_HH-MM-SS
                        if isinstance(extraction_timestamp, str):
                            dt = datetime.fromisoformat(extraction_timestamp.replace('Z', '+00:00'))
                        else:
                            dt = datetime.fromtimestamp(extraction_timestamp, tz=timezone.utc)
                        extraction_time = dt.strftime("%Y-%m-%d_%H-%M-%S")
                    except Exception:
                        extraction_time = ""
                # paths to extract (do NOT store path-lists in output)
                path_map: Dict[str, Any] = {
                    "dataset_id": dataset_id,
                    "mlentory_id": AI4LifeHelper.generate_mlentory_entity_hash_id("Dataset", record_id),
                    "name": manifest.get('name', ''),
                    "description": manifest.get('description', ''),
                    "creator": manifest.get('authors', ''),
                    "keywords": manifest.get('tags', ''),
                    "version": manifest.get('version', ''),
                    "date_created": safe_iso_date(record.get('created_at')),
                    "date_modified": safe_iso_date(record.get('last_modified')),
                    "citation": manifest.get('cite', ''),
                    "license": manifest.get('license', ''),
                    "url": f"https://bioimage.io/#/artifacts/{dataset_id}",
                    "extraction_metadata": {
                        "extraction_method": "Hypha API",
                        "confidence": 1.0,
                        "extraction_time": extraction_time
                    },
                    "enriched": True,
                    "entity_type": "Dataset",
                    "platform": "AI4Life"
                }
                return path_map
        return None
