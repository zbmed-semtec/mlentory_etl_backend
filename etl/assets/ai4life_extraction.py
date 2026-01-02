"""
Dagster assets for AI4Life extraction.

Pipeline:
1) Create run folder: /data/raw/ai4life/<timestamp_uuid>/
2) Fetch raw records from AI4Life API
3) Filter by type (model/dataset/application) and wrap with extraction metadata
4) Persist each entity type under the run folder
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Any
import json
import logging
import pandas as pd

from dagster import asset, AssetIn

from etl_extractors.ai4life.ai4life_extractor import AI4LifeExtractor
from etl.config import get_ai4life_config


logger = logging.getLogger(__name__)


@asset(group_name="ai4life_extraction", tags={"pipeline": "ai4life_etl"})
def ai4life_run_folder() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    run_folder = Path("/data/1_raw/ai4life") / f"{timestamp}_{run_id}"
    run_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Created AI4Life run folder: %s", run_folder)
    return str(run_folder)


@asset(group_name="ai4life_extraction", tags={"pipeline": "ai4life_etl"}, ins={"run_folder": AssetIn("ai4life_run_folder")})
def ai4life_raw_records(run_folder: str) -> Dict[str, Any]:
    """
    Fetch raw records from AI4Life API.
    Returns (records_list, run_folder, extractor_with_timestamp).
    """
    config = get_ai4life_config()
    extractor = AI4LifeExtractor()

    records, extraction_timestamp = extractor.fetch_records(config.num_models, config.base_url, config.parent_id)
    logger.info("Fetched %d AI4Life records", len(records))
    records_data = {}
    records_data['data'] = records
    records_data['timestamp'] = extraction_timestamp 
    
    # Save merged dataframe to run folder
    run_folder_path = Path(run_folder)
    record_path = run_folder_path / "records.json"
    record_path.write_text(json.dumps(records_data, indent=2), encoding="utf-8")
    payload = {
        "run_folder": run_folder,
        "data": records_data
    }
    return payload


@asset(group_name="ai4life", tags={"pipeline": "ai4life_etl"}, ins={"raw_data": AssetIn("ai4life_raw_records")})
def ai4life_models_raw(raw_data: Dict[str, Any]) -> Tuple[str, str]:
    """
    Filter model records and wrap with extraction metadata.
    Returns (models_json_path, run_folder).
    """
    extractor = AI4LifeExtractor(records_data = raw_data['data'])
    models_df = extractor.extract_models()
    
    # Save to JSON
    models_path = Path(raw_data['run_folder']) / "models.json"
    models_df.to_json(models_path, orient="records", indent=2)
    logger.info("Saved %d models to %s", len(models_df), models_path)
    return (str(models_path), raw_data['run_folder'])


# @asset(group_name="ai4life", tags={"pipeline": "ai4life_etl"}, ins={"raw_data": AssetIn("ai4life_raw_records")})
# def ai4life_datasets_raw(raw_data: Tuple[List[Dict[str, Any]], str, AI4LifeExtractor]) -> Tuple[str, str]:
#     """
#     Filter dataset records and wrap with extraction metadata.
#     Returns (datasets_json_path, run_folder).
#     """
#     records, run_folder, extractor = raw_data
    
#     # Filter records by type
#     datasets = [r for r in records if r.get("type") == "dataset"]
    
#     # Wrap each dataset with metadata
#     # wrapped_datasets = [extractor.wrap_record_with_metadata(d) for d in datasets]
    
#     # Save to JSON
#     datasets_path = Path(run_folder) / "datasets.json"
#     datasets_path.write_text(json.dumps(datasets, indent=2), encoding="utf-8")
    
#     logger.info("Saved %d datasets to %s", len(datasets), datasets_path)
#     return (str(datasets_path), run_folder)


# @asset(group_name="ai4life", tags={"pipeline": "ai4life_etl"}, ins={"raw_data": AssetIn("ai4life_raw_records")})
# def ai4life_applications_raw(raw_data: Tuple[List[Dict[str, Any]], str, AI4LifeExtractor]) -> Tuple[str, str]:
#     """
#     Filter application records and wrap with extraction metadata.
#     Returns (applications_json_path, run_folder).
#     """
#     records, run_folder, extractor = raw_data
    
#     # Filter records by type
#     applications = [r for r in records if r.get("type") == "application"]
    
#     # Wrap each application with metadata
#     # wrapped_applications = [extractor.wrap_record_with_metadata(a) for a in applications]
    
#     # Save to JSON
#     applications_path = Path(run_folder) / "applications.json"
#     applications_path.write_text(json.dumps(applications, indent=2), encoding="utf-8")
    
#     logger.info("Saved %d applications to %s", len(applications), applications_path)
#     return (str(applications_path), run_folder)


