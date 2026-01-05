"""
Identifier for different schema properties.
"""

from __future__ import annotations
from typing import Set, Dict, List, Any
import pandas as pd
import logging
from pathlib import Path
from datetime import datetime

from .base import EntityIdentifier
import re
import json

logger = logging.getLogger(__name__)


class CitationIdentifier(EntityIdentifier):
    """
    Identifies chunks that contain property: citation
    
    """

    @property
    def entity_type(self) -> str:
        return "citation"

    def identify(self, chunks_dict: Dict[str, dict]) -> Set[str]:
        # not used for this step, so just return an empty set
        return set()

    def identify_per_model(self, chunks_dict: Dict[str, List[Dict[str, Any]]], output_root: Path) ->  Dict[str, dict | None]:
        """
        Identifies chunks that contain property: citation.

        Returns:
            Dict mapping model_id to identified chunk
        """

        def _has_citation_word(s: str) -> bool:
            return bool(re.search(r"\bcitation\b", s, flags=re.IGNORECASE))

        result = {}  # {model_id: chunk | None}

        for model_id, chunks_list in chunks_dict.items():
            result[model_id] = None

            for chunk in chunks_list:
                phtext = chunk.get("phtext")
                if not phtext or not _has_citation_word(phtext):
                    continue

                # best case: code chunk with citation
                if chunk.get("type") == "code":
                    result[model_id] = chunk
                    break

                # fallback: first non-code citation
                if result[model_id] is None:
                    result[model_id] = chunk

        suffix = "chunks_citation"
        output_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        json_path = output_root / f"{timestamp}_{suffix}.json"

        with json_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        logger.info("Saved %s to %s", suffix, json_path)
        return json_path