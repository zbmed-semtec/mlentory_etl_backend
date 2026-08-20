from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from etl_extractors.kaggle.clients.models_client import KaggleModelClient
from etl_extractors.kaggle.clients.instances_client import KaggleInstancesClient
from etl_extractors.kaggle.clients.licenses_client import KaggleLicenseClient
from etl_extractors.kaggle.clients.keywords_client import KaggleKeywordsClient
from etl_extractors.kaggle.clients.frameworks_client import KaggleFrameworkClient

from etl_extractors.kaggle.kaggle_crawler import KaggleCrawler

logger = logging.getLogger(__name__)


class KaggleExtractor:
    """Extractor for fetching raw model metadata from the Kaggle platform.

    Unlike single-request platforms, Kaggle needs one API call per model
    (~42k of them), so ``fetch_records`` delegates to :class:`KaggleCrawler`,
    which handles parallelism, rate limiting, resume-on-crash, and
    incremental refresh. Everything downstream of that follows the usual
    client-per-entity pattern.
    """

    def __init__(
        self,
        records_data: Optional[Dict[str, Any]] = None,
        crawler: Optional[KaggleCrawler] = None,
        models_client: Optional[KaggleModelClient] = None,
        instances_client: Optional[KaggleInstancesClient] = None,
        licenses_client: Optional[KaggleLicenseClient] = None,
        keywords_client: Optional[KaggleKeywordsClient] = None,
        frameworks_client: Optional[KaggleFrameworkClient] = None,
    ) -> None:
        self.models_client = models_client or KaggleModelClient(records_data)
        self.crawler = crawler
        self.instances_client = instances_client or KaggleInstancesClient(records_data)
        self.licenses_client = licenses_client or KaggleLicenseClient(records_data)
        self.keywords_client = keywords_client or KaggleKeywordsClient(records_data)
        self.frameworks_client = frameworks_client or KaggleFrameworkClient(records_data)

    def fetch_records(
        self,
        output_dir: str,
        num_models: Optional[int] = None,
        incremental: bool = True,
        force_full_refresh: bool = False,
        refresh_metadata: bool = True,
        threads: int = 8,
        max_retries: int = 6,
        request_timeout_seconds: int = 30,
        checkpoint_every: int = 200,
        meta_dataset: str = "kaggle/meta-kaggle",
    ) -> Tuple[Dict[str, Any], str]:
        """Fetch model cards from the Kaggle API and set extraction timestamp.

        Returns ``({"data": [...], "summary": {...}}, timestamp)``. The crawl
        is resumable: an interrupted run re-entered with the same
        ``output_dir`` continues from its last checkpoint.
        """
        try:
            crawler = self.crawler or KaggleCrawler(
                output_dir=output_dir,
                threads=threads,
                max_retries=max_retries,
                request_timeout_seconds=request_timeout_seconds,
                checkpoint_every=checkpoint_every,
                meta_dataset=meta_dataset,
            )
            self.crawler = crawler
            crawler.check_credentials()

            extraction_timestamp = datetime.utcnow().isoformat()

            if incremental and not force_full_refresh:
                summary = crawler.fetch_incremental(
                    refresh_csvs=refresh_metadata, limit=num_models
                )
            else:
                refs = crawler.load_or_build_refs(rebuild=refresh_metadata)
                summary = crawler.fetch_model_cards(refs=refs, limit=num_models)

            records = crawler.load_records()
            payload = {"data": records, "summary": summary}
            return payload, extraction_timestamp
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to fetch Kaggle records: {exc}") from exc

    def extract_models(self) -> pd.DataFrame:
        df = self.models_client.get_models_metadata()
        return df
    
    def extract_specific_instances(self, instance_ids) -> pd.DataFrame:
        df = self.instances_client.get_instances_metadata(instance_ids)
        return df
    
    def extract_specific_licenses(self, license_names) -> pd.DataFrame:
        df = self.licenses_client.get_licenses_metadata(license_names)
        return df
    
    def extract_specific_keywords(self, keywords_names) -> pd.DataFrame:
            df = self.keywords_client.get_keywords_metadata(keywords_names)
            return df
        
    def extract_specific_frameworks(self, frameworks_names) -> pd.DataFrame:
                df = self.frameworks_client.get_frameworks_metadata(frameworks_names)
                return df