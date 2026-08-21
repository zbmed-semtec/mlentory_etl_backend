"""
Helper utilities for Kaggle extraction and enrichment.

Contains commonly used functions shared across Kaggle extractors, enrichment, and assets.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class KaggleHelper:
    """
    Helper class containing common utility functions for Kaggle data processing.

    This class provides static methods for common operations like loading
    dataframes from JSON files, validating data, and other shared utilities.
    """

    @staticmethod
    def load_models_dataframe(models_json_path: Path | str) -> pd.DataFrame:
        """
        Load models JSON into a DataFrame with robust handling.

        Supports both array JSON (e.g., [ {...}, {...} ]) and JSON Lines (NDJSON).
        Both matter here: the crawler writes NDJSON as its append-only log and
        a deduplicated array as its final output, so either may be handed in.

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

        # NDJSON first when the suffix says so - the crawler's log is large and
        # trying array-parse on it first is wasted work.
        if path.suffix.lower() in (".ndjson", ".jsonl"):
            try:
                df = pd.read_json(path, orient="records", lines=True)
                if not df.empty or len(df.columns) > 0:
                    logger.debug(f"Loaded {len(df)} records from {path} (JSON Lines)")
                    return df
            except ValueError:
                pass

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

        Kaggle's raw records key on ``ref`` (owner/slug); normalized records
        use ``modelId``.

        Args:
            df: DataFrame containing model data

        Returns:
            Name of the ID column ('modelId', 'ref', or 'id')

        Raises:
            ValueError: If no recognized ID column is found
        """
        for candidate in ("modelId", "ref", "id"):
            if candidate in df.columns:
                return candidate
        raise ValueError("DataFrame must contain a 'modelId', 'ref', or 'id' column")

    @staticmethod
    def deduplicate_models(df: pd.DataFrame, id_column: str | None = None) -> pd.DataFrame:
        """
        Remove duplicate models from a DataFrame based on model ID.

        Incremental runs append a fresh record for changed models, so the
        LAST occurrence is the current one - note this keeps "last", unlike
        the AI4Life equivalent which keeps "first".

        Args:
            df: DataFrame containing model data
            id_column: Name of the ID column (if None, auto-detected)

        Returns:
            DataFrame with duplicates removed
        """
        if id_column is None:
            try:
                id_column = KaggleHelper.get_model_id_column(df)
            except ValueError:
                logger.warning("No ID column found, returning DataFrame unchanged")
                return df

        if id_column not in df.columns:
            logger.warning(f"Column '{id_column}' not found, returning DataFrame unchanged")
            return df

        before_count = len(df)
        df = df.drop_duplicates(subset=[id_column], keep="last")
        after_count = len(df)

        if after_count != before_count:
            logger.info(
                f"Removed {before_count - after_count} duplicate models "
                f"(before: {before_count}, after: {after_count})"
            )

        return df

    @staticmethod
    def generate_mlentory_entity_hash_id(entity_type: str, entity_id: str, platform: str = "Kaggle") -> str:
        """
        Generate a consistent hash from entity properties.

        Must stay byte-identical to the other platform helpers so entity IDs
        reconcile across the graph - same key order, same separators, same
        w3id prefix. Only the default platform differs.

        Args:
            entity_type (str): The type of entity (e.g., 'Dataset', 'Model', 'Article')
            entity_id (str): The unique identifier for the entity
            platform (str): The platform name (default: 'Kaggle')

        Returns:
            str: A SHA-256 hash of the concatenated properties (mlentory_id)

        Example:
            >>> hash_value = KaggleHelper.generate_mlentory_entity_hash_id('Model', 'google/gemma')
            >>> print(hash_value)
            'https://w3id.org/mlentory/mlentory_graph/...'
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
    def raw_kaggle_catalog_website_records() -> list[dict[str, object]]:
        """
        Canonical Kaggle hosting ``schema:WebSite`` row(s) for this pipeline.

        Minted with :meth:`generate_mlentory_entity_hash_id` like other Kaggle entities.
        Intended to be written as ``sources.json`` under ``1_raw/kaggle/<run>/`` at extract.
        """
        url = "https://www.kaggle.com/models"
        mlentory_id = KaggleHelper.generate_mlentory_entity_hash_id("WebSite", url)
        return [
            {
                "https://schema.org/identifier": [mlentory_id],
                "https://schema.org/name": "Kaggle",
                "https://schema.org/url": url,
            }
        ]

    @staticmethod
    def resolve_abstract_content(raw_model: Dict[str, Any]) -> Optional[str]:
        """
        Resolve schema:abstract content for a Kaggle model.

        Unlike AI4Life, no network call is needed: Kaggle serves the model
        card inline as ``description`` on the models/get response, which the
        crawler has already persisted. Falls back to ``subtitle`` when a
        model has no description.
        """
        for field in ("documentation_content", "description", "intendedUse", "subtitle"):
            value = str(raw_model.get(field, "") or "").strip()
            if value:
                return value
        return None

    @staticmethod
    def attach_documentation(models: List[Dict[str, Any]]) -> None:
        """
        Attach ``documentation_content`` to each model from its inline card.

        Present for parity with the AI4Life helper, but no fetching occurs -
        the content already arrived with the record.
        """
        if not models:
            return
        for model in models:
            if not isinstance(model, dict):
                continue
            if str(model.get("documentation_content", "")).strip():
                continue
            model["documentation_content"] = KaggleHelper.resolve_abstract_content(model) or ""