"""Hugging Face tasks metadata client backed by the local tasks catalog."""

from __future__ import annotations

from typing import Optional
from pathlib import Path
import logging

import pandas as pd

from etl.utils import generate_mlentory_entity_hash_id
from .keyword_client import HFKeywordClient
from ..entity_identifiers.task_identifier import TaskIdentifier


logger = logging.getLogger(__name__)


class HFTasksClient:
    """Load Hugging Face task metadata and enrich with keyword definitions."""

    def __init__(
        self,
        *,
        catalog_path: Path | str | None = None,
        keyword_client: Optional[HFKeywordClient] = None,
    ) -> None:
        self.catalog_path = Path(catalog_path or TaskIdentifier.DEFAULT_CSV_PATH)
        self.keyword_client = keyword_client or HFKeywordClient()
        self.identifier = TaskIdentifier(tasks_csv_path=self.catalog_path)

    def get_tasks_metadata(self) -> pd.DataFrame:
        """Return the HF tasks catalog augmented with optional definitions."""

        catalog_df = self.identifier.get_tasks_catalog()

        if catalog_df.empty:
            logger.warning("HF tasks catalog is empty; returning placeholder dataframe")
            return pd.DataFrame(
                columns=[
                    "task",
                    "category",
                    "url",
                    "mlentory_id",
                    "entity_type",
                    "platform",
                    "enriched",
                    "extraction_metadata",
                    "definition",
                    "definition_source",
                    "definition_url",
                    "definition_aliases",
                    "definition_wikidata_qid",
                    "definition_enriched",
                    "definition_extraction_metadata",
                ]
            )

        enriched_df = catalog_df.copy()
        enriched_df["url"] = enriched_df["task"].apply(lambda task: f"https://huggingface.co/tasks/{task}")
        enriched_df["mlentory_id"] = enriched_df["task"].apply(
            lambda task: generate_mlentory_entity_hash_id("Task", task, platform="HF")
        )
        enriched_df["entity_type"] = "Task"
        enriched_df["platform"] = "HF"
        enriched_df["enriched"] = True
        enriched_df["extraction_metadata"] = enriched_df["task"].apply(
            lambda _: {
                "extraction_method": "catalog_csv",
                "source": str(self.catalog_path),
            }
        )

        task_names = (
            enriched_df["task"].dropna().astype(str).unique().tolist()
        )
        if task_names:
            definitions_df = self.keyword_client.get_keywords_metadata(task_names)
            definitions_df = self._prepare_definitions(definitions_df)
            if not definitions_df.empty:
                enriched_df = enriched_df.merge(definitions_df, on="task", how="left")

        return enriched_df

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_definitions(definitions_df: pd.DataFrame) -> pd.DataFrame:
        if definitions_df.empty:
            return definitions_df

        rename_map = {
            "keyword": "task",
            "definition": "definition",
            "source": "definition_source",
            "url": "definition_url",
            "aliases": "definition_aliases",
            "wikidata_qid": "definition_wikidata_qid",
            "enriched": "definition_enriched",
            "extraction_metadata": "definition_extraction_metadata",
        }

        available_map = {old: new for old, new in rename_map.items() if old in definitions_df.columns}
        defs_df = definitions_df.rename(columns=available_map)

        keep_columns = [
            "task",
            "definition",
            "definition_source",
            "definition_url",
            "definition_aliases",
            "definition_wikidata_qid",
            "definition_enriched",
            "definition_extraction_metadata",
        ]

        keep_columns = [col for col in keep_columns if col in defs_df.columns]
        if "task" not in keep_columns:
            return pd.DataFrame(columns=keep_columns)

        defs_df = defs_df[keep_columns]
        defs_df = defs_df.drop_duplicates(subset=["task"])
        return defs_df


