"""
Dagster assets for AI4Life extraction.

Pipeline:
1) Create run folder: /data/raw/ai4life/<timestamp_uuid>/
2) Fetch raw records from AI4Life API
3) Filter by type (model/dataset/application) and wrap with extraction metadata
4) Persist each entity type under the run folder
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Any
import json
import logging

from dagster import asset, AssetIn

from extractors.ai4life.ai4life_extractor import AI4LifeExtractor


logger = logging.getLogger(__name__)


@dataclass
class AI4LifeConfig:
    num_models: int = int(os.getenv("AI4LIFE_NUM_MODELS", "50"))
    base_url: str = os.getenv("AI4LIFE_BASE_URL", "https://hypha.aicell.io")
    parent_id: str = os.getenv("AI4LIFE_PARENT_ID", "bioimage-io/bioimage.io")


@asset(group_name="ai4life")
def ai4life_run_folder() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    run_folder = Path("/data/raw/ai4life") / f"{timestamp}_{run_id}"
    run_folder.mkdir(parents=True, exist_ok=True)
    logger.info("Created AI4Life run folder: %s", run_folder)
    return str(run_folder)


@asset(group_name="ai4life", ins={"run_folder": AssetIn("ai4life_run_folder")})
def ai4life_raw_records(run_folder: str) -> Tuple[List[Dict[str, Any]], str, AI4LifeExtractor]:
    """
    Fetch raw records from AI4Life API.
    Returns (records_list, run_folder, extractor_with_timestamp).
    """
    cfg = AI4LifeConfig()
    extractor = AI4LifeExtractor(base_url=cfg.base_url, parent_id=cfg.parent_id)

    records = extractor.fetch_records(cfg.num_models)

    # Extract list from response (support both list and dict with 'data' key)
    data = records if isinstance(records, list) else records.get("data", [])

    logger.info("Fetched %d AI4Life records", len(data))
    return (data, run_folder, extractor)


@asset(group_name="ai4life", ins={"raw_data": AssetIn("ai4life_raw_records")})
def ai4life_models_raw(raw_data: Tuple[List[Dict[str, Any]], str, AI4LifeExtractor]) -> Tuple[str, str]:
    """
    Filter model records and wrap with extraction metadata.
    Returns (models_json_path, run_folder).
    """
    records, run_folder, extractor = raw_data
    
    # Filter records by type
    models = [r for r in records if r.get("type") == "model"]
    
    # Wrap each model with metadata
    # wrapped_models = [extractor.wrap_record_with_metadata(m) for m in models]
    
    # Save to JSON
    models_path = Path(run_folder) / "models.json"
    models_path.write_text(json.dumps(models, indent=2), encoding="utf-8")
    
    logger.info("Saved %d models to %s", len(models), models_path)
    return (str(models_path), run_folder)


@asset(group_name="ai4life", ins={"raw_data": AssetIn("ai4life_raw_records")})
def ai4life_datasets_raw(raw_data: Tuple[List[Dict[str, Any]], str, AI4LifeExtractor]) -> Tuple[str, str]:
    """
    Filter dataset records and wrap with extraction metadata.
    Returns (datasets_json_path, run_folder).
    """
    records, run_folder, extractor = raw_data
    
    # Filter records by type
    datasets = [r for r in records if r.get("type") == "dataset"]
    
    # Wrap each dataset with metadata
    # wrapped_datasets = [extractor.wrap_record_with_metadata(d) for d in datasets]
    
    # Save to JSON
    datasets_path = Path(run_folder) / "datasets.json"
    datasets_path.write_text(json.dumps(datasets, indent=2), encoding="utf-8")
    
    logger.info("Saved %d datasets to %s", len(datasets), datasets_path)
    return (str(datasets_path), run_folder)


@asset(group_name="ai4life", ins={"raw_data": AssetIn("ai4life_raw_records")})
def ai4life_applications_raw(raw_data: Tuple[List[Dict[str, Any]], str, AI4LifeExtractor]) -> Tuple[str, str]:
    """
    Filter application records and wrap with extraction metadata.
    Returns (applications_json_path, run_folder).
    """
    records, run_folder, extractor = raw_data
    
    # Filter records by type
    applications = [r for r in records if r.get("type") == "application"]
    
    # Wrap each application with metadata
    # wrapped_applications = [extractor.wrap_record_with_metadata(a) for a in applications]
    
    # Save to JSON
    applications_path = Path(run_folder) / "applications.json"
    applications_path.write_text(json.dumps(applications, indent=2), encoding="utf-8")
    
    logger.info("Saved %d applications to %s", len(applications), applications_path)
    return (str(applications_path), run_folder)


