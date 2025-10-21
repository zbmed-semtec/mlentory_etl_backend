from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import logging

import pandas as pd

from .clients import HFModelsClient, HFDatasetsClient, HFArxivClient, HFLicenseClient, HFKeywordClient


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class HFExtractor:
    """
    High-level wrapper around HFDatasetManager to extract raw artifacts
    and persist them to the data volume under /data/raw/hf.
    """

    def __init__(
        self,
        models_client: Optional[HFModelsClient] = None,
        datasets_client: Optional[HFDatasetsClient] = None,
        arxiv_client: Optional[HFArxivClient] = None,
        license_client: Optional[HFLicenseClient] = None,
        keyword_client: Optional[HFKeywordClient] = None,
    ) -> None:
        self.models_client = models_client or HFModelsClient()
        self.datasets_client = datasets_client or HFDatasetsClient()
        self.arxiv_client = arxiv_client or HFArxivClient()
        self.license_client = license_client or HFLicenseClient()
        self.keyword_client = keyword_client or HFKeywordClient()

    def extract_models(
        self,
        num_models: int = 50,
        update_recent: bool = True,
        threads: int = 4,
        output_root: Path | None = None,
        save_csv: bool = False,
    ) -> (pd.DataFrame, Path):
        df = self.models_client.get_model_metadata_dataset(
            update_recent=update_recent, limit=num_models, threads=threads
        )
        json_path = self.save_dataframe_to_json(df, output_root=output_root, save_csv=save_csv, suffix="hf_models")
        return df, json_path

    def extract_specific_models(
        self,
        model_ids: List[str],
        threads: int = 4,
        save_csv: bool = False,
        output_root: Path | None = None,
    ) -> (pd.DataFrame, Path):
        df = self.models_client.get_specific_models_metadata(model_ids=model_ids, threads=threads)
        json_path = self.save_dataframe_to_json(df, output_root=output_root, save_csv=save_csv, suffix="hf_models_specific")
        return df, json_path

    def extract_specific_datasets(
        self,
        dataset_names: List[str],
        save_csv: bool = False,
        threads: int = 4,
        output_root: Path | None = None,
    ) -> (pd.DataFrame, Path):
        df = self.datasets_client.get_specific_datasets_metadata(dataset_names=dataset_names, threads=threads)
        json_path = self.save_dataframe_to_json(df, output_root=output_root, save_csv=save_csv, suffix="hf_datasets_specific")
        return df, json_path

    def extract_specific_arxiv(
        self,
        arxiv_ids: List[str],
        save_csv: bool = False,
        batch_size: int = 200,
        output_root: Path | None = None,
    ) -> (pd.DataFrame, Path):
        df = self.arxiv_client.get_specific_arxiv_metadata_dataset(arxiv_ids=arxiv_ids, batch_size=batch_size)
        json_path = self.save_dataframe_to_json(df, output_root=output_root, save_csv=save_csv, suffix="arxiv_articles")
        return df, json_path

    def extract_licenses(
        self,
        license_ids: List[str],
        save_csv: bool = False,
        output_root: Path | None = None,
    ) -> (pd.DataFrame, Path):
        df = self.license_client.get_licenses_metadata(license_ids=license_ids)
        json_path = self.save_dataframe_to_json(df, output_root=output_root, save_csv=save_csv, suffix="licenses")
        return df, json_path

    def extract_keywords(
        self,
        keywords: List[str],
        save_csv: bool = False,
        output_root: Path | None = None,
    ) -> (pd.DataFrame, Path):
        df = self.keyword_client.get_keywords_metadata(keywords=keywords)
        json_path = self.save_dataframe_to_json(df, output_root=output_root, save_csv=save_csv, suffix="keywords")
        return df, json_path
    
    def save_dataframe_to_json(self, df: pd.DataFrame, output_root: Path | None = None, save_csv: bool = False, suffix: str = "hf_models") -> Path:
        output_dir = (output_root or Path("/data")).joinpath("raw", "hf")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        json_path = output_dir / f"{timestamp}_{suffix}.json"
        df.to_json(path_or_buf=str(json_path), orient="records", indent=2, date_format="iso")
        if save_csv:
            csv_path = output_dir / f"{timestamp}_{suffix}.csv"
            df.to_csv(csv_path, index=False)
        logger.info("Saved %s to %s", suffix, json_path)
        return json_path

