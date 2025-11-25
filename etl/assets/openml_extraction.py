"""
Dagster assets for OpenML data extraction.

This module defines a complete extraction pipeline for OpenML:
1. Create a unique run folder
2. Extract runs metadata
3. Identify and extract related entities (datasets only)

All outputs are saved to /data/raw/openml/<timestamp_uuid>/ for traceability.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Set, Tuple
import logging

from dagster import asset, AssetIn

from etl_extractors.openml import OpenMLExtractor, OpenMLEnrichment
from etl.config import get_openml_config


logger = logging.getLogger(__name__)


# ========== Run Folder Creation ==========


@asset(group_name="openml", tags={"pipeline": "openml_etl"})
def openml_run_folder() -> str:
    """
    Create a unique run folder for this materialization.
    
    All assets in this run will save outputs to this folder, ensuring
    that outputs from a single run are grouped together.
    
    Returns:
        Path to the run-specific output directory
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    run_folder_name = f"{timestamp}_{run_id}"
    
    run_folder = Path("/data/1_raw/openml") / run_folder_name
    run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created run folder: {run_folder}")
    return str(run_folder)


# ========== Runs Extraction ==========


@asset(
    group_name="openml",
    tags={"pipeline": "openml_etl"},
    ins={"run_folder": AssetIn("openml_run_folder")},
)
def openml_raw_runs(run_folder: str) -> Tuple[str, str]:
    """
    Extract raw OpenML run metadata and persist JSON under the run folder.
    
    Args:
        run_folder: Path to the run-specific output directory
    
    Returns:
        Tuple of (runs_json_path, run_folder) to pass to downstream assets
    """
    config = get_openml_config()
    
    extractor = OpenMLExtractor(enable_scraping=config.enable_scraping)
    
    try:
        output_root = Path(run_folder).parent.parent  # Go up to /data
        df, output_path = extractor.extract_runs(
            num_instances=config.num_instances,
            offset=config.offset,
            threads=config.threads,
            output_root=output_root,
        )
        
        # Move the file to the run folder with a clean name
        run_folder_path = Path(run_folder)
        final_path = run_folder_path / "runs.json"
        Path(output_path).rename(final_path)
        
        logger.info(f"OpenML raw runs saved to {final_path}")
        return (str(final_path), run_folder)
    
    finally:
        # Clean up extractor resources (browser pool if enabled)
        extractor.close()


# ========== Dataset Enrichment Assets ==========


@asset(
    group_name="openml_enrichment",
    tags={"pipeline": "openml_etl"},
    ins={"runs_data": AssetIn("openml_raw_runs")},
)
def openml_identified_datasets(runs_data: Tuple[str, str]) -> Tuple[Set[int], str]:
    """
    Identify dataset references from raw OpenML runs.
    
    Args:
        runs_data: Tuple of (runs_json_path, run_folder)
        
    Returns:
        Tuple of (dataset_ids, run_folder)
    """
    runs_json_path, run_folder = runs_data
    enrichment = OpenMLEnrichment()
    runs_df = enrichment._load_runs_dataframe(runs_json_path)
    
    datasets = enrichment.identifiers["datasets"].identify(runs_df)
    logger.info(f"Identified {len(datasets)} unique datasets")
    
    return (datasets, run_folder)


@asset(
    group_name="openml_enrichment",
    tags={"pipeline": "openml_etl"},
    ins={"datasets_data": AssetIn("openml_identified_datasets")},
)
def openml_enriched_datasets(datasets_data: Tuple[Set[int], str]) -> str:
    """
    Extract metadata for identified datasets from OpenML.
    
    Args:
        datasets_data: Tuple of (dataset_ids, run_folder)
        
    Returns:
        Path to the saved datasets JSON file
    """
    dataset_ids, run_folder = datasets_data
    config = get_openml_config()
    
    extractor = OpenMLExtractor(enable_scraping=config.enable_scraping)
    
    try:
        if not dataset_ids:
            logger.info("No datasets to extract")
            return ""
        
        logger.info(f"Extracting {len(dataset_ids)} datasets")
        output_root = Path(run_folder).parent.parent  # Go up to /data
        _, json_path = extractor.extract_specific_datasets(
            dataset_ids=list(dataset_ids),
            threads=config.enrichment_threads,
            output_root=output_root,
        )
        
        # Move to run folder with clean name
        final_path = Path(run_folder) / "datasets.json"
        Path(json_path).rename(final_path)
        
        logger.info(f"Datasets saved to {final_path}")
        return str(final_path)
    
    finally:
        # Clean up extractor resources
        extractor.close()


## Flows and tasks enrichment removed — only datasets are enriched.


