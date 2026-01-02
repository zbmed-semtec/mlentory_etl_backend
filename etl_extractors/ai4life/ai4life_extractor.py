from __future__ import annotations
from etl_extractors.ai4life.clients.models_client import AI4LifeModelClient


import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging

import requests


logger = logging.getLogger(__name__)


class AI4LifeExtractor:
    """Extractor for fetching raw model metadata from the AI4Life platform."""

    def __init__(self, models_client: Optional[AI4LifeModelClient] = None, records_data = None) -> None:
        self.models_client = models_client or AI4LifeModelClient(records_data)
        
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

 
      
    
    
    


