from __future__ import annotations
from etl_extractors.ai4life.clients.models_client import AI4LifeModelClient
from etl_extractors.ai4life.clients.datasets_client import AI4LifeDatasetsClient

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging

import requests


logger = logging.getLogger(__name__)


class AI4LifeExtractor:
    """Extractor for fetching raw model metadata from the AI4Life platform."""

    def __init__(self, records_data = None, 
                 models_client: Optional[AI4LifeModelClient] = None,
                 datasets_client: Optional[AI4LifeDatasetsClient] = None) -> None:
        self.models_client = models_client or AI4LifeModelClient(records_data)
        self.datasets_client = datasets_client or AI4LifeDatasetsClient(records_data)
        
    def fetch_records(self, num_models:int, base_url:str, parent_id:str) -> Dict[str, Any]:
        """Fetch records from AI4Life API and set extraction timestamp."""
        try:
            response = requests.get(
                f"{base_url}/public/services/artifact-manager/list",
                params={"parent_id": parent_id, "limit": num_models},
                timeout=15,
            )
            extraction_timestamp = datetime.utcnow().isoformat()
            response.raise_for_status()
            return response.json(),extraction_timestamp
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to fetch AI4Life records: {exc}") from exc
        
    def extract_models(self):
        df = self.models_client.get_models_metadata()
        return df
    
    def extract_specific_datasets(self, dataset_names):
        df = self.datasets_client.get_datasets_metadata(dataset_names)

 
      
    
    
    


