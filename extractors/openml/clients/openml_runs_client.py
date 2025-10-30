"""
Client for fetching OpenML run metadata.
"""

from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

import pandas as pd
import openml


logger = logging.getLogger(__name__)


class OpenMLRunsClient:
    """
    Client for interacting with OpenML runs API.
    
    Fetches run metadata including associated dataset, flow, and task information.
    """

    def __init__(self):
        pass

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

    def get_recent_run_ids(
        self, num_instances: int = 10, offset: int = 0
    ) -> List[int]:
        """
        Get a list of recent run IDs.

        Args:
            num_instances: Number of run IDs to fetch
            offset: Number of runs to skip before fetching

        Returns:
            List of run IDs
        """
        logger.info(f"Fetching {num_instances} recent run IDs with offset {offset}")
        try:
            runs = openml.runs.list_runs(
                size=num_instances, offset=offset, output_format="dataframe"
            )
            run_ids = runs["run_id"].tolist()[:num_instances]
            logger.debug(f"Fetched run IDs: {run_ids[:5]}..." if len(run_ids) > 5 else f"Fetched run IDs: {run_ids}")
            return run_ids
        except Exception as e:
            logger.error(f"Error fetching recent run IDs: {str(e)}", exc_info=True)
            raise

    def get_run_metadata(self, run_id: int) -> Optional[Dict]:
        """
        Fetch metadata for a single run.

        Args:
            run_id: The ID of the run

        Returns:
            Dictionary containing run metadata, or None if error occurs
        """
        logger.info(f"Fetching metadata for run_id={run_id}")
        logger.info(type(run_id))
        run_id = int(run_id)
        if run_id == 1:
            raise Exception(f"Run ID {run_id} is not valid")
        try:
            run = openml.runs.get_run(run_id)
            dataset = openml.datasets.get_dataset(run.dataset_id)
            flow = openml.flows.get_flow(run.flow_id)
            task = openml.tasks.get_task(run.task_id)

            # Derived/optional values
            dataset_openml_url = f"https://www.openml.org/d/{run.dataset_id}"
            uploader_url = f"https://www.openml.org/u/{run.uploader}"
            flow_upload_date = None
            try:
                flow_upload_date = (
                    flow.upload_date.isoformat() if getattr(flow, "upload_date", None) else None
                )
            except Exception:
                flow_upload_date = None

            flow_language = getattr(flow, "language", None)
            flow_description = getattr(flow, "description", None)
            flow_tags = list(flow.tags) if getattr(flow, "tags", None) else []

            # Evaluations may not always be present on the run object
            evaluations = getattr(run, "evaluations", None)

            metadata = {
                "run_id": run.run_id,
                # "description": self._wrap_metadata(run.description),
                "uploader": run.uploader,
                "uploader_name": run.uploader_name,
                "uploader_url": uploader_url,
                "task_id": run.task_id,
                "task_type": task.task_type,
                "task_evaluation_measure": task.evaluation_measure,
                "task_estimation_procedure": task.estimation_procedure,
                "flow_id": run.flow_id,
                "flow_name": flow.name,
                "flow_version": flow.version,
                "flow_description": flow_description,
                "flow_upload_date": flow_upload_date,
                "flow_language": flow_language,
                "setup_id": run.setup_id,
                "setup_string": run.setup_string,
                "dataset_id": run.dataset_id,
                "dataset_name": dataset.name,
                "dataset_openml_url": dataset_openml_url,
                "openml_url": f"https://www.openml.org/r/{run_id}",
                "evaluations": evaluations,
                "error_message": run.error_message,
                "tags": list(run.tags) if run.tags else [],
                "flow_tags": flow_tags,
                "keywords": list({*(list(run.tags) if run.tags else []), *flow_tags}),
            }

            logger.info(f"Successfully fetched run metadata for run_id={run_id}")
            return metadata

        except Exception as e:
            logger.error(
                f"Error fetching metadata for run {run_id}: {str(e)}", exc_info=True
            )
            return None

    def get_multiple_runs_metadata(
        self, num_instances: int, offset: int = 0, threads: int = 4
    ) -> pd.DataFrame:
        """
        Fetch metadata for multiple runs using multithreading.

        Args:
            num_instances: Number of runs to fetch
            offset: Number of runs to skip before fetching
            threads: Number of threads for parallel processing

        Returns:
            DataFrame containing metadata for the runs
        """
        logger.info(
            f"Fetching metadata for {num_instances} runs with offset={offset}, threads={threads}"
        )
        run_ids = self.get_recent_run_ids(num_instances, offset)
        run_metadata = []

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {
                executor.submit(self.get_run_metadata, run_id): run_id
                for run_id in run_ids
            }

            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    run_metadata.append(result)

        logger.info(f"Successfully fetched {len(run_metadata)} runs")
        return pd.DataFrame(run_metadata)


