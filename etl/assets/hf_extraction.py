from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Set
import logging

from dagster import asset, AssetIn

from extractors.hf import HFExtractor, HFEnrichment


logger = logging.getLogger(__name__)


@dataclass
class HFModelsExtractionConfig:
    num_models: int = int(os.getenv("HF_NUM_MODELS", "50"))
    update_recent: bool = os.getenv("HF_UPDATE_RECENT", "true").lower() == "true"
    threads: int = int(os.getenv("HF_THREADS", "4"))


@dataclass
class HFEnrichmentConfig:
    threads: int = int(os.getenv("HF_ENRICHMENT_THREADS", "4"))


@asset(group_name="hf")
def hf_raw_models() -> str:
    """
    Extract raw HF model metadata and persist JSON under /data/raw/hf.
    
    Returns:
        Path to the saved models JSON file
    """
    config = HFModelsExtractionConfig()
    extractor = HFExtractor()
    df, output_path = extractor.extract_models(
        num_models=config.num_models,
        update_recent=config.update_recent,
        threads=config.threads,
    )
    logger.info(f"HF raw models saved to {output_path}")
    return str(output_path)


# ========== Individual Entity Enrichment Assets ==========


@asset(
    group_name="hf_enrichment",
    ins={"models_json_path": AssetIn("hf_raw_models")},
)
def hf_identified_datasets(models_json_path: str) -> Set[str]:
    """
    Identify dataset references from raw HF models.
    
    Args:
        models_json_path: Path to the raw models JSON
        
    Returns:
        Set of unique dataset names
    """
    enrichment = HFEnrichment()
    models_df = enrichment._load_models_dataframe(models_json_path)
    
    datasets = enrichment.identifiers["datasets"].identify(models_df)
    logger.info(f"Identified {len(datasets)} unique datasets")
    
    return datasets


@asset(
    group_name="hf_enrichment",
    ins={"dataset_names": AssetIn("hf_identified_datasets")},
)
def hf_enriched_datasets(dataset_names: Set[str]) -> str:
    """
    Extract metadata for identified datasets from HuggingFace.
    
    Args:
        dataset_names: Set of dataset names to extract
        
    Returns:
        Path to the saved datasets JSON file
    """
    config = HFEnrichmentConfig()
    extractor = HFExtractor()
    
    if not dataset_names:
        logger.info("No datasets to extract")
        return ""
    
    logger.info(f"Extracting {len(dataset_names)} datasets")
    _, json_path = extractor.extract_specific_datasets(
        dataset_names=list(dataset_names),
        threads=config.threads,
    )
    
    logger.info(f"Datasets saved to {json_path}")
    return str(json_path)


@asset(
    group_name="hf_enrichment",
    ins={"models_json_path": AssetIn("hf_raw_models")},
)
def hf_identified_articles(models_json_path: str) -> Set[str]:
    """
    Identify arXiv article references from raw HF models.
    
    Args:
        models_json_path: Path to the raw models JSON
        
    Returns:
        Set of unique arXiv IDs
    """
    enrichment = HFEnrichment()
    models_df = enrichment._load_models_dataframe(models_json_path)
    
    articles = enrichment.identifiers["articles"].identify(models_df)
    logger.info(f"Identified {len(articles)} unique arXiv articles")
    
    return articles


@asset(
    group_name="hf_enrichment",
    ins={"arxiv_ids": AssetIn("hf_identified_articles")},
)
def hf_enriched_articles(arxiv_ids: Set[str]) -> str:
    """
    Extract metadata for identified arXiv articles.
    
    Args:
        arxiv_ids: Set of arXiv IDs to extract
        
    Returns:
        Path to the saved articles JSON file
    """
    extractor = HFExtractor()
    
    if not arxiv_ids:
        logger.info("No articles to extract")
        return ""
    
    logger.info(f"Extracting {len(arxiv_ids)} arXiv articles")
    _, json_path = extractor.extract_specific_arxiv(arxiv_ids=list(arxiv_ids))
    
    logger.info(f"Articles saved to {json_path}")
    return str(json_path)


