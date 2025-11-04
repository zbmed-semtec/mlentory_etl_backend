from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Set, Tuple, List, Optional, Dict
import logging

import pandas as pd

from dagster import asset, AssetIn

from etl_extractors.hf import HFExtractor, HFEnrichment, HFHelper


logger = logging.getLogger(__name__)


def _read_model_ids_from_file(file_path: str) -> List[str]:
    """
    Read model IDs from a text file (one per line).
    
    Args:
        file_path: Path to the file containing model IDs
        
    Returns:
        List of model IDs, with empty lines and comments removed
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"Model IDs file not found: {file_path}")
        return []
    
    model_ids = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                model_ids.append(line)
    
    logger.info(f"Read {len(model_ids)} model IDs from {file_path}")
    return model_ids


@dataclass
class HFModelsExtractionConfig:
    num_models: int = int(os.getenv("HF_NUM_MODELS", "50"))
    update_recent: bool = os.getenv("HF_UPDATE_RECENT", "true").lower() == "true"
    threads: int = int(os.getenv("HF_THREADS", "4"))
    models_file_path: str = os.getenv("HF_MODELS_FILE_PATH", "/data/config/hf_model_ids.txt")
    base_model_iterations: int = int(os.getenv("HF_BASE_MODEL_ITERATIONS", "1"))


@dataclass
class HFEnrichmentConfig:
    threads: int = int(os.getenv("HF_ENRICHMENT_THREADS", "4"))


@asset(group_name="hf", tags={"pipeline": "hf_etl"})
def hf_run_folder() -> str:
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
    
    run_folder = Path("/data/raw/hf") / run_folder_name
    run_folder.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Created run folder: {run_folder}")
    return str(run_folder)


@asset(
    group_name="hf",
    ins={"run_folder": AssetIn("hf_run_folder")},
    tags={"pipeline": "hf_etl"}
)
def hf_raw_models_latest(run_folder: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Extract the latest N HF models using get_model_metadata_dataset.
    
    Args:
        run_folder: Path to the run-specific output directory
    
    Returns:
        Tuple of (models_dataframe, run_folder) to pass to merge asset
    """
    config = HFModelsExtractionConfig()
    extractor = HFExtractor()
    
    output_root = Path(run_folder).parent.parent  # Go up to /data
    df, output_path = extractor.extract_models(
        num_models=config.num_models,
        update_recent=config.update_recent,
        threads=config.threads,
        output_root=output_root,
    )
    
    # Clean up the temporary file created by extractor
    Path(output_path).unlink(missing_ok=True)
    
    logger.info(f"Extracted {len(df)} latest models")
    return (df, run_folder)


