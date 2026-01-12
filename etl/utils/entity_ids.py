"""
Shared helpers for generating MLentory entity identifiers.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def generate_mlentory_entity_hash_id(entity_type: str, entity_id: Any, platform: str | None = None) -> str:
    """
    Generate a consistent SHA-256 based MLentory IRI for an entity.
    """
    properties = {
        "platform": platform or "generic",
        "type": entity_type,
        "id": str(entity_id),
    }
    properties_str = json.dumps(properties, sort_keys=True)
    hash_obj = hashlib.sha256(properties_str.encode())
    return "https://w3id.org/mlentory/mlentory_graph/" + hash_obj.hexdigest()

