from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from etl_extractors.kaggle.kaggle_helper import KaggleHelper

logger = logging.getLogger(__name__)


class KaggleModelClient:
    """Extractor for fetching raw model metadata from the Kaggle platform."""

    def __init__(self, records_data: Dict[str, Any]):
        # expected: {"data": [...], "timestamp": "..."}
        self.records_data = records_data or {}

    def get_models_metadata(self) -> pd.DataFrame:
        """Normalize every fetched model card into a dataframe."""
        records = self.records_data.get("data", []) or []
        model_records = [r for r in records if isinstance(r, dict)]

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
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _first_hit(flat: Dict[str, Any], paths: List[str]) -> Any:
        """Return first non-empty value found in flat for given paths; else None."""
        for p in paths:
            if p in flat:
                v = flat[p]
                if v is not None and v != "" and v != p:
                    return v
        return None
    
    @classmethod
    def _distinct(cls, instances: List[Dict[str, Any]], field: str) -> List[str]:
        """Collect distinct non-empty values of `field` across model instances."""
        values: List[str] = []
        for inst in instances:
            v = cls._to_str(inst.get(field, "")).strip()
            if v and v not in values:
                values.append(v)
        return values
    
    @classmethod
    def _distinct_frameworks(cls, instances: List[Dict[str, Any]]) -> List[str]:
        """
        Distinct framework display names, read from each instance URL.

        The URL's third path segment ("TensorFlow2") is the only consistently
        cased form Kaggle provides; the `framework` field varies by record.
        """
        marker = "/models/"
        names: List[str] = []
        for inst in instances:
            url = cls._to_str(inst.get("url", ""))
            name = ""
            if url and marker in url:
                parts = url.split(marker, 1)[1].strip("/").split("/")
                if len(parts) >= 3:
                    name = parts[2]
            if not name:
                name = cls._to_str(inst.get("framework", "")).strip()
            if name and name not in names:
                names.append(name)
        return names

    @classmethod
    def _join_unique(cls, instances: List[Dict[str, Any]], field: str,
                     sep: str = ", ") -> str:
        """Collect distinct non-empty values of `field` across model instances."""
        values = []
        for inst in instances:
            v = cls._to_str(inst.get(field, "")).strip()
            if v and v not in values:
                values.append(v)
        return sep.join(values)

    @staticmethod
    def _safe_iso_date(ts: Any) -> str:
        """
        Convert a Kaggle timestamp to YYYY-MM-DD.

        Kaggle returns ISO 8601 strings on the models endpoint, but Meta
        Kaggle CSV columns can surface as unix seconds, so handle both.
        """
        if isinstance(ts, (int, float)):
            try:
                return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
            except (OverflowError, OSError, ValueError):
                return ""
        if isinstance(ts, str) and ts:
            cleaned = ts.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(cleaned).strftime("%Y-%m-%d")
            except ValueError:
                return ts[:10] if len(ts) >= 10 else ""
        return ""

    def fetch_model_metadata(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch a single model's metadata and normalize all missing values to ''."""
        flat = self._flatten_dict(record or {})

        # 'ref' is owner/slug and is the stable identifier the crawler keys on.
        raw_ref = flat.get("ref") or record.get("ref") or ""
        model_id = self._to_str(raw_ref)

        out: Dict[str, Any] = {}

        # fixed fields
        out["modelId"] = model_id
        out["mlentory_id"] = KaggleHelper.generate_mlentory_entity_hash_id(
            "Model", model_id, platform="Kaggle"
        )
        out["extraction_timestamp"] = self._to_str(self.records_data.get("timestamp", ""))
        out["enriched"] = True
        out["entity_type"] = "Model"
        out["platform"] = "Kaggle"

        # url fields
        out["url"] = f"https://www.kaggle.com/models/{model_id}" if model_id else ""
        # Kaggle serves the model card as the description field rather than a
        # separate file, so there is no distinct readme URL to point at.
        out["readme_file"] = ""

        # paths to extract (do NOT store path-lists in output)
        #
        # Mapped against a real models/get response. Note two Kaggle quirks:
        #   - several fields carry a "Nullable" suffix (voteCountNullable)
        #   - license/framework/url/version live on INSTANCES, not the model,
        #     because one model has many framework+variation instances
        path_map: Dict[str, List[str]] = {
            "name": ["title", "slug"],
            "intendedUse": ["description", "subtitle"],
            "sharedBy": ["author"],
            "author": ["author"],
            "maintainer": ["author"],
            "keywords": ["tags", "keywords"],
            "citation": ["citation"],
            "referencePublication": ["publicationUrl", "provenanceSources"],
            "codeRepository": ["codeRepository", "repositoryUrl"],
            "downloadCount": ["downloadCountNullable", "downloadCount", "totalDownloads"],
            "voteCount": ["voteCountNullable", "voteCount", "totalVotes"],
        }

        # extract fields
        for key, paths in path_map.items():
            val = self._first_hit(flat, paths)
            if val is None or val == "":
                out[key] = ""
            else:
                out[key] = val

        # ---- instance-derived fields ----
        # A model has many instances (framework x variation). License,
        # framework, training data and version all live there, so collect
        # across instances rather than assuming a single value.
        instances = record.get("instances")
        instances = instances if isinstance(instances, list) else []
        dict_instances = [i for i in instances if isinstance(i, dict)]

        
        out["modelArchitecture"] = self._join_unique(dict_instances, "framework")
        out["modelInstanceType"] = self._join_unique(dict_instances, "modelInstanceType")
        out["num_instances"] = len(dict_instances)

        # trainingData is a list per instance; flatten across all of them
        training = []
        for inst in dict_instances:
            td = inst.get("trainingData")
            if isinstance(td, list):
                training.extend(str(t) for t in td if t)
            elif td:
                training.append(str(td))
        seen_td = list(dict.fromkeys(training))
        out["trainedOn"] = json.dumps(seen_td, ensure_ascii=False) if seen_td else ""

        # version: highest versionNumber across instances
        versions = [i.get("versionNumber") for i in dict_instances
                    if isinstance(i.get("versionNumber"), int)]
        out["version"] = self._to_str(max(versions)) if versions else ""
        
        # license lives on instances, and a model can carry several. Keep the
        # joined string for display, plus a JSON array so downstream consumers
        # (the license identifier) can recover the individual values - license
        # names are not safe to split on a comma.
        out["license"] = self._join_unique(dict_instances, "licenseName")
        distinct_licenses = self._distinct(dict_instances, "licenseName")
        out["licenses"] = (
            json.dumps(distinct_licenses, ensure_ascii=False) if distinct_licenses else ""
        )
        
        # Kaggle reports framework inconsistently across records ("pyTorch",
        # "keras", "MODEL_FRAMEWORK_TENSOR_FLOW_2"), while the instance URL
        # always carries a clean display form. Keep the raw joined value for
        # modelArchitecture, plus a JSON array of the clean names for the
        # framework identifier - framework names are not safe to split on a
        # comma.
        out["modelArchitecture"] = self._join_unique(dict_instances, "framework")
        distinct_frameworks = self._distinct_frameworks(dict_instances)
        out["frameworks"] = (
            json.dumps(distinct_frameworks, ensure_ascii=False)
            if distinct_frameworks else ""
        )
        
        out["modelInstanceType"] = self._join_unique(dict_instances, "modelInstanceType")
        out["num_instances"] = len(dict_instances)

        # release notes: Kaggle has no versionNotes; the per-instance overview
        # is the closest equivalent
        out["releaseNotes"] = self._join_unique(dict_instances, "overview", sep=" | ")

        # instance URLs, useful for provenance and for the enrichment step
        inst_urls = [self._to_str(i.get("url", "")) for i in dict_instances]
        inst_urls = [u for u in inst_urls if u]
        out["instance_urls"] = json.dumps(inst_urls, ensure_ascii=False) if inst_urls else ""

        # storage footprint across all instances
        total_bytes = sum(i.get("totalUncompressedBytes") or 0 for i in dict_instances
                          if isinstance(i.get("totalUncompressedBytes"), (int, float)))
        out["contentSize"] = self._to_str(total_bytes) if total_bytes else ""

        # ---- dates ----
        # The models/get response carries no timestamps. Meta Kaggle's
        # Models.csv does, so the crawler can merge them in; when absent
        # these stay empty rather than being invented.
        out["dateCreated"] = self._safe_iso_date(
            self._first_hit(flat, ["publishTime", "creationDate", "CreationDate"])
        )
        out["dateModified"] = self._safe_iso_date(
            self._first_hit(flat, ["lastUpdateTime", "updateTime", "LastUpdateTime"])
        )
        out["datePublished"] = out["dateCreated"]

        # conditionsOfAccess: isPrivate is a bool; express it as an access label
        is_private = self._first_hit(flat, ["isPrivate"])
        if isinstance(is_private, bool):
            out["conditionsOfAccess"] = "restricted" if is_private else "public"
        else:
            out["conditionsOfAccess"] = ""

        # archivedAt: keep the canonical Kaggle url, as a JSON string
        archived = [out["url"]] if out.get("url") else []
        out["archivedAt"] = json.dumps(archived, ensure_ascii=False) if archived else ""

        # sharedBy: if extracted value is a list/dict, string-ify; else string
        out["sharedBy"] = self._to_str(out.get("sharedBy", ""))

        # contributor fields: convert to list[{"name":..., "url":...}] then JSON string
        for field in ["author", "maintainer"]:
            raw = out.get(field, "")
            parsed: List[Any]

            if isinstance(raw, str):
                try:
                    candidate = json.loads(raw)
                    parsed = candidate if isinstance(candidate, list) else [candidate]
                except (ValueError, TypeError):
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
                    # Owner slug doubles as the Kaggle profile path.
                    owner_slug = model_id.split("/", 1)[0] if model_id else ""
                    url = f"https://www.kaggle.com/{owner_slug}" if owner_slug else ""
                    transformed.append({"name": contributor, "url": url})
                    continue
                if not isinstance(contributor, dict):
                    continue

                name = self._to_str(contributor.get("name", ""))
                slug = self._to_str(contributor.get("slug", ""))
                url = f"https://www.kaggle.com/{slug}" if slug else ""
                transformed.append({"name": name, "url": url})

            out[field] = json.dumps(transformed, ensure_ascii=False) if transformed else ""

        # finally, enforce: everything missing -> ""
        for k, v in list(out.items()):
            if v is None:
                out[k] = ""
            elif isinstance(v, (list, dict)):
                out[k] = json.dumps(v, ensure_ascii=False)

        return out

    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
        """
        Flatten nested dict keys using dot notation.

        Lists of dicts are indexed (``instances.0.framework``) because Kaggle
        nests per-framework variations under a list rather than a dict.
        """
        items: List[tuple[str, Any]] = []
        for key, value in (d or {}).items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(self._flatten_dict(value, new_key, sep).items())
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                items.append((new_key, value))
                for idx, element in enumerate(value):
                    if isinstance(element, dict):
                        items.extend(
                            self._flatten_dict(element, f"{new_key}{sep}{idx}", sep).items()
                        )
            else:
                items.append((new_key, value))
        return dict(items)