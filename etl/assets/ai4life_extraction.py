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
from typing import Tuple, List, Dict, Any, Set
import json
import logging
import pandas as pd
import pycountry
from dagster import asset, AssetIn
from etl_extractors.ai4life.ai4life_enrichment import AI4LifeEnrichment
from etl_extractors.ai4life.ai4life_helper import AI4LifeHelper
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


@asset(
    group_name="ai4life_extraction",
    tags={"pipeline": "ai4life_etl"},
    ins={"run_folder": AssetIn("ai4life_run_folder")},
)
def ai4life_raw_catalog_sources(run_folder: str) -> str:
    """
    Write the canonical AI4Life catalog ``WebSite`` to the raw run folder.

    Produces ``sources.json`` (one row) with ``mlentory_id`` and schema.org fields
    so downstream transform/load can align ``MLModel.source`` with extraction.
    """
    out_path = Path(run_folder) / "sources.json"
    payload = AI4LifeHelper.raw_ai4life_catalog_website_records()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    logger.info("Wrote AI4Life catalog sources to %s", out_path)
    return str(out_path)


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


@asset(group_name="ai4life_extraction", tags={"pipeline": "ai4life_etl"}, ins={"raw_data": AssetIn("ai4life_raw_records")})
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


@asset(
    group_name="ai4life_enrichment",
    ins={"models_data": AssetIn("ai4life_models_raw")},
    tags={"pipeline": "ai4life_etl", "stage": "extract"}
)
def ai4life_identified_datasets(models_data: Tuple[str, str]) -> Dict[str, List[str]]:
    """
    Identify dataset references per model from raw HF models.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Tuple of ({model_id: [dataset_names]}, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = AI4LifeEnrichment()
    models_df = AI4LifeHelper.load_models_dataframe(models_json_path)

    model_datasets = enrichment.identifiers["datasets"].identify_per_model(models_df)
    logger.info(f"Identified datasets for {len(model_datasets)} models")
    return model_datasets



@asset(group_name="ai4life_enrichment", tags={"pipeline": "ai4life_etl"}, 
     ins={
        "raw_records": AssetIn("ai4life_raw_records"),
        "identified_datasets": AssetIn("ai4life_identified_datasets"),
    },)
def ai4life_datasets_raw(
    raw_records: Dict[str, Any],              
    identified_datasets: Dict[str, List[str]]) -> Tuple[str, str]:
    """
    Filter dataset records and wrap with extraction metadata.
    Returns (datasets_json_path, run_folder).
    """
    records = raw_records['data']
    run_folder = raw_records['run_folder']
    extractor = AI4LifeExtractor(records_data = records)
    dataset_names = set()
    for model_id, datasets in identified_datasets.items():
        dataset_names.update(datasets)
    dataset_df = extractor.extract_specific_datasets(dataset_names)
  
    # Save to JSON
    datasets_path = Path(run_folder) / "datasets.json"
    dataset_df.to_json(datasets_path, orient="records", indent=2)
    
    logger.info("Saved %d datasets to %s", len(dataset_df), datasets_path)
    return (str(datasets_path), run_folder)


@asset(
    group_name="ai4life_enrichment",
    ins={"models_data": AssetIn("ai4life_models_raw")},
    tags={"pipeline": "ai4life_etl", "stage": "extract"}
)
def ai4life_identified_licenses(models_data: Tuple[str, str]) -> Dict[str, List[str]]:
    """
    Identify license references per model from raw AI4Life models.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Dict of {model_id: [license_ids_or_names]}
    """
    models_json_path, _ = models_data
    enrichment = AI4LifeEnrichment()
    models_df = AI4LifeHelper.load_models_dataframe(models_json_path)

    model_licenses = enrichment.identifiers["licenses"].identify_per_model(models_df)
    logger.info("Identified licenses for %d models", len(model_licenses))
    return model_licenses

@asset(
    group_name="ai4life_enrichment",
    tags={"pipeline": "ai4life_etl"},
    ins={
        "raw_records": AssetIn("ai4life_raw_records"),
        "identified_licenses": AssetIn("ai4life_identified_licenses"),
    },
)
def ai4life_licenses_raw(
    raw_records: Dict[str, Any],
    identified_licenses: Dict[str, List[str]],
) -> Tuple[str, str]:
    """
    Extract license records and save to licenses.json.
    Returns (licenses_json_path, run_folder).
    """
    records = raw_records["data"]
    run_folder = raw_records["run_folder"]

    # Collect unique licenses
    license_names: Set[str] = set()
    for _, lic_list in identified_licenses.items():
        license_names.update([x for x in lic_list if x])

    if not license_names:
        logger.info("No licenses to extract")
        return ("", run_folder)

    extractor = AI4LifeExtractor(records_data=records)
    license_df = extractor.extract_specific_licenses(list(license_names))

    license_path = Path(run_folder) / "licenses.json"
    license_df.to_json(str(license_path), orient="records", indent=2)

    logger.info("Saved %d licenses to %s", len(license_df), license_path)
    return (str(license_path), run_folder)

@asset(
    group_name="ai4life_enrichment",
    ins={"models_data": AssetIn("ai4life_models_raw")},
    tags={"pipeline": "ai4life_etl", "stage": "extract"}
)
def ai4life_identified_keywords(models_data: Tuple[str, str]) -> Dict[str, List[str]]:
    """
    Identify keyword references per model from raw AI4Life models.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Dict of {model_id: [keyword_names]}
    """
    models_json_path, _ = models_data
    enrichment = AI4LifeEnrichment()
    models_df = AI4LifeHelper.load_models_dataframe(models_json_path)

    model_keywords = enrichment.identifiers["keywords"].identify_per_model(models_df)
    logger.info("Identified keywords for %d models", len(model_keywords))
    return model_keywords

@asset(
    group_name="ai4life_enrichment",
    tags={"pipeline": "ai4life_etl"},
    ins={
        "raw_records": AssetIn("ai4life_raw_records"),
        "identified_keywords": AssetIn("ai4life_identified_keywords"),
    },
)
def ai4life_keywords_raw(
    raw_records: Dict[str, Any],
    identified_keywords: Dict[str, List[str]],
) -> Tuple[str, str]:
    """
    Extract keyword records and save to licenses.json.
    Returns (keywords_json_path, run_folder).
    """
    records = raw_records["data"]
    run_folder = raw_records["run_folder"]

    # Collect unique keywords
    keywords_names: Set[str] = set()
    for _, keyword_list in identified_keywords.items():
        keywords_names.update([x for x in keyword_list if x])

    if not keywords_names:
        logger.info("No keywords to extract")
        return ("", run_folder)

    extractor = AI4LifeExtractor(records_data=records)
    keywords_df = extractor.extract_specific_keywords(list(keywords_names))

    keywords_path = Path(run_folder) / "keywords.json"
    keywords_df.to_json(str(keywords_path), orient="records", indent=2)

    logger.info("Saved %d keywords to %s", len(keywords_df), keywords_path)
    return (str(keywords_path), run_folder)


@asset(
    group_name="ai4life_enrichment",
    ins={"models_data": AssetIn("ai4life_models_raw")},
    tags={"pipeline": "ai4life_etl", "stage": "extract"}
)
def ai4life_identified_tasks(models_data: Tuple[str, str]) -> Dict[str, List[str]]:
    """
    Identify ML task references per model from AI4Life model metadata.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Dict of {model_id: [task_names]}
    """
    models_json_path, _ = models_data
    enrichment = AI4LifeEnrichment()
    models_df = AI4LifeHelper.load_models_dataframe(models_json_path)

    model_tasks = enrichment.identifiers["tasks"].identify_per_model(models_df)
    logger.info("Identified tasks for %d models", len(model_tasks))
    return model_tasks


@asset(
    group_name="ai4life_enrichment",
    tags={"pipeline": "ai4life_etl"},
    ins={
        "raw_records": AssetIn("ai4life_raw_records"),
        "identified_tasks": AssetIn("ai4life_identified_tasks"),
    },
)
def ai4life_tasks_raw(
    raw_records: Dict[str, Any],
    identified_tasks: Dict[str, List[str]],
) -> Tuple[str, str]:
    """
    Build task entity records from identified AI4Life tasks and save to tasks.json.
    Returns (tasks_json_path, run_folder).
    """
    run_folder = raw_records["run_folder"]

    task_names: Set[str] = set()
    for _, task_list in identified_tasks.items():
        task_names.update([x for x in task_list if x])

    if not task_names:
        logger.info("No tasks to extract")
        return ("", run_folder)

    extractor = AI4LifeExtractor(records_data=raw_records["data"])
    tasks_df = extractor.extract_tasks(sorted(task_names))

    tasks_path = Path(run_folder) / "tasks.json"
    tasks_df.to_json(str(tasks_path), orient="records", indent=2)

    logger.info("Saved %d tasks to %s", len(tasks_df), tasks_path)
    return (str(tasks_path), run_folder)


@asset(
    group_name="ai4life_enrichment",
    ins={"models_data": AssetIn("ai4life_models_raw")},
    tags={"pipeline": "ai4life_etl", "stage": "extract"}
)
def ai4life_identified_sharedby(models_data: Tuple[str, str]) -> Dict[str, List[str]]:
    """
    Identify sharedBy entities per model from AI4Life model metadata.
    """
    models_json_path, _ = models_data
    enrichment = AI4LifeEnrichment()
    models_df = AI4LifeHelper.load_models_dataframe(models_json_path)

    model_sharedby = enrichment.identifiers["sharedby"].identify_per_model(models_df)
    logger.info("Identified sharedBy entities for %d models", len(model_sharedby))
    return model_sharedby


@asset(
    group_name="ai4life_enrichment",
    ins={"models_data": AssetIn("ai4life_models_raw")},
    tags={"pipeline": "ai4life_etl", "stage": "extract"},
)
def ai4life_detected_inlanguage(models_data: Tuple[str, str]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Detect documentation/description languages per model for schema:inLanguage.
    """
    from etl_extractors.common.text_language_detector import detect_language_predictions

    models_json_path, _ = models_data
    with open(models_json_path, "r", encoding="utf-8") as file_handle:
        raw_models = json.load(file_handle)

    if not isinstance(raw_models, list):
        logger.warning("Expected list of models at %s", models_json_path)
        return {}

    detected: Dict[str, List[Dict[str, Any]]] = {}
    for idx, raw_model in enumerate(raw_models):
        if not isinstance(raw_model, dict):
            continue

        model_id = str(raw_model.get("modelId", "")).strip() or f"unknown_{idx}"
        text_parts = [
            str(raw_model.get("description", "")).strip(),
            str(raw_model.get("intendedUse", "")).strip(),
            str(raw_model.get("name", "")).strip(),
        ]
        detected[model_id] = detect_language_predictions(
            "\n\n".join([part for part in text_parts if part]),
            min_confidence=0.75,
            max_languages=5,
        )

    logger.info("Detected inLanguage values for %d AI4Life models", len(detected))
    return detected


