from __future__ import annotations
from typing import Optional, List, Dict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from typing import Any, Dict, List, Optional
from datetime import datetime
from etl_extractors.ai4life.ai4life_helper import AI4LifeHelper
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import pandas as pd
import itertools
import requests



from ..ai4life_helper import AI4LifeHelper


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AI4LifeDatasetsClient:
    """
    Client for interacting with HuggingFace datasets (Croissant metadata).
    """

    def __init__(self, records_data) -> None:
        self.records_data = records_data
    
    def get_datasets_metadata(self, dataset_names):
        """get records from AI4Life API and set extraction timestamp."""
         # Filter records by type
        dataset_records = [r for r in self.records_data['data'] if r.get("type") == "dataset"]
        dataset_metadata = [self.get_dataset_metadata(dataset_name) for dataset_name in dataset_names]
        dataset_metadata_df = pd.DataFrame(dataset_metadata)
        return dataset_metadata_df

   
    def get_dataset_metadata(self, dataset_names):
        pass
        