"""
Entity enrichment orchestrator for HF models.

Coordinates the identification and extraction of related entities.
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime
import logging

import pandas as pd

from etl_extractors.hf.entity_identifiers.language_identifier import LanguageIdentifier

from .hf_helper import HFHelper
from .entity_identifiers import (
    EntityIdentifier,
    DatasetIdentifier,
    ArticleIdentifier,
    BaseModelIdentifier,
    KeywordIdentifier,
    LicenseIdentifier,
)

from .hf_extractor import HFExtractor


logger = logging.getLogger(__name__)


class HFEnrichment:
    """
    Orchestrates the identification and extraction of related entities for HF models.
    
    Workflow:
    1. Load raw HF models JSON
    2. Identify related entities (datasets, articles, base_models, keywords, licenses)
    3. Download metadata for each entity type
    4. Persist enriched data to /data/raw/hf/<entity_type>/
    """

    def __init__(
        self,
        extractor: Optional[HFExtractor] = None,
    ) -> None:
        self.extractor = extractor or HFExtractor()
        
        # Register entity identifiers
        self.identifiers: Dict[str, EntityIdentifier] = {
            "datasets": DatasetIdentifier(),
            "articles": ArticleIdentifier(),
            "base_models": BaseModelIdentifier(),
            "keywords": KeywordIdentifier(),
            "licenses": LicenseIdentifier(),
            "languages": LanguageIdentifier(),
        }

    def enrich_from_models_json(
        self,
        models_json_path: Path | str,
        *,
        entity_types: List[str] | None = None,
        threads: int = 4,
        output_root: Path | None = None,
    ) -> Dict[str, Path]:
        """
        Complete enrichment workflow: load models, identify entities, extract them.
        
        Args:
            models_json_path: Path to the raw models JSON file
            entity_types: List of entity types to extract, or None for all
            threads: Number of threads for parallel downloads
            output_root: Root directory for output (defaults to /data)
            
        Returns:
            Dict mapping entity type to output file path
        """
        # Load models (robust to array JSON and JSONL)
        models_df = HFHelper.load_models_dataframe(models_json_path)
        logger.info("Loaded %d models from %s", len(models_df), models_json_path)
        
        # Identify related entities
        related_entities = self.identify_related_entities(models_df, entity_types)
        
        # Extract and persist
        output_paths = self.extract_related_entities(
            related_entities, threads=threads, output_root=output_root
        )
        
        return output_paths

    def enrich_with_ancestor_models(
        self,
        current_models_dataframe: pd.DataFrame,
        depth_iterations: int = 1,
        threads: int = 4,
    ) -> pd.DataFrame:
        """
        Iteratively extract base model metadata and merge with current models.
        
        This method identifies base models referenced in current_models_dataframe,
        fetches their metadata, and repeats the process for newly discovered base
        models up to depth_iterations times.
        
        Args:
            current_models_dataframe: DataFrame containing current model metadata
            depth_iterations: Number of iterations to traverse base model references
            threads: Number of threads for parallel downloads
            
        Returns:
            DataFrame containing all models with their ancestors merged
        """
        base_identifier = self.identifiers["base_models"]
        
        max_iterations = max(0, depth_iterations)
        if max_iterations == 0:
            logger.info("depth_iterations set to 0; skipping base model extraction")
            return current_models_dataframe
        
        # Identify initial base models from current dataframe
        initial_base_models = base_identifier.identify(current_models_dataframe)
        logger.info(
            "Identified %d base models from %d current models", 
            len(initial_base_models), 
            len(current_models_dataframe)
        )
        
        if not initial_base_models:
            logger.info("No base models found; returning current models unchanged")
            return current_models_dataframe
        
        # Track which models we've already extracted
        seen_ids: Set[str] = set()
        
        # Add current model IDs to seen set to avoid re-fetching
        try:
            id_column = HFHelper.get_model_id_column(current_models_dataframe)
            seen_ids.update(
                current_models_dataframe[id_column].dropna().astype(str).tolist()
            )
        except ValueError:
            logger.warning("No ID column found in current models dataframe")
        
        pending_ids: Set[str] = set(initial_base_models)
        collected_frames: List[pd.DataFrame] = [current_models_dataframe]
        iterations_run = 0
        
        # Iteratively extract base models
        for iteration in range(max_iterations):
            current_ids = sorted(pending_ids - seen_ids)
            if not current_ids:
                logger.info(
                    "No new base models to extract at iteration %d; stopping early",
                    iteration + 1,
                )
                break
            
            iterations_run = iteration + 1
            logger.info(
                "Base model extraction iteration %d/%d: extracting %d models",
                iterations_run,
                max_iterations,
                len(current_ids),
            )
            
            try:
                df, _ = self.extractor.extract_specific_models(
                    model_ids=current_ids,
                    threads=threads,
                    save_csv=False,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Failed to extract base models on iteration %d: %s",
                    iterations_run,
                    exc,
                    exc_info=True,
                )
                seen_ids.update(current_ids)
                continue
            
            seen_ids.update(current_ids)
            
            if df is None or df.empty:
                logger.info(
                    "Iteration %d returned no base model metadata",
                    iterations_run,
                )
                continue
            
            collected_frames.append(df)
            
            # Identify new base models from the extracted data
            newly_identified = base_identifier.identify(df)
            newly_identified -= seen_ids
            if newly_identified:
                logger.info(
                    "Iteration %d discovered %d additional base models",
                    iterations_run,
                    len(newly_identified),
                )
                pending_ids.update(newly_identified)
            else:
                logger.info(
                    "Iteration %d discovered no new base models",
                    iterations_run,
                )
        
        remaining = pending_ids - seen_ids
        if remaining:
            logger.info(
                "Reached iteration limit (%d) with %d base models still pending",
                max_iterations,
                len(remaining),
            )
        
        # Merge all collected dataframes
        merged_df = pd.concat(collected_frames, ignore_index=True)
        
        # Remove duplicates using helper
        merged_df = HFHelper.deduplicate_models(merged_df)
        
        logger.info(
            "Merged %d total models (original: %d, iterations: %d)",
            len(merged_df),
            len(current_models_dataframe),
            iterations_run,
        )
        
        return merged_df
