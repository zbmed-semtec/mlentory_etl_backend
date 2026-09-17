"""
Helper utilities for AI4Life extraction and enrichment.

Contains commonly used functions shared across AI4Life extractors, enrichment, and assets.
"""

from __future__ import annotations
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from etl_transformers.common.utils import validate_optional_url


logger = logging.getLogger(__name__)

DOCUMENTATION_FETCH_TIMEOUT = 15


class AI4LifeHelper:
    """
    Helper class containing common utility functions for AI4Life data processing.
    
    This class provides static methods for common operations like loading
    dataframes from JSON files, validating data, and other shared utilities.
    """

    @staticmethod
    def load_models_dataframe(models_json_path: Path | str) -> pd.DataFrame:
        """
        Load models JSON into a DataFrame with robust handling.

        Supports both array JSON (e.g., [ {...}, {...} ]) and JSON Lines (NDJSON).
        Provides clear diagnostics for common issues (missing/empty/invalid file).
        
        Args:
            models_json_path: Path to the JSON file containing model metadata
            
        Returns:
            DataFrame containing the model data
            
        Raises:
            FileNotFoundError: If the file does not exist
            ValueError: If the file is a directory, empty, or invalid JSON format
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
                logger.debug(f"Loaded {len(df)} records from {path} (array JSON)")
                return df
        except ValueError:
            pass

        # Second attempt: JSON Lines via pandas
        try:
            df = pd.read_json(path, orient="records", lines=True)
            if not df.empty or len(df.columns) > 0:
                logger.debug(f"Loaded {len(df)} records from {path} (JSON Lines)")
                return df
        except ValueError:
            pass

        # If both pandas attempts fail, raise clear error
        raise ValueError(
            f"Failed to parse models JSON at {path}. "
            "File must be valid JSON array or JSON Lines format."
        )

    @staticmethod
    def get_model_id_column(df: pd.DataFrame) -> str:
        """
        Determine the model ID column name in a DataFrame.
        
        Args:
            df: DataFrame containing model data
            
        Returns:
            Name of the ID column ('id' or 'modelId')
            
        Raises:
            ValueError: If neither 'id' nor 'modelId' column is found
        """
        if "id" in df.columns:
            return "id"
        elif "modelId" in df.columns:
            return "modelId"
        else:
            raise ValueError("DataFrame must contain either 'id' or 'modelId' column")

    @staticmethod
    def deduplicate_models(df: pd.DataFrame, id_column: str | None = None) -> pd.DataFrame:
        """
        Remove duplicate models from a DataFrame based on model ID.
        
        Args:
            df: DataFrame containing model data
            id_column: Name of the ID column (if None, auto-detected)
            
        Returns:
            DataFrame with duplicates removed
        """
        if id_column is None:
            try:
                id_column = AI4LifeHelper.get_model_id_column(df)
            except ValueError:
                logger.warning("No ID column found, returning DataFrame unchanged")
                return df
        
        if id_column not in df.columns:
            logger.warning(f"Column '{id_column}' not found, returning DataFrame unchanged")
            return df
        
        before_count = len(df)
        df = df.drop_duplicates(subset=[id_column], keep="first")
        after_count = len(df)
        
        if after_count != before_count:
            logger.info(
                f"Removed {before_count - after_count} duplicate models "
                f"(before: {before_count}, after: {after_count})"
            )
        
        return df

    @staticmethod
    def generate_mlentory_entity_hash_id(entity_type: str, entity_id: str, platform: str = "AI4Life") -> str:
        """
        Generate a consistent hash from entity properties.

        Args:
            entity_type (str): The type of entity (e.g., 'Dataset', 'Model', 'Article')
            entity_id (str): The unique identifier for the entity
            platform (str): The platform name (default: 'AI4Life')

        Returns:
            str: A SHA-256 hash of the concatenated properties (mlentory_id)

        Example:
            >>> hash_value = AI4LifeHelper.generate_mlentory_entity_hash_id('Dataset', 'squad')
            >>> print(hash_value)
            '8a1c0c50e3e4f0b8a9d5c9e8b7a6f5d4c3b2a1'
        """
        # Create a sorted dictionary of properties to ensure consistent hashing
        properties = {
            "platform": platform,
            "type": entity_type,
            "id": entity_id
        }

        # Convert to JSON string to ensure consistent serialization
        properties_str = json.dumps(properties, sort_keys=True)

        # Generate SHA-256 hash
        hash_obj = hashlib.sha256(properties_str.encode())
        return "https://w3id.org/mlentory/mlentory_graph/"+hash_obj.hexdigest()

    @staticmethod
    def raw_ai4life_catalog_website_records() -> list[dict[str, object]]:
        """
        Canonical AI4Life hosting ``schema:WebSite`` row(s) for this pipeline.

        Minted with :meth:`generate_mlentory_entity_hash_id` like other AI4Life entities.
        Intended to be written as ``sources.json`` under ``1_raw/ai4life/<run>/`` at extract.
        """
        url = "https://ai4life.eurobioimaging.eu/"
        mlentory_id = AI4LifeHelper.generate_mlentory_entity_hash_id("WebSite", url)
        return [
            {
                "https://schema.org/identifier": [mlentory_id],
                "https://schema.org/name": "AI4Life",
                "https://schema.org/url": url,
            }
        ]

    @staticmethod
    def fetch_documentation_text(url: str, timeout: int = DOCUMENTATION_FETCH_TIMEOUT) -> Optional[str]:
        """Fetch markdown/text documentation from a readme URL."""
        if not url or not isinstance(url, str):
            return None

        cleaned_url = url.strip()
        if not cleaned_url:
            return None

        try:
            response = requests.get(cleaned_url, timeout=timeout)
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            text = response.text
            return text.strip() if text and text.strip() else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch documentation from %s: %s", cleaned_url, exc)
            return None

    @staticmethod
    def resolve_abstract_content(
        raw_model: Dict[str, Any],
        timeout: int = DOCUMENTATION_FETCH_TIMEOUT,
    ) -> Optional[str]:
        """
        Resolve schema:abstract content for an AI4Life model.

        Prefers persisted ``documentation_content`` from extraction; falls back to
        fetching the readme URL when missing (e.g. older raw runs).
        """
        stored = str(raw_model.get("documentation_content", "")).strip()
        if stored:
            return stored

        readme_url = validate_optional_url(raw_model.get("readme_file"))
        if not readme_url:
            return None

        return AI4LifeHelper.fetch_documentation_text(readme_url, timeout=timeout)

    @staticmethod
    def enrich_models_with_documentation(
        models: List[Dict[str, Any]],
        max_workers: int = 4,
        timeout: int = DOCUMENTATION_FETCH_TIMEOUT,
    ) -> None:
        """Fetch readme content and attach it as ``documentation_content`` on each model."""
        if not models:
            return

        def _enrich_one(model: Dict[str, Any]) -> None:
            if not isinstance(model, dict):
                return

            existing = str(model.get("documentation_content", "")).strip()
            if existing:
                return

            readme_url = validate_optional_url(model.get("readme_file"))
            if not readme_url:
                model["documentation_content"] = ""
                return

            content = AI4LifeHelper.fetch_documentation_text(readme_url, timeout=timeout)
            model["documentation_content"] = content or ""

        workers = max(1, min(max_workers, len(models)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            list(executor.map(_enrich_one, models))