@asset(
    group_name="hf",
    ins={"run_folder": AssetIn("hf_run_folder")},
    tags={"pipeline": "hf_etl"}
)
def hf_raw_models_from_file(run_folder: str) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Extract HF models from a file containing model IDs (one per line).
    
    Args:
        run_folder: Path to the run-specific output directory
    
    Returns:
        Tuple of (models_dataframe, run_folder) to pass to merge asset
    """
    config = HFModelsExtractionConfig()
    extractor = HFExtractor()
    
    # Read model IDs from file
    model_ids = _read_model_ids_from_file(config.models_file_path)
    
    if not model_ids:
        logger.info("No model IDs found in file, skipping file-based extraction")
        return (None, run_folder)
    
    output_root = Path(run_folder).parent.parent  # Go up to /data
    df, output_path = extractor.extract_specific_models(
        model_ids=model_ids,
        threads=config.threads,
        save_csv=False,
    )
    
    # Clean up the temporary file created by extractor
    Path(output_path).unlink(missing_ok=True)
    
    logger.info(f"Extracted {len(df)} models from file")
    return (df, run_folder)


@asset(
    group_name="hf",
    ins={
        "latest_data": AssetIn("hf_raw_models_latest"),
        "file_data": AssetIn("hf_raw_models_from_file"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_raw_models(
    latest_data: Tuple[Optional[pd.DataFrame], str],
    file_data: Tuple[Optional[pd.DataFrame], str],
) -> Tuple[str, str]:
    """
    Merge models from both extraction modes (latest N + file-based).
    
    Combines models from both sources, removing duplicates based on model ID.
    
    Args:
        latest_data: Tuple of (models_df, run_folder) from latest extraction
        file_data: Tuple of (models_df, run_folder) from file-based extraction
    
    Returns:
        Tuple of (merged_models_json_path, run_folder) to pass to downstream assets
    """
    latest_df, run_folder = latest_data
    file_df, _ = file_data
    
    # Collect non-None dataframes
    dfs_to_merge = []
    if latest_df is not None and not latest_df.empty:
        dfs_to_merge.append(latest_df)
        logger.info(f"Including {len(latest_df)} models from latest extraction")
    
    if file_df is not None and not file_df.empty:
        dfs_to_merge.append(file_df)
        logger.info(f"Including {len(file_df)} models from file extraction")
    
    # Merge and deduplicate
    if not dfs_to_merge:
        logger.warning("No models extracted from either source!")
        # Create an empty dataframe with expected structure
        merged_df = pd.DataFrame()
    elif len(dfs_to_merge) == 1:
        merged_df = dfs_to_merge[0]
    else:
        merged_df = pd.concat(dfs_to_merge, ignore_index=True)
        # Remove duplicates based on model_id (assuming 'id' or 'modelId' column exists)
        id_column = 'id' if 'id' in merged_df.columns else 'modelId'
        if id_column in merged_df.columns:
            before_count = len(merged_df)
            merged_df = merged_df.drop_duplicates(subset=[id_column], keep='first')
            after_count = len(merged_df)
            logger.info(f"Removed {before_count - after_count} duplicate models")
    
    # Save merged dataframe to run folder
    run_folder_path = Path(run_folder)
    final_path = run_folder_path / "hf_models.json"
    merged_df.to_json(path_or_buf=str(final_path), orient="records", indent=2, date_format="iso")
    
    logger.info(f"Merged {len(merged_df)} total models saved to {final_path}")
    return (str(final_path), run_folder)
# ========== Individual Entity Enrichment Assets ==========

@asset(
    group_name="hf_enrichment",
    ins={"models_data": AssetIn("hf_raw_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_add_ancestor_models(models_data: Tuple[str, str]) -> Tuple[str, str]:
    """
    Iteratively extract metadata for base models discovered in HF models.

    The extraction loop follows newly identified base model references up to
    ``HF_BASE_MODEL_ITERATIONS`` iterations. Each iteration fetches metadata for
    newly discovered base models and inspects the results to find additional
    references, avoiding duplicate downloads.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Path to the saved base models JSON file (``hf_models_with_ancestors.json``)
    """
    models_json_path, run_folder = models_data
    config = HFModelsExtractionConfig()
    extractor = HFExtractor()
    enrichment = HFEnrichment(extractor=extractor)
    
    models_df = HFHelper.load_models_dataframe(models_json_path)
    
    df_with_ancestors = enrichment.enrich_with_ancestor_models(
        current_models_dataframe=models_df,
        depth_iterations=config.base_model_iterations,
        threads=config.threads,
    )

    # Move to run folder with clean name
    final_path = Path(run_folder) / "hf_models_with_ancestors.json"
    df_with_ancestors.to_json(path_or_buf=str(final_path), orient="records", indent=2, date_format="iso")
    
    logger.info(f"Base models with ancestors saved to {final_path}")
    return (str(final_path), run_folder)

@asset(
    group_name="hf_enrichment",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_identified_datasets(models_data: Tuple[str, str]) -> Tuple[Dict[str, List[str]], str]:
    """
    Identify dataset references per model from raw HF models.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Tuple of ({model_id: [dataset_names]}, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)

    model_datasets = enrichment.identifiers["datasets"].identify_per_model(models_df)
    logger.info(f"Identified datasets for {len(model_datasets)} models")

    return (model_datasets, run_folder)


@asset(
    group_name="hf_enrichment",
    ins={"datasets_data": AssetIn("hf_identified_datasets")},
    tags={"pipeline": "hf_etl"}
)
def hf_enriched_datasets(datasets_data: Tuple[Dict[str, List[str]], str]) -> str:
    """
    Extract metadata for identified datasets from HuggingFace.
    
    Args:
        datasets_data: Tuple of (dataset_names, run_folder)
        
    Returns:
        Path to the saved datasets JSON file
    """
    model_datasets_dict, run_folder = datasets_data
    dataset_names = set()
    for model_id, datasets in model_datasets_dict.items():
        dataset_names.update(datasets)
    
    config = HFEnrichmentConfig()
    extractor = HFExtractor()
    
    if not dataset_names:
        logger.info("No datasets to extract")
        return ""
    
    logger.info(f"Extracting {len(dataset_names)} datasets")
    output_root = Path(run_folder).parent.parent  # Go up to /data
    _, json_path = extractor.extract_specific_datasets(
        dataset_names=list(dataset_names),
        threads=config.threads,
        output_root=output_root,
    )
    
    # Move to run folder with clean name
    final_path = Path(run_folder) / "hf_datasets_specific.json"
    Path(json_path).rename(final_path)
    
    logger.info(f"Datasets saved to {final_path}")
    return str(final_path)


