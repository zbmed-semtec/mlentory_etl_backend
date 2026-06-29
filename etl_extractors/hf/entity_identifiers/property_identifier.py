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

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        return super().identify(models_df)
    
    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, Any]:
        return super().identify_per_model(models_df)

    def identify_from_chunks(self, chunks_dict: Dict[str, List[Dict[str, Any]]], output_root: Path) ->  Path:
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


class ModelSizeIdentifier(EntityIdentifier):
    """
    Identifies modelsize from huggingface model card tags
    
    """

    @property
    def entity_type(self) -> str:
        return "modelsize"

    def identify(self, models_df: pd.DataFrame) -> Set[str]:
        # not used for this step, so just return an empty set
        return set()

    def identify_per_model(self, models_df: pd.DataFrame) -> Dict[str, Dict[str, str | None] | None]:
        """
        Identifies model size from huggingface model card ID.
        Standardized to always return a dictionary of counts.
        """
        def format_params(param_count: int) -> str:
            """Formats parameter count into human-readable string with suffixes."""
            units = {
                1_000_000_000_000: "T",
                1_000_000_000: "B",
                1_000_000: "M",
                1_000: "K"
            }

            for threshold, suffix in units.items():
                if param_count >= threshold:
                    value = round(param_count / threshold, 2)
                    return f"{value:g}{suffix}"
            
            return str(param_count)
        
        model_sizes: Dict[str, Dict[str, str | None] | None] = {}

        if models_df.empty:
            return model_sizes

        for _, row in models_df.iterrows():
            logger.info(f"Processing model row: {row}")
            full_id = row.get("modelId", "")
            if not full_id:
                continue

            model_st = row.get("safetensors", {})
            
            # if safetensors metadata exists
            if model_st:
                params = model_st.get("parameters", {})
                if params:
                    # individual parameter counts available (fp32, fp16, etc.)
                    model_sizes[full_id] = {k: format_params(v) for k, v in params.items()}
                else:
                    # only total parameter count available
                    total_size = model_st.get("total", 0)
                    model_sizes[full_id] = {"total": format_params(total_size) if total_size > 0 else None}
            
            # fallback to regex parsing of model ID
            else:
                short_name = full_id.split("/")[-1]
                regex = r"(\d+(\.\d+)?[BM])"
                match = re.search(regex, short_name, re.IGNORECASE)
                
                if match:
                    model_sizes[full_id] = {"total": match.group(1).upper()}
                else:
                    model_sizes[full_id] = None

        logger.info("Identified sizes for %d models", len(model_sizes))
        return model_sizes