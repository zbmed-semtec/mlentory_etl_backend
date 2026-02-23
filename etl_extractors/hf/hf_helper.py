"""
Helper utilities for HuggingFace extraction and enrichment.

Contains commonly used functions shared across HF extractors, enrichment, and assets.
"""

from __future__ import annotations
from pathlib import Path
import logging

import pandas as pd

logger = logging.getLogger(__name__)


class HFHelper:
    """
    Helper class containing common utility functions for HF data processing.
    
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
                id_column = HFHelper.get_model_id_column(df)
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