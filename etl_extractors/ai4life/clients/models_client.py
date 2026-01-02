from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from etl_extractors.ai4life.ai4life_helper import AI4LifeHelper

logger = logging.getLogger(__name__)


class AI4LifeModelClient:
    """Extractor for fetching raw model metadata from the AI4Life platform."""

    def __init__(self, records_data: Dict[str, Any]):
        # expected: {"data": [...], "timestamp": "..."}
        self.records_data = records_data or {}

    def get_models_metadata(self) -> pd.DataFrame:
        """Filter records by type=model and return a dataframe of normalized metadata."""
        records = self.records_data.get("data", []) or []
        model_records = [r for r in records if isinstance(r, dict) and r.get("type") == "model"]

        models_metadata = [self.fetch_model_metadata(model_record) for model_record in model_records]
        return pd.DataFrame(models_metadata)

    # ---------- helpers for normalization ----------

    @staticmethod
    def _to_str(value: Any) -> str:
        """Convert any value to string; missing/None becomes empty string."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        # keep nested objects representable, still a string
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _first_hit(flat: Dict[str, Any], paths: List[str]) -> Any:
        """Return first non-empty value found in flat for given paths; else None."""
        for p in paths:
            if p in flat:
                v = flat[p]
                if v not in (None, ""):
                    return v
        return None

    @staticmethod
    def _safe_utc_date(ts: Any) -> str:
        """Convert unix timestamp (seconds) to YYYY-MM-DD. Else empty string."""
        if isinstance(ts, (int, float)):
            try:
                return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
            except Exception:
                return ""
        return ""

    def fetch_model_metadata(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch a single model's metadata and normalize all missing values to ''."""
        flat = self._flatten_dict(record or {})
        raw_id = flat.get("id") or record.get("id") or ""
        model_id = str(raw_id).split("/", 1)[-1]  # keep last part

        out: Dict[str, Any] = {}

        # fixed fields
        out["modelId"] = model_id
        out["mlentory_id"] = AI4LifeHelper.generate_mlentory_entity_hash_id(
            "Model", model_id, platform="AI4Life"
        )
        out["extraction_timestamp"] = self._to_str(self.records_data.get("timestamp", ""))
        out["enriched"] = True
        out["entity_type"] = "Model"
        out["platform"] = "AI4Life"

        # url fields
        out["url"] = f"https://bioimage.io/#/artifacts/{model_id}"
        readme_file = self._to_str(flat.get("manifest.documentation") or "")
        out["readme_file"] = (
            f"https://hypha.aicell.io/bioimage-io/artifacts/{model_id}/files/{readme_file}"
            if readme_file
            else ""
        )

        # paths to extract (do NOT store path-lists in output)
        path_map: Dict[str, List[str]] = {
            "modelArchitecture": ["manifest.weights.pytorch_state_dict.architecture.callable"],
            "sharedBy": ["created_by", "manifest.uploader.name", "manifest.uploader.email"],
            "trainedOn": ["manifest.training_data.id"],
            "intendedUse": ["manifest.description"],
            "referencePublication": ["config.zenodo.doi_url"],
            "citation": ["manifest.cite"],
            "maintainer": ["manifest.maintainers"],
            "author": ["manifest.authors"],
            "license": ["manifest.license"],
            "name": ["manifest.name"],
            "keywords": ["manifest.tags", "config.zenodo.keywords"],
            "codeRepository": ["git_repo"],
            "datePublished": ["config.zenodo.metadata.publication_date"],
            "conditionsOfAccess": ["config.zenodo.metadata.access_right"],
            "archivedAt": ["config.zenodo.links.record_html"],
            "releaseNotes": ["config.zenodo.notes"],
        }

        # extract fields
        for key, paths in path_map.items():
            val = self._first_hit(flat, paths)
            out[key] = val if val is not None else ""

        # dates: your record uses unix timestamps for created_at/last_modified
        out["dateCreated"] = self._safe_utc_date(flat.get("created_at"))
        out["dateModified"] = self._safe_utc_date(flat.get("last_modified"))

        # version: take last version if list[dict] available; else empty string
        versions = flat.get("versions")
        if isinstance(versions, list) and versions:
            last = versions[-1]
            if isinstance(last, dict):
                out["version"] = self._to_str(last.get("version", ""))
            else:
                out["version"] = self._to_str(last)
        else:
            out["version"] = ""

        # archivedAt: store both zenodo record_html (if any) and ai4life url, as a JSON string
        archived = []
        if out.get("archivedAt"):
            archived.append(out["archivedAt"])
        if out.get("url"):
            archived.append(out["url"])
        out["archivedAt"] = json.dumps(archived, ensure_ascii=False) if archived else ""

        # sharedBy: if extracted value is a list/dict, string-ify; else string
        out["sharedBy"] = self._to_str(out.get("sharedBy", ""))

        # contributor fields: convert to list[{"name":..., "url":...}] then JSON string
        for field in ["author", "maintainer"]:
            raw = out.get(field, "")
            parsed: List[Any]

            # raw might already be a list/dict in flat. Our extraction put it into out as-is.
            if isinstance(raw, str):
                # if it's already a JSON string from _to_str, try to parse
                try:
                    candidate = json.loads(raw)
                    parsed = candidate if isinstance(candidate, list) else [candidate]
                except Exception:
                    parsed = [raw] if raw else []
            elif isinstance(raw, dict):
                parsed = [raw]
            elif isinstance(raw, list):
                parsed = raw
            else:
                parsed = []

            transformed: List[Dict[str, str]] = []
            for contributor in parsed:
                if isinstance(contributor, str):
                    name = contributor
                    transformed.append({"name": name, "url": ""})
                    continue
                if not isinstance(contributor, dict):
                    continue

                name = self._to_str(contributor.get("name", ""))
                orcid = self._to_str(contributor.get("orcid", ""))
                github_user = self._to_str(contributor.get("github_user", ""))

                url = ""
                if orcid:
                    url = f"https://orcid.org/{orcid}"
                elif github_user:
                    url = f"https://github.com/{github_user}"

                transformed.append({"name": name, "url": url})

            out[field] = json.dumps(transformed, ensure_ascii=False) if transformed else ""

        # finally, enforce: everything missing -> "" (keep booleans as-is if you want)
        for k, v in list(out.items()):
            if v is None:
                out[k] = ""
            # if any remaining lists/dicts slipped through, stringify them
            elif isinstance(v, (list, dict)):
                out[k] = json.dumps(v, ensure_ascii=False)

        return out

    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
        """Flatten nested dict keys using dot notation."""
        items: List[tuple[str, Any]] = []
        for key, value in (d or {}).items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(self._flatten_dict(value, new_key, sep).items())
            else:
                items.append((new_key, value))
        return dict(items)
