"""
Client for fetching OpenML dataset metadata.
"""

from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

import pandas as pd
import openml


logger = logging.getLogger(__name__)


class OpenMLDatasetsClient:
    """
    Client for interacting with OpenML datasets API.
    
    Fetches dataset metadata with optional web scraping for stats
    not available via the API.
    """

    def __init__(self, scraper=None):
        """
        Initialize the datasets client.

        Args:
            scraper: Optional OpenMLWebScraper instance for fetching web stats
        """
        self.scraper = scraper

    def _wrap_metadata(
        self, value, method: str = "openml_python_package"
    ) -> List[Dict]:
        """
        Wrap metadata value in standard format.

        Args:
            value: The metadata value
            method: Extraction method identifier

        Returns:
            List containing metadata dict with extraction info
        """
        return [
            {
                "data": value,
                "extraction_method": method,
                "confidence": 1,
                "extraction_time": datetime.utcnow().isoformat(),
            }
        ]

    def get_recent_dataset_ids(
        self, num_instances: int = 10, offset: int = 0
    ) -> List[int]:
        """
        Get a list of recent dataset IDs.

        Args:
            num_instances: Number of dataset IDs to fetch
            offset: Number of datasets to skip before fetching

        Returns:
            List of dataset IDs
        """
        logger.info(f"Fetching {num_instances} recent dataset IDs with offset {offset}")
        try:
            datasets = openml.datasets.list_datasets(
                size=num_instances, offset=offset, output_format="dataframe"
            )
            dataset_ids = datasets["did"].tolist()[:num_instances]
            logger.debug(f"Fetched dataset IDs: {dataset_ids[:5]}..." if len(dataset_ids) > 5 else f"Fetched dataset IDs: {dataset_ids}")
            return dataset_ids
        except Exception as e:
            logger.error(f"Error fetching recent dataset IDs: {str(e)}", exc_info=True)
            raise

    def get_dataset_metadata(
        self, dataset_id: int, datasets_df: Optional[pd.DataFrame] = None
    ) -> Optional[Dict]:
        """
        Fetch metadata for a single dataset.

        Args:
            dataset_id: The ID of the dataset
            datasets_df: Optional DataFrame with all dataset info for fallback status

        Returns:
            Dictionary containing dataset metadata, or None if error occurs
        """
        logger.info(f"Fetching metadata for dataset_id={dataset_id}")
        try:
            dataset = openml.datasets.get_dataset(dataset_id)

            # Get scraped stats if scraper is available
            scraped_stats = {"status": "N/A", "downloads": 0, "likes": 0, "issues": 0}
            if self.scraper:
                scraped_stats = self.scraper.scrape_dataset_stats(dataset_id)

            # Determine status (prefer scraped, fallback to API)
            api_status = "N/A"
            if datasets_df is not None and dataset_id in datasets_df["did"].values:
                api_status = datasets_df.loc[
                    datasets_df["did"] == dataset_id, "status"
                ].values[0]

            status = (
                scraped_stats["status"]
                if scraped_stats["status"] != "N/A"
                else api_status
            )

            metadata = {
                "dataset_id": self._wrap_metadata(dataset_id),
                "name": self._wrap_metadata(dataset.name),
                "version": self._wrap_metadata(str(dataset.version)),
                "description": self._wrap_metadata(dataset.description),
                "format": self._wrap_metadata(dataset.format),
                # "license": self._wrap_metadata(dataset.license),
                "inLanguage": self._wrap_metadata(dataset.language),
                # "uploader": self._wrap_metadata(dataset.uploader),
                "status": self._wrap_metadata(
                    status,
                    method=(
                        "web_scraping"
                        if scraped_stats["status"] != "N/A"
                        else "openml_python_package"
                    ),
                ),
                "likes": self._wrap_metadata(
                    scraped_stats["likes"], method="web_scraping"
                ),
                "downloads": self._wrap_metadata(
                    scraped_stats["downloads"], method="web_scraping"
                ),
                "url": self._wrap_metadata(dataset.url),
                "openml_url": self._wrap_metadata(
                    f"https://www.openml.org/d/{dataset_id}"
                ),
            }

            logger.debug(
                f"Successfully fetched dataset metadata for dataset_id={dataset_id}"
            )
            return metadata

        except Exception as e:
            logger.error(
                f"Error fetching metadata for dataset {dataset_id}: {str(e)}",
                exc_info=True,
            )
            return None

    def get_specific_datasets_metadata(
        self, dataset_ids: List[int], threads: int = 4
    ) -> pd.DataFrame:
        """
        Fetch metadata for specific datasets using multithreading.

        Args:
            dataset_ids: List of dataset IDs to fetch
            threads: Number of threads for parallel processing

        Returns:
            DataFrame containing metadata for the datasets
        """
        logger.info(
            f"Fetching metadata for {len(dataset_ids)} specific datasets with threads={threads}"
        )

        # Get all datasets info for status fallback
        datasets_df = None
        try:
            datasets_df = openml.datasets.list_datasets(output_format="dataframe")
        except Exception as e:
            logger.warning(f"Could not fetch datasets list for status fallback: {e}")

        dataset_metadata = []

        # Limit threads for scraping to avoid overwhelming the server
        scraping_threads = min(threads, 2) if self.scraper else threads

        with ThreadPoolExecutor(max_workers=scraping_threads) as executor:
            futures = {
                executor.submit(
                    self.get_dataset_metadata, dataset_id, datasets_df
                ): dataset_id
                for dataset_id in dataset_ids
            }

            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    dataset_metadata.append(result)

        logger.info(f"Successfully fetched {len(dataset_metadata)} datasets")
        return pd.DataFrame(dataset_metadata)

    def get_multiple_datasets_metadata(
        self, num_instances: int, offset: int = 0, threads: int = 4
    ) -> pd.DataFrame:
        """
        Fetch metadata for multiple recent datasets using multithreading.

        Args:
            num_instances: Number of datasets to fetch
            offset: Number of datasets to skip before fetching
            threads: Number of threads for parallel processing

        Returns:
            DataFrame containing metadata for the datasets
        """
        logger.info(
            f"Fetching metadata for {num_instances} datasets with offset={offset}, threads={threads}"
        )
        dataset_ids = self.get_recent_dataset_ids(num_instances, offset)
        return self.get_specific_datasets_metadata(dataset_ids, threads)


