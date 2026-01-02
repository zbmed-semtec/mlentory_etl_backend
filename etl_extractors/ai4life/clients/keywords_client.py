from __future__ import annotations
from typing import Optional, List, Dict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from __future__ import annotations
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


class AI4LifeKeywordsClient:
    """
    Client for interacting with HuggingFace datasets (Croissant metadata).
    """

    def __init__(self) -> None:
        self.records_data = records_data