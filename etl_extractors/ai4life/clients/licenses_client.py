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


class AI4LifeLicenseClient:
    """
    Client for interacting with AI4Life Model license.
    """

    def __init__(self, records_data = None) -> None:
        self.records_data = records_data
        
   

        
    def get_licenses_metadata(self, license_ids: List[str]) -> pd.DataFrame:
        # make unique + deterministic
        license_ids = sorted({x for x in license_ids if x})

        all_license_data: List[Dict[str, Any]] = []

        for license_id in license_ids:
            license_data: Dict[str, Any] = {
                "name": license_id,
                "mlentory_id": AI4LifeHelper.generate_mlentory_entity_hash_id("License", license_id),
                "entity_type": "License",
                "platform": "AI4Life",
                "enriched": True,
                "extraction_metadata": {
                    "extraction_method": "Hypha API",
                    "confidence": 1.0,
                },
            }
            # ✅ must be inside loop
            all_license_data.append(license_data)

        return pd.DataFrame(all_license_data)