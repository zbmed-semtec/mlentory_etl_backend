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


class AI4LifeKeywordClient:
    """
    Client for interacting with AI4Life model keywords/tags.
    """

    def __init__(self,records_data = None) -> None:
        self.records_data = records_data
    import json

    def _flatten_keyword_ids(keyword_ids):
        flat = []
        for k in keyword_ids:
            if isinstance(k, str) and k.strip().startswith("[") and k.strip().endswith("]"):
                try:
                    val = json.loads(k)
                    if isinstance(val, list):
                        flat.extend([str(x) for x in val])
                        continue
                except Exception:
                    pass
            flat.append(k)
        return flat

        
    def get_keywords_metadata(self, keyword_ids: List[str]) -> pd.DataFrame:
        # make unique + deterministic
        keyword_ids = sorted({x for x in keyword_ids if x})

        all_keyword_data: List[Dict[str, Any]] = []

        for keyword_id in keyword_ids:
            keyword_data: Dict[str, Any] = {
                "name": keyword_id,
                "mlentory_id": AI4LifeHelper.generate_mlentory_entity_hash_id("Keyword", keyword_id),
                "entity_type": "Keywords",
                "platform": "AI4Life",
                "enriched": True,
                "extraction_metadata": {
                    "extraction_method": "Hypha API",
                    "confidence": 1.0,
                },
            }
            # ✅ must be inside loop
            all_keyword_data.append(keyword_data)

        return pd.DataFrame(all_keyword_data)