@asset(
    group_name="ai4life_enrichment",
    ins={
        "models_data": AssetIn("ai4life_models_raw"),
        "inlanguage_mapping": AssetIn("ai4life_detected_inlanguage"),
    },
    tags={"pipeline": "ai4life_etl", "stage": "extract"},
)
def ai4life_languages_raw(
    models_data: Tuple[str, str],
    inlanguage_mapping: Dict[str, List[Dict[str, Any]]],
) -> str:
    """
    Persist detected language metadata to raw run folder as ``languages.json``.

    This mirrors HF extraction behavior so language artifacts are available under
    ``/data/1_raw/ai4life/<run>/`` before transformation.
    """
    _, run_folder = models_data

    per_code_confidence: Dict[str, float] = {}
    for predictions in (inlanguage_mapping or {}).values():
        for prediction in (predictions or []):
            if not isinstance(prediction, dict):
                continue
            code = str(prediction.get("code", "")).strip().lower()
            if not code:
                continue
            confidence = float(prediction.get("confidence", 0.0) or 0.0)
            per_code_confidence[code] = max(per_code_confidence.get(code, 0.0), confidence)

    records: List[Dict[str, Any]] = []
    for code in sorted(per_code_confidence.keys()):
        language = pycountry.languages.get(alpha_2=code) or pycountry.languages.get(alpha_3=code)
        records.append(
            {
                "code": code,
                "alpha_2": getattr(language, "alpha_2", None) if language else None,
                "alpha_3": getattr(language, "alpha_3", None) if language else None,
                "name": getattr(language, "name", None) if language else code,
                "scope": getattr(language, "scope", None) if language else None,
                "type": getattr(language, "type", None) if language else None,
                "mlentory_id": AI4LifeHelper.generate_mlentory_entity_hash_id("Language", code),
                "enriched": language is not None,
                "entity_type": "Language",
                "platform": "AI4Life",
                "extraction_metadata": {
                    "extraction_method": "lingua-language-detector+pycountry",
                    "confidence": per_code_confidence[code],
                },
            }
        )

    out_path = Path(run_folder) / "languages.json"
    with open(out_path, "w", encoding="utf-8") as file_handle:
        json.dump(records, file_handle, indent=2, ensure_ascii=False)

    logger.info("Saved %d AI4Life languages to %s", len(records), out_path)
    return str(out_path)


