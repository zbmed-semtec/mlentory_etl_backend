"""Review decisions for model content safety.

Elasticsearch documents are rebuilt from scratch by the index loader. A
decision stored only on a document would be lost. This file is the record
the loader copies back onto each document.

A missing entry means safe. Only ``safe`` and ``inappropriate`` are stored.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)

SAFE = "safe"
INAPPROPRIATE = "inappropriate"
ALLOWED = {SAFE, INAPPROPRIATE}


def store_path() -> Path:
    """JSON file of model id to contentSafety. Override with CONTENT_SAFETY_STORE."""
    return Path(os.getenv("CONTENT_SAFETY_STORE", "/data/moderation/content_safety.json"))


def load_decisions(path: Optional[Path] = None) -> Dict[str, str]:
    """Return stored decisions. A missing or unreadable file yields none."""
    target = path or store_path()
    if not target.exists():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read content safety decisions from %s: %s", target, exc)
        return {}
    if not isinstance(raw, dict):
        logger.warning("Content safety store %s is not an object", target)
        return {}

    decisions: Dict[str, str] = {}
    for model_id, value in raw.items():
        if value in ALLOWED:
            decisions[str(model_id)] = value
        else:
            logger.warning("Ignoring content safety value %r for %s", value, model_id)
    return decisions


def decision_for(decisions: Dict[str, str], *model_ids: str) -> Optional[str]:
    """First stored decision among the model's identifiers."""
    for model_id in model_ids:
        if not model_id:
            continue
        value = decisions.get(model_id)
        if value in ALLOWED:
            return value
    return None


def record_decision(model_id: str, value: str, path: Optional[Path] = None) -> None:
    """Store or replace one decision. ``safe`` keeps an explicit clear mark."""
    if value not in ALLOWED:
        raise ValueError(f"contentSafety must be one of {sorted(ALLOWED)}")
    if not model_id:
        raise ValueError("model id is required")

    target = path or store_path()
    decisions = load_decisions(target)
    decisions[model_id] = value
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(decisions, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
