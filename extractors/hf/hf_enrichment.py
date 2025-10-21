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

from .hf_extractor import HFExtractor
from .entity_identifiers import (
    EntityIdentifier,
    DatasetIdentifier,
    ArticleIdentifier,
    BaseModelIdentifier,
    KeywordIdentifier,
    LicenseIdentifier,
)


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
        }

    def identify_related_entities(
        self, models_df: pd.DataFrame, entity_types: List[str] | None = None
    ) -> Dict[str, Set[str]]:
        """
        Identify all related entities from the models DataFrame.
        
        Args:
            models_df: DataFrame containing raw HF model metadata
            entity_types: List of entity types to identify, or None for all
            
        Returns:
            Dict mapping entity type to set of entity IDs
        """
        if entity_types is None:
            entity_types = list(self.identifiers.keys())
        
        related_entities: Dict[str, Set[str]] = {}
        
        for entity_type in entity_types:
            if entity_type in self.identifiers:
                identifier = self.identifiers[entity_type]
                related_entities[entity_type] = identifier.identify(models_df)
            else:
                logger.warning("Unknown entity type '%s', skipping", entity_type)
        
        return related_entities

    def extract_related_entities(
        self,
        related_entities: Dict[str, Set[str]],
        *,
        threads: int = 4,
        output_root: Path | None = None,
    ) -> Dict[str, Path]:
        """
        Download and persist metadata for identified related entities.
        
        Args:
            related_entities: Dict mapping entity type to set of entity IDs
            threads: Number of threads for parallel downloads
            output_root: Root directory for output (defaults to /data)
            
        Returns:
            Dict mapping entity type to output file path
        """
        output_paths: Dict[str, Path] = {}
        output_base = (output_root or Path("/data")).joinpath("raw", "hf")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        for entity_type, entity_ids in related_entities.items():
            if not entity_ids:
                logger.info("No %s to extract", entity_type)
                continue
                
            logger.info("Extracting %d %s", len(entity_ids), entity_type)
            
            try:
                if entity_type == "datasets":
                    _,json_path = self.extractor.extract_specific_datasets(
                        dataset_names=list(entity_ids), threads=threads
                    )
                    output_paths[entity_type] = Path(json_path)
                    continue
                    
                elif entity_type == "articles":
                    _,json_path = self.extractor.extract_specific_arxiv(
                        arxiv_ids=list(entity_ids)
                    )
                    output_paths[entity_type] = Path(json_path)
                    continue
                    
                elif entity_type == "base_models":
                    _,json_path = self.extractor.extract_specific_models(
                        model_ids=list(entity_ids), threads=threads
                    )
                    output_paths[entity_type] = Path(json_path)
                    continue
                    
                elif entity_type == "keywords":
                    _,json_path = self.extractor.extract_keywords(
                        keywords=list(entity_ids)
                    )
                    output_paths[entity_type] = Path(json_path)
                    continue
                    
                elif entity_type == "licenses":
                    _,json_path = self.extractor.extract_licenses(
                        license_ids=list(entity_ids)
                    )
                    output_paths[entity_type] = Path(json_path)
                    continue
                    
                else:
                    logger.warning("No extraction handler for entity type '%s'", entity_type)
                    continue
                
                
            except Exception as e:  # noqa: BLE001
                logger.error("Error extracting %s: %s", entity_type, e, exc_info=True)
        
        return output_paths

    def _load_models_dataframe(self, models_json_path: Path | str) -> pd.DataFrame:
        """
        Load models JSON into a DataFrame with robust handling.

        Supports both array JSON (e.g., [ {...}, {...} ]) and JSON Lines (NDJSON).
        Provides clear diagnostics for common issues (missing/empty/invalid file).
        """
        path = Path(models_json_path)

        if not path.exists():
            raise FileNotFoundError(f"Models JSON not found at: {path}")
        if path.is_dir():
            raise ValueError(f"Expected a file but got a directory: {path}")
        if path.stat().st_size == 0:
            raise ValueError(f"Models JSON is empty: {path}")

        # First attempt: array JSON via pandas
        try:
            df = pd.read_json(path, orient="records")
            if not df.empty or len(df.columns) > 0:
                return df
        except ValueError:
            pass

        # Second attempt: JSON Lines via pandas
        try:
            df = pd.read_json(path, orient="records", lines=True)
            if not df.empty or len(df.columns) > 0:
                return df
        except ValueError:
            pass

        # If both pandas attempts fail, raise clear error
        raise ValueError(
            f"Failed to parse models JSON at {path}. "
            "File must be valid JSON array or JSON Lines format."
        )

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
        models_df = self._load_models_dataframe(models_json_path)
        logger.info("Loaded %d models from %s", len(models_df), models_json_path)
        
        # Identify related entities
        related_entities = self.identify_related_entities(models_df, entity_types)
        
        # Extract and persist
        output_paths = self.extract_related_entities(
            related_entities, threads=threads, output_root=output_root
        )
        
        return output_paths