@asset(
    group_name="hf_enrichment",
    ins={"models_json_path": AssetIn("hf_raw_models")},
)
def hf_identified_base_models(models_json_path: str) -> Set[str]:
    """
    Identify base model references from raw HF models.
    
    Args:
        models_json_path: Path to the raw models JSON
        
    Returns:
        Set of unique base model IDs
    """
    enrichment = HFEnrichment()
    models_df = enrichment._load_models_dataframe(models_json_path)
    
    base_models = enrichment.identifiers["base_models"].identify(models_df)
    logger.info(f"Identified {len(base_models)} unique base models")
    
    return base_models


@asset(
    group_name="hf_enrichment",
    ins={
        "base_model_ids": AssetIn("hf_identified_base_models"),
    },
)
def hf_enriched_base_models(
    base_model_ids: Set[str]
) -> str:
    """
    Extract metadata for identified base models from HuggingFace.
    
    This asset depends on datasets being extracted first, as base models
    may reference the same datasets.
    
    Args:
        base_model_ids: Set of base model IDs to extract
        
    Returns:
        Path to the saved base models JSON file
    """
    config = HFEnrichmentConfig()
    extractor = HFExtractor()
    
    if not base_model_ids:
        logger.info("No base models to extract")
        return ""
    
    logger.info(f"Extracting {len(base_model_ids)} base models")
    _, json_path = extractor.extract_specific_models(
        model_ids=list(base_model_ids),
        threads=config.threads,
    )
    
    logger.info(f"Base models saved to {json_path}")
    return str(json_path)


@asset(
    group_name="hf_enrichment",
    ins={"models_json_path": AssetIn("hf_raw_models")},
)
def hf_identified_keywords(models_json_path: str) -> Set[str]:
    """
    Identify keywords/tags from raw HF models.
    
    Args:
        models_json_path: Path to the raw models JSON
        
    Returns:
        Set of unique keywords
    """
    enrichment = HFEnrichment()
    models_df = enrichment._load_models_dataframe(models_json_path)
    
    keywords = enrichment.identifiers["keywords"].identify(models_df)
    logger.info(f"Identified {len(keywords)} unique keywords")
    
    return keywords


@asset(
    group_name="hf_enrichment",
    ins={"keywords": AssetIn("hf_identified_keywords")},
)
def hf_enriched_keywords(keywords: Set[str]) -> str:
    """
    Extract metadata for identified keywords.
    
    Args:
        keywords: Set of keywords to extract
        
    Returns:
        Path to the saved keywords JSON file
    """
    extractor = HFExtractor()
    
    if not keywords:
        logger.info("No keywords to extract")
        return ""
    
    logger.info(f"Extracting {len(keywords)} keywords")
    _, json_path = extractor.extract_keywords(keywords=list(keywords))
    
    logger.info(f"Keywords saved to {json_path}")
    return str(json_path)


@asset(
    group_name="hf_enrichment",
    ins={"models_json_path": AssetIn("hf_raw_models")},
)
def hf_identified_licenses(models_json_path: str) -> Set[str]:
    """
    Identify license references from raw HF models.
    
    Args:
        models_json_path: Path to the raw models JSON
        
    Returns:
        Set of unique license IDs
    """
    enrichment = HFEnrichment()
    models_df = enrichment._load_models_dataframe(models_json_path)
    
    licenses = enrichment.identifiers["licenses"].identify(models_df)
    logger.info(f"Identified {len(licenses)} unique licenses")
    
    return licenses


@asset(
    group_name="hf_enrichment",
    ins={"license_ids": AssetIn("hf_identified_licenses")},
)
def hf_enriched_licenses(license_ids: Set[str]) -> str:
    """
    Extract metadata for identified licenses.
    
    Args:
        license_ids: Set of license IDs to extract
        
    Returns:
        Path to the saved licenses JSON file
    """
    extractor = HFExtractor()
    
    if not license_ids:
        logger.info("No licenses to extract")
        return ""
    
    logger.info(f"Extracting {len(license_ids)} licenses")
    _, json_path = extractor.extract_licenses(license_ids=list(license_ids))
    
    logger.info(f"Licenses saved to {json_path}")
    return str(json_path)