@asset(
    group_name="hf_enrichment",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_identified_articles(models_data: Tuple[str, str]) -> Tuple[Dict[str, List[str]], str]:
    """
    Identify arXiv article references per model from raw HF models.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Tuple of ({model_id: [arxiv_ids]}, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)

    model_articles = enrichment.identifiers["articles"].identify_per_model(models_df)
    logger.info(f"Identified arXiv articles for {len(model_articles)} models")

    return (model_articles, run_folder)


@asset(
    group_name="hf_enrichment",
    ins={"articles_data": AssetIn("hf_identified_articles")},
    tags={"pipeline": "hf_etl"}
)
def hf_enriched_articles(articles_data: Tuple[Dict[str, List[str]], str]) -> str:
    """
    Extract metadata for identified arXiv articles.
    
    Args:
        articles_data: Tuple of (arxiv_ids, run_folder)
        
    Returns:
        Path to the saved articles JSON file
    """
    model_articles_dict, run_folder = articles_data
    extractor = HFExtractor()
    
    arxiv_ids = set()
    
    for model_id, articles in model_articles_dict.items():
        arxiv_ids.update(articles)
    
    if not arxiv_ids:
        logger.info("No articles to extract")
        return ""
    
    
    logger.info(f"Extracting {len(arxiv_ids)} arXiv articles")
    output_root = Path(run_folder).parent.parent  # Go up to /data
    _, json_path = extractor.extract_specific_arxiv(
        arxiv_ids=list(arxiv_ids),
        output_root=output_root,
    )
    
    # Move to run folder with clean name
    final_path = Path(run_folder) / "arxiv_articles.json"
    Path(json_path).rename(final_path)
    
    logger.info(f"Articles saved to {final_path}")
    return str(final_path)


@asset(
    group_name="hf_enrichment",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_identified_keywords(models_data: Tuple[str, str]) -> Tuple[Dict[str, List[str]], str]:
    """
    Identify keywords/tags per model from raw HF models.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Tuple of ({model_id: [keywords]}, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)

    model_keywords = enrichment.identifiers["keywords"].identify_per_model(models_df)
    logger.info(f"Identified keywords for {len(model_keywords)} models")

    return (model_keywords, run_folder)


@asset(
    group_name="hf_enrichment",
    ins={"keywords_data": AssetIn("hf_identified_keywords")},
    tags={"pipeline": "hf_etl"}
)
def hf_enriched_keywords(keywords_data: Tuple[Dict[str, List[str]], str]) -> str:
    """
    Extract metadata for identified keywords.
    
    Args:
        keywords_data: Tuple of (keywords, run_folder)
        
    Returns:
        Path to the saved keywords JSON file
    """
    model_keywords_dict, run_folder = keywords_data
    keywords = set()
    
    for model_id, model_keywords in model_keywords_dict.items():
        keywords.update(model_keywords)
    
    extractor = HFExtractor()
    
    if not keywords:
        logger.info("No keywords to extract")
        return ""
    
    logger.info(f"Extracting {len(keywords)} keywords")
    output_root = Path(run_folder).parent.parent  # Go up to /data
    _, json_path = extractor.extract_keywords(
        keywords=list(keywords),
        output_root=output_root,
    )
    
    # Move to run folder with clean name
    final_path = Path(run_folder) / "keywords.json"
    Path(json_path).rename(final_path)
    
    logger.info(f"Keywords saved to {final_path}")
    return str(final_path)


@asset(
    group_name="hf_enrichment",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_identified_licenses(models_data: Tuple[str, str]) -> Tuple[Dict[str, List[str]], str]:
    """
    Identify license references per model from raw HF models.

    Args:
        models_data: Tuple of (models_json_path, run_folder)

    Returns:
        Tuple of ({model_id: [license_ids]}, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)

    model_licenses = enrichment.identifiers["licenses"].identify_per_model(models_df)
    logger.info(f"Identified licenses for {len(model_licenses)} models")

    return (model_licenses, run_folder)


@asset(
    group_name="hf_enrichment",
    ins={"licenses_data": AssetIn("hf_identified_licenses")},
    tags={"pipeline": "hf_etl"}
)
def hf_enriched_licenses(licenses_data: Tuple[Dict[str, List[str]], str]) -> str:
    """
    Extract metadata for identified licenses.
    
    Args:
        licenses_data: Tuple of (license_ids, run_folder)
        
    Returns:
        Path to the saved licenses JSON file
    """
    model_licenses_dict, run_folder = licenses_data
    license_ids = set()
    for model_id, licenses in model_licenses_dict.items():
        license_ids.update(licenses)
    
    extractor = HFExtractor()
    
    if not license_ids:
        logger.info("No licenses to extract")
        return ""
    
    logger.info(f"Extracting {len(license_ids)} licenses")
    output_root = Path(run_folder).parent.parent  # Go up to /data
    _, json_path = extractor.extract_licenses(
        license_ids=list(license_ids),
        output_root=output_root,
    )
    
    # Move to run folder with clean name
    final_path = Path(run_folder) / "licenses.json"
    Path(json_path).rename(final_path)
    
    logger.info(f"Licenses saved to {final_path}")
    return str(final_path)

@asset(
    group_name="hf_enrichment",
    ins={"models_data": AssetIn("hf_add_ancestor_models")},
    tags={"pipeline": "hf_etl"}
)
def hf_identified_base_models(models_data: Tuple[str, str]) -> Tuple[Dict[str, List[str]], str]:
    """
    Identify related models per model from raw HF models.
    
    Args:
        models_data: Tuple of (models_json_path, run_folder)
    
    Returns:
        Tuple of ({model_id: [related_model_ids]}, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)
    
    model_related_models = enrichment.identifiers["base_models"].identify_per_model(models_df)
    logger.info(f"Identified related models for {len(model_related_models)} models")
    return (model_related_models, run_folder)

@asset(
    group_name="hf_enrichment",
    ins={
        "base_models_data": AssetIn("hf_identified_base_models"),
        "ancestor_models": AssetIn("hf_add_ancestor_models"),
    },
    tags={"pipeline": "hf_etl"}
)
def hf_enriched_base_models(
    base_models_data: Tuple[Dict[str, List[str]], str],
    ancestor_models: Tuple[str, str],
) -> str:
    """
    Aggregate metadata for identified base models and create stubs when missing.

    Args:
        base_models_data: Tuple of ({model_id: [base_model_ids]}, run_folder)
        ancestor_models: Tuple of (hf_models_with_ancestors_path, run_folder)

    Returns:
        Path to the saved base models JSON file
    """
    model_base_models_map, _ = base_models_data
    ancestors_json_path, run_folder = ancestor_models

    # Load extracted ancestor models to see which base models we already have metadata for
    if Path(ancestors_json_path).exists():
        with open(ancestors_json_path, "r", encoding="utf-8") as f:
            ancestor_models_data = json.load(f)
    else:
        logger.warning("Ancestor models file not found at %s", ancestors_json_path)
        ancestor_models_data = []

    ancestor_models_by_id: Dict[str, Dict] = {}
    for model in ancestor_models_data:
        model_id = model.get("modelId") or model.get("id")
        if not model_id:
            continue
        ancestor_models_by_id[model_id] = model

    # Collect all unique base model identifiers
    unique_base_model_ids: Set[str] = set()
    for base_models in model_base_models_map.values():
        unique_base_model_ids.update(base_models)

    logger.info("Evaluating %d unique base models for enrichment", len(unique_base_model_ids))

    base_model_entities: Dict[str, Dict] = {}

    for base_model_id in sorted(unique_base_model_ids):
        mlentory_id = HFHelper.generate_entity_hash("Model", base_model_id)
        if base_model_id in ancestor_models_by_id:
            model_record = dict(ancestor_models_by_id[base_model_id])
            model_record["mlentory_id"] = model_record.get("mlentory_id", mlentory_id)
            model_record["enriched"] = True
            model_record.setdefault("entity_type", "Model")
            model_record.setdefault("platform", "HF")
            base_model_entities[base_model_id] = model_record
        else:
            base_model_entities[base_model_id] = {
                "modelId": base_model_id,
                "mlentory_id": mlentory_id,
                "enriched": False,
                "entity_type": "Model",
                "platform": "HF",
                "extraction_metadata": {
                    "extraction_method": "HF_API",
                    "confidence": 1.0,
                    "extraction_time": datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
                },
            }

    # Persist enriched + stub base model entities
    output_path = Path(run_folder) / "hf_base_models_enriched.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            list(base_model_entities.values()),
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    logger.info(
        "Saved %d base model entities (including stubs) to %s",
        len(base_model_entities),
        output_path,
    )

    return str(output_path)
