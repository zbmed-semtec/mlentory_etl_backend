from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Set, Tuple, List, Optional
import logging

import pandas as pd

from dagster import asset, AssetIn

from extractors.hf import HFExtractor, HFEnrichment, HFHelper


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


@asset(group_name="hf")
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
)
def hf_identified_datasets(models_data: Tuple[str, str]) -> Tuple[Set[str], str]:
    """
    Identify dataset references from raw HF models.
    
    Args:
        models_data: Tuple of (models_json_path, run_folder)
        
    Returns:
        Tuple of (dataset_names, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)
    
    datasets = enrichment.identifiers["datasets"].identify(models_df)
    logger.info(f"Identified {len(datasets)} unique datasets")
    
    return (datasets, run_folder)


@asset(
    group_name="hf_enrichment",
    ins={"datasets_data": AssetIn("hf_identified_datasets")},
)
def hf_enriched_datasets(datasets_data: Tuple[Set[str], str]) -> str:
    """
    Extract metadata for identified datasets from HuggingFace.
    
    Args:
        datasets_data: Tuple of (dataset_names, run_folder)
        
    Returns:
        Path to the saved datasets JSON file
    """
    dataset_names, run_folder = datasets_data
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
)
def hf_identified_articles(models_data: Tuple[str, str]) -> Tuple[Set[str], str]:
    """
    Identify arXiv article references from raw HF models.
    
    Args:
        models_data: Tuple of (models_json_path, run_folder)
        
    Returns:
        Tuple of (arxiv_ids, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)
    
    articles = enrichment.identifiers["articles"].identify(models_df)
    logger.info(f"Identified {len(articles)} unique arXiv articles")
    
    return (articles, run_folder)


@asset(
    group_name="hf_enrichment",
    ins={"articles_data": AssetIn("hf_identified_articles")},
)
def hf_enriched_articles(articles_data: Tuple[Set[str], str]) -> str:
    """
    Extract metadata for identified arXiv articles.
    
    Args:
        articles_data: Tuple of (arxiv_ids, run_folder)
        
    Returns:
        Path to the saved articles JSON file
    """
    arxiv_ids, run_folder = articles_data
    extractor = HFExtractor()
    
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
)
def hf_identified_keywords(models_data: Tuple[str, str]) -> Tuple[Set[str], str]:
    """
    Identify keywords/tags from raw HF models.
    
    Args:
        models_data: Tuple of (models_json_path, run_folder)
        
    Returns:
        Tuple of (keywords, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)
    
    keywords = enrichment.identifiers["keywords"].identify(models_df)
    logger.info(f"Identified {len(keywords)} unique keywords")
    
    return (keywords, run_folder)


@asset(
    group_name="hf_enrichment",
    ins={"keywords_data": AssetIn("hf_identified_keywords")},
)
def hf_enriched_keywords(keywords_data: Tuple[Set[str], str]) -> str:
    """
    Extract metadata for identified keywords.
    
    Args:
        keywords_data: Tuple of (keywords, run_folder)
        
    Returns:
        Path to the saved keywords JSON file
    """
    keywords, run_folder = keywords_data
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
)
def hf_identified_licenses(models_data: Tuple[str, str]) -> Tuple[Set[str], str]:
    """
    Identify license references from raw HF models.
    
    Args:
        models_data: Tuple of (models_json_path, run_folder)
        
    Returns:
        Tuple of (license_ids, run_folder)
    """
    models_json_path, run_folder = models_data
    enrichment = HFEnrichment()
    models_df = HFHelper.load_models_dataframe(models_json_path)
    
    licenses = enrichment.identifiers["licenses"].identify(models_df)
    logger.info(f"Identified {len(licenses)} unique licenses")
    
    return (licenses, run_folder)


@asset(
    group_name="hf_enrichment",
    ins={"licenses_data": AssetIn("hf_identified_licenses")},
)
def hf_enriched_licenses(licenses_data: Tuple[Set[str], str]) -> str:
    """
    Extract metadata for identified licenses.
    
    Args:
        licenses_data: Tuple of (license_ids, run_folder)
        
    Returns:
        Path to the saved licenses JSON file
    """
    license_ids, run_folder = licenses_data
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
