from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import pandas as pd

from etl_extractors.kaggle.kaggle_helper import KaggleHelper

logger = logging.getLogger(__name__)


class KaggleInstancesClient:
    """Extractor for model instance metadata from the Kaggle platform.

    A Kaggle model is a container: the downloadable artifacts are its
    *instances*, one per framework and variation. ``Microsoft/phi-3`` has
    three (pyTorch/mini, pyTorch/moe, keras/vision), each with its own
    license, version, size and URL. Flattening them onto the model row would
    lose which framework belongs to which variation, so they are emitted as
    their own entities linked back by ``parent_mlentory_id``.
    """

    def __init__(self, records_data: Dict[str, Any]):
        # expected: {"data": [...], "timestamp": "..."}
        self.records_data = records_data or {}

    def get_instances_metadata(self, instance_ids=None) -> pd.DataFrame:
        """
        Flatten model instances into one row per instance.

        Args:
            instance_ids: Optional iterable of instance ids to keep. When
                omitted, every instance found is returned.
        """
        records = self.records_data.get("data", []) or []
        model_records = [r for r in records if isinstance(r, dict)]

        wanted = set(instance_ids) if instance_ids is not None else None

        instances_metadata: List[Dict[str, Any]] = []
        for model_record in model_records:
            for row in self.fetch_instances_metadata(model_record):
                if wanted is None or row["instanceId"] in wanted:
                    instances_metadata.append(row)

        logger.info(
            "Extracted %d instances from %d models",
            len(instances_metadata), len(model_records),
        )
        return pd.DataFrame(instances_metadata)

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
    def _display_name(variation: str, parent_title: str, framework: str) -> str:
        """
        Catalog label for a variation.

        Always include the parent title and the framework so two runtimes of
        the same slug (PyTorch mini vs TensorFlow2 mini) do not share a name.
        Drop only generic slugs (``default``, ``1``) that Kaggle uses when a
        model has a single unnamed variation. The identifier stays
        ``owner/model/framework/variation``.
        """
        generic = {"default", "", "1"}
        parent = (parent_title or "").strip()
        runtime = (framework or "").strip()
        slug = (variation or "").strip()
        keep_slug = bool(slug) and slug.lower() not in generic

        inner = [part for part in (runtime, slug if keep_slug else "") if part]
        if parent and inner:
            return f"{parent} ({' · '.join(inner)})"
        if parent:
            return parent
        if inner:
            return " · ".join(inner)
        return slug

    @staticmethod
    def _clean_framework(framework: str) -> str:
        """
        Turn Kaggle's framework enum into the form used in instance URLs.

        ``MODEL_FRAMEWORK_TENSOR_FLOW_2`` -> ``TensorFlow2``. Only used when an
        instance has no URL to read the display name from; the URL is
        authoritative whenever it is present.
        """
        if not framework:
            return ""
        name = framework
        if name.startswith("MODEL_FRAMEWORK_"):
            name = name[len("MODEL_FRAMEWORK_"):]
        parts = [p for p in name.split("_") if p]
        return "".join(p.capitalize() for p in parts)

    def fetch_instances_metadata(self, record: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Normalize all instances of a single model, missing values as ''."""
        model_ref = self._to_str((record or {}).get("ref", ""))
        if not model_ref:
            return []

        parent_id = KaggleHelper.generate_mlentory_entity_hash_id(
            "Model", model_ref, platform="Kaggle"
        )
        # Carried onto every instance row so instances are searchable on their
        # parent's model card, not just their own short overview.
        parent_description = self._to_str((record or {}).get("description", ""))
        parent_title = self._to_str((record or {}).get("title", ""))
        # The uploader is declared once on the model. Instances have no owner
        # of their own, so it is carried down: a search for everything an
        # account published should return their variations too.
        parent_shared_by = self._to_str((record or {}).get("author", ""))
        # models/get has no timestamps. Meta Kaggle CreationDate is merged
        # onto the parent record; variations inherit that parent created date.
        # dateModified prefers an API update time, else the same CreationDate.
        parent_created = (
            record.get("publishTime")
            or record.get("CreationDate")
            or record.get("creationDate")
            or record.get("dateCreated")
            or ""
        )
        parent_modified = (
            record.get("lastUpdateTime")
            or record.get("updateTime")
            or record.get("LastUpdateTime")
            or record.get("dateModified")
            or parent_created
        )

        raw_instances = record.get("instances")
        raw_instances = raw_instances if isinstance(raw_instances, list) else []

        out_rows: List[Dict[str, Any]] = []
        for position, instance in enumerate(raw_instances):
            if not isinstance(instance, dict):
                continue

            framework = self._to_str(instance.get("framework", ""))
            variation = self._to_str(instance.get("slug", ""))
            instance_url = self._to_str(instance.get("url", ""))

            # Instance id mirrors the Kaggle URL path so it round-trips:
            # owner/model/framework/variation
            #
            # Derive it from the URL when present rather than from the
            # `framework` field: Kaggle capitalises them differently
            # ("PyTorch" in the URL vs "pyTorch" in the field), and the
            # identifier reads URLs, so both sides must agree.
            marker = "/models/"
            if instance_url and marker in instance_url:
                instance_ref = instance_url.split(marker, 1)[1].strip("/")
            else:
                # No URL: fall back to the enum, cleaned into the display form
                # Kaggle uses in URLs, so ids stay consistent either way.
                instance_ref = "/".join(
                    part for part in
                    (model_ref, self._clean_framework(framework), variation) if part
                )

            # The URL's third segment is the display framework name
            # ("TensorFlow2") as opposed to the enum in the `framework` field.
            ref_parts = instance_ref.split("/")
            framework_display = ref_parts[2] if len(ref_parts) >= 3 else framework

            out: Dict[str, Any] = {}

            # ---- pass through every raw instance field ----
            # Kaggle may add fields at any time, and a curated subset would
            # silently drop them. Raw keys land first so the derived schema
            # fields below win on any name collision.
            for raw_key, raw_value in instance.items():
                if isinstance(raw_value, bool):
                    out[raw_key] = raw_value
                else:
                    out[raw_key] = self._to_str(raw_value)

            # ---- identity ----
            out["instanceId"] = instance_ref
            out["mlentory_id"] = KaggleHelper.generate_mlentory_entity_hash_id(
                "ModelInstance", instance_ref, platform="Kaggle"
            )
            out["parent_mlentory_id"] = parent_id
            out["modelId"] = model_ref
            out["parent_name"] = parent_title
            out["parent_description"] = parent_description
            out["sharedBy"] = parent_shared_by
            out["dateCreated"] = self._to_str(parent_created)
            out["dateModified"] = self._to_str(parent_modified)
            out["extraction_timestamp"] = self._to_str(
                self.records_data.get("timestamp", "")
            )
            out["enriched"] = True
            out["entity_type"] = "ModelInstance"
            out["platform"] = "Kaggle"
            out["position"] = position

            # ---- schema-aligned fields ----
            out["slug"] = variation
            # Parent title plus framework, with the variation slug when it is
            # informative. Generic slugs stay in `slug`, not in `name`.
            out["name"] = self._display_name(variation, parent_title, framework_display)
            out["description"] = self._to_str(instance.get("overview", ""))
            out["modelArchitecture"] = framework
            # Kaggle reports framework as an enum ("MODEL_FRAMEWORK_TENSOR_FLOW_2")
            # but uses a display form in the URL ("TensorFlow2"). Keep both:
            # the enum is faithful to the API, the display form is searchable.
            out["frameworkName"] = framework_display
            out["license"] = self._to_str(instance.get("licenseName", ""))
            out["version"] = self._to_str(instance.get("versionNumber", ""))
            out["url"] = instance_url
            out["usage"] = self._to_str(instance.get("usage", ""))

            # contentSize: bytes, kept numeric-as-string for consistency
            size = instance.get("totalUncompressedBytes")
            out["contentSize"] = self._to_str(size) if isinstance(size, (int, float)) else ""

            # booleans kept as-is; downstream can coerce
            out["fineTunable"] = bool(instance.get("fineTunable", False))
            out["hasBaseModelInstanceInformation"] = bool(
                instance.get("hasBaseModelInstanceInformation", False)
            )

            # trainingData is a list per instance
            training = instance.get("trainingData")
            if isinstance(training, list):
                cleaned = [str(t) for t in training if t]
            elif training:
                cleaned = [str(training)]
            else:
                cleaned = []
            out["trainedOn"] = json.dumps(cleaned, ensure_ascii=False) if cleaned else ""

            # enforce: everything missing -> ""
            for key, value in list(out.items()):
                if value is None:
                    out[key] = ""
                elif isinstance(value, (list, dict)):
                    out[key] = json.dumps(value, ensure_ascii=False)

            out_rows.append(out)

        return out_rows