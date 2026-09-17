"""
Infer parameter-count scale labels from Hugging Face model ids.

These are plain string literals per model (similar to ``name``), not shared
catalog entities: no MLentory hash ids, no separate extraction client, and no
entry in the entity identifier registry.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_SCALE_PATTERN = re.compile(r"\b(\d+(\.\d+)?[BM])\b", re.IGNORECASE)


def infer_parameter_count_labels(models_df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """
    Map each full ``modelId`` (``org/name``) to a scale token such as ``7B`` or ``540M``
    when the model name segment matches the usual pattern, else ``None``.
    """
    out: Dict[str, Optional[str]] = {}
    if models_df.empty:
        return out

    for _, row in models_df.iterrows():
        full_model_id = row.get("modelId", "")
        if not full_model_id:
            continue
        name_part = (
            full_model_id.split("/", 1)[1]
            if "/" in str(full_model_id)
            else str(full_model_id)
        )
        match = _SCALE_PATTERN.search(name_part)
        label = match.group(1) if match else None
        out[str(full_model_id)] = label

    logger.info("Inferred parameter-count labels for %d models", len(out))
    return out
