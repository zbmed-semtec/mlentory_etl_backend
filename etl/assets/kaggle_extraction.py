"""
Dagster assets for Kaggle model-card extraction.

Pipeline:
1) Create run folder: /data/1_raw/kaggle/<timestamp_uuid>/
2) Build owner/slug refs from the Meta Kaggle dataset
3) Fetch model cards from the Kaggle API (parallel, resumable, incremental)
4) Normalize records and persist under the run folder

Crawl state lives in /data/1_raw/kaggle/_state/ rather than the run folder:
resume and incremental refresh both work by reading what previous runs
collected, so a per-run location would reset them every time and turn every
run into a fresh multi-hour crawl.
"""

import os  
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple, List, Dict, Any, Set

import pandas as pd
from dagster import AssetIn, asset

from etl.config import get_kaggle_config
from etl_extractors.kaggle import KaggleExtractor
from etl_extractors.kaggle.kaggle_crawler import KaggleCrawler
from etl_extractors.kaggle.kaggle_helper import KaggleHelper
from etl_extractors.kaggle.kaggle_enrichment import KaggleEnrichment

logger = logging.getLogger(__name__)


KAGGLE_ROOT = Path("/data/1_raw/kaggle")
STATE_DIR = Path(os.getenv("CACHE_PATH", "/data/cache")) / "kaggle"


@asset(group_name="kaggle_extraction", tags={"pipeline": "Kaggle_etl"})
def kaggle_run_folder() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = str(uuid.uuid4())[:8]
    run_folder = KAGGLE_ROOT / f"{timestamp}_{run_id}"
    run_folder.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Created Kaggle run folder: %s", run_folder)
    return str(run_folder)

@asset(
    group_name="kaggle_extraction",
    tags={"pipeline": "Kaggle_etl"},
    ins={"run_folder": AssetIn("kaggle_run_folder")},
)
def kaggle_raw_catalog_sources(run_folder: str) -> str:
    """
    Write the canonical Kaggle catalog ``WebSite`` to the raw run folder.
 
    Produces ``sources.json`` (one row) with ``mlentory_id`` and schema.org fields
    so downstream transform/load can align ``MLModel.source`` with extraction.
    """
    out_path = Path(run_folder) / "sources.json"
    payload = KaggleHelper.raw_kaggle_catalog_website_records()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    logger.info("Wrote Kaggle catalog sources to %s", out_path)
    return str(out_path)
 


@asset(group_name="kaggle_extraction", tags={"pipeline": "Kaggle_etl"}, ins={"run_folder": AssetIn("kaggle_run_folder")})
def kaggle_model_refs(run_folder: str) -> List[str]:
    """Build the owner/slug ref list from the Meta Kaggle dataset."""
    config = get_kaggle_config()
    crawler = KaggleCrawler(
        output_dir=str(STATE_DIR),
        threads=config.threads,
        meta_dataset=config.meta_dataset,
    )
    crawler.check_credentials()

    if config.refresh_metadata:
        crawler.ensure_meta_kaggle_csvs(force=True)
    refs = crawler.load_or_build_refs(rebuild=config.refresh_metadata)

    logger.info("Built %d Kaggle model refs for run %s", len(refs), run_folder)
    return refs


@asset(group_name="kaggle_extraction", tags={"pipeline": "Kaggle_etl"}, ins={"run_folder": AssetIn("kaggle_run_folder"), "refs": AssetIn("kaggle_model_refs")})
def kaggle_raw_records(run_folder: str, refs: List[str]) -> Dict[str, Any]:
    """Fetch raw model cards from the Kaggle API and set extraction timestamp."""
    config = get_kaggle_config()
    extractor = KaggleExtractor()

    records_data, extraction_timestamp = extractor.fetch_records(
        output_dir=str(STATE_DIR),
        num_models=config.num_models,
        incremental=config.incremental,
        force_full_refresh=config.force_full_refresh,
        refresh_metadata=False,  # already refreshed by kaggle_model_refs
        threads=config.threads,
        max_retries=config.max_retries,
        request_timeout_seconds=config.request_timeout_seconds,
        checkpoint_every=config.checkpoint_every,
        meta_dataset=config.meta_dataset,
    )
    
    records_data["timestamp"] = extraction_timestamp

    summary = records_data.get("summary", {})
    logger.info(
        "Kaggle fetch: %d records, %d failed, %.1f min, %.2f rec/s",
        len(records_data.get("data", [])), summary.get("failed", 0),
        summary.get("elapsed_s", 0) / 60, summary.get("records_per_second", 0),
    )
    
 
    # Save merged records to run folder
    run_folder_path = Path(run_folder)
    record_path = run_folder_path / "records.json"
    record_path.write_text(json.dumps(records_data, indent=2), encoding="utf-8")
    payload = {
        "run_folder": run_folder,
        "data": records_data
    }
    return payload


@asset(group_name="kaggle_extraction", tags={"pipeline": "Kaggle_etl"}, ins={"raw_data": AssetIn("kaggle_raw_records")})
def kaggle_models_raw(raw_data: Dict[str, Any]) -> Tuple[str, str]:
    extractor = KaggleExtractor(records_data=raw_data['data'])
    models_df = extractor.extract_models()
    models_df = KaggleHelper.deduplicate_models(models_df)

    models_path = Path(raw_data['run_folder']) / "models.json"
    models_df.to_json(models_path, orient="records", indent=2)
    logger.info("Saved %d models to %s", len(models_df), models_path)
    return (str(models_path), raw_data['run_folder'])

@asset(
    group_name="kaggle_enrichment",
    ins={"models_data": AssetIn("kaggle_models_raw")},
    tags={"pipeline": "Kaggle_etl", "stage": "extract"}
)
def kaggle_identified_instances(models_data: Tuple[str, str]) -> Dict[str, List[str]]:
    """
    Identify model instance references per model from raw Kaggle models.
 
    A Kaggle model is a container; its downloadable artifacts are instances,
    one per framework and variation, each with its own license, version, size
    and URL.
 
    Args:
        models_data: Tuple of (models_json_path, run_folder)
 
    Returns:
        Dict of {model_id: [instance_ids]}
    """
    models_json_path, _ = models_data
    enrichment = KaggleEnrichment()
    models_df = KaggleHelper.load_models_dataframe(models_json_path)
 
    model_instances = enrichment.identifiers["instances"].identify_per_model(models_df)
    logger.info("Identified instances for %d models", len(model_instances))
    return model_instances

@asset(
    group_name="kaggle_enrichment",
    tags={"pipeline": "Kaggle_etl"},
    ins={
        "raw_records": AssetIn("kaggle_raw_records"),
        "identified_instances": AssetIn("kaggle_identified_instances"),
    },
)
def kaggle_instances_raw(
    raw_records: Dict[str, Any],
    identified_instances: Dict[str, List[str]],
) -> Tuple[str, str]:
    """
    Build model instance entity records and save to instances.json.
    Returns (instances_json_path, run_folder).
    """
    records = raw_records["data"]
    run_folder = raw_records["run_folder"]
 
    instance_ids: Set[str] = set()
    for _, ids in identified_instances.items():
        instance_ids.update([x for x in ids if x])
 
    if not instance_ids:
        logger.info("No instances to extract")
        return ("", run_folder)
 
    extractor = KaggleExtractor(records_data=records)
    instances_df = extractor.extract_specific_instances(sorted(instance_ids))
 
    instances_path = Path(run_folder) / "instances.json"
    instances_df.to_json(str(instances_path), orient="records", indent=2)
 
    logger.info("Saved %d instances to %s", len(instances_df), instances_path)
    return (str(instances_path), run_folder)