@asset(
    group_name="ai4life_enrichment",
    tags={"pipeline": "ai4life_etl"},
    ins={
        "raw_records": AssetIn("ai4life_raw_records"),
        "identified_sharedby": AssetIn("ai4life_identified_sharedby"),
    },
)
def ai4life_sharedby_raw(
    raw_records: Dict[str, Any],
    identified_sharedby: Dict[str, List[str]],
) -> Tuple[str, str]:
    """
    Build sharedBy entity records and save to sharedby.json.
    Returns (sharedby_json_path, run_folder).
    """
    run_folder = raw_records["run_folder"]
    sharedby_names: Set[str] = set()
    for _, names in identified_sharedby.items():
        sharedby_names.update([x for x in names if x])

    if not sharedby_names:
        logger.info("No sharedBy entities to extract")
        return ("", run_folder)

    extractor = AI4LifeExtractor(records_data=raw_records["data"])
    sharedby_df = extractor.extract_sharedby(sorted(sharedby_names))

    sharedby_path = Path(run_folder) / "sharedby.json"
    sharedby_df.to_json(str(sharedby_path), orient="records", indent=2)

    logger.info("Saved %d sharedBy entities to %s", len(sharedby_df), sharedby_path)
    return (str(sharedby_path), run_folder)


# # @asset(group_name="ai4life", tags={"pipeline": "ai4life_etl"}, ins={"raw_data": AssetIn("ai4life_raw_records")})
# # def ai4life_applications_raw(raw_data: Tuple[List[Dict[str, Any]], str, AI4LifeExtractor]) -> Tuple[str, str]:
# #     """
# #     Filter application records and wrap with extraction metadata.
# #     Returns (applications_json_path, run_folder).
# #     """
# #     records, run_folder, extractor = raw_data
    
# #     # Filter records by type
# #     applications = [r for r in records if r.get("type") == "application"]
    
# #     # Wrap each application with metadata
# #     # wrapped_applications = [extractor.wrap_record_with_metadata(a) for a in applications]
    
# #     # Save to JSON
# #     applications_path = Path(run_folder) / "applications.json"
# #     applications_path.write_text(json.dumps(applications, indent=2), encoding="utf-8")
    
# #     logger.info("Saved %d applications to %s", len(applications), applications_path)
# #     return (str(applications_path), run_folder)


