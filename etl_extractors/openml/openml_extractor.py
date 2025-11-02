"""
High-level extractor for OpenML metadata.

Coordinates client classes to extract and persist raw artifacts
to the data volume under /data/raw/openml.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional, List
import logging
import os

import pandas as pd

from .clients import (
    OpenMLRunsClient,
    OpenMLDatasetsClient,
)
from .scrapers import OpenMLWebScraper


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class OpenMLExtractor:
    """
    High-level wrapper around OpenML clients to extract raw artifacts
    and persist them to the data volume under /data/raw/openml.
    """

    def __init__(
        self,
        runs_client: Optional[OpenMLRunsClient] = None,
        datasets_client: Optional[OpenMLDatasetsClient] = None,
        enable_scraping: bool = False,
    ) -> None:
        """
        Initialize the OpenML extractor.

        Args:
            runs_client: Client for runs extraction
            datasets_client: Client for datasets extraction
            flows_client: Client for flows extraction
            tasks_client: Client for tasks extraction
            enable_scraping: Whether to enable web scraping for dataset stats
        """
        # Initialize scraper if enabled
        self.scraper = None
        if enable_scraping:
            try:
                self.scraper = OpenMLWebScraper(max_browsers=2, max_retries=3)
                logger.info("Web scraping enabled for dataset stats")
            except Exception as e:
                logger.warning(f"Failed to initialize web scraper: {e}")
                logger.info("Continuing with API-only extraction")

        # Initialize clients
        self.runs_client = runs_client or OpenMLRunsClient()
        self.datasets_client = datasets_client or OpenMLDatasetsClient(
            scraper=self.scraper
        )

    def extract_runs(
        self,
        num_instances: int = 50,
        offset: int = 0,
        threads: int = 4,
        output_root: Path | None = None,
        save_csv: bool = False,
    ) -> tuple[pd.DataFrame, Path]:
        """
        Extract run metadata.

        Args:
            num_instances: Number of runs to extract
            offset: Offset for pagination
            threads: Number of threads for parallel processing
            output_root: Root directory for outputs
            save_csv: Whether to also save as CSV

        Returns:
            Tuple of (DataFrame, json_path)
        """
        df = self.runs_client.get_multiple_runs_metadata(
            num_instances=num_instances, offset=offset, threads=threads
        )
        json_path = self.save_dataframe_to_json(
            df, output_root=output_root, save_csv=save_csv, suffix="openml_runs"
        )
        return df, json_path

    def extract_specific_datasets(
        self,
        dataset_ids: List[int],
        threads: int = 4,
        output_root: Path | None = None,
        save_csv: bool = False,
    ) -> tuple[pd.DataFrame, Path]:
        """
        Extract metadata for specific datasets.

        Args:
            dataset_ids: List of dataset IDs to extract
            threads: Number of threads for parallel processing
            output_root: Root directory for outputs
            save_csv: Whether to also save as CSV

        Returns:
            Tuple of (DataFrame, json_path)
        """
        df = self.datasets_client.get_specific_datasets_metadata(
            dataset_ids=dataset_ids, threads=threads
        )
        json_path = self.save_dataframe_to_json(
            df, output_root=output_root, save_csv=save_csv, suffix="openml_datasets"
        )
        return df, json_path

    # Flows and tasks are not extracted as separate enrichment entities anymore

    def save_dataframe_to_json(
        self,
        df: pd.DataFrame,
        output_root: Path | None = None,
        save_csv: bool = False,
        suffix: str = "openml",
    ) -> Path:
        """
        Save a DataFrame to JSON (and optionally CSV).

        Args:
            df: DataFrame to save
            output_root: Root directory for outputs (defaults to /data)
            save_csv: Whether to also save as CSV
            suffix: Filename suffix

        Returns:
            Path to the saved JSON file
        """
        output_dir = (output_root or Path("/data")).joinpath("raw", "openml")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        json_path = output_dir / f"{timestamp}_{suffix}.json"
        df.to_json(path_or_buf=str(json_path), orient="records", indent=2, date_format="iso")
        
        if save_csv:
            csv_path = output_dir / f"{timestamp}_{suffix}.csv"
            df.to_csv(csv_path, index=False)
        
        logger.info("Saved %s to %s", suffix, json_path)
        return json_path

    def close(self):
        """Clean up resources (e.g., browser pool)"""
        if self.scraper:
            self.scraper.close()

    def __del__(self):
        """Cleanup on object destruction"""
        if hasattr(self, "scraper") and self.scraper:
            try:
                self.scraper.close()
            except:
                pass


