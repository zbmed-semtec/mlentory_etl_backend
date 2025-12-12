"""
Pure OpenML → FAIR4ML mapping helpers.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from etl.utils import generate_mlentory_entity_hash_id
from schemas.croissant import CroissantDataset
from schemas.fair4ml import MLModel
from schemas.schemaorg import DefinedTerm


logger = logging.getLogger(__name__)


def hash_uri(entity_type: str, entity_id: Any) -> str:
    return generate_mlentory_entity_hash_id(
        entity_type=entity_type,
        entity_id=str(entity_id),
        platform="OpenML",
    )


def make_identifier(url: Optional[str], entity_type: str, entity_id: Any) -> List[str]:
    ids: List[str] = []
    if url:
        ids.append(url)
    ids.append(hash_uri(entity_type, entity_id))
    return ids


def split_keywords(values: List[str]) -> List[str]:
    keywords: List[str] = []
    for val in values or []:
        if not val:
            continue
        parts = [p.strip() for p in str(val).split(",") if p.strip()]
        for p in parts:
            if p and p not in keywords:
                keywords.append(p)
    return keywords


def collect_keyword_map(runs: List[Dict[str, Any]], flows: List[Dict[str, Any]]) -> Dict[str, str]:
    keyword_strings: List[str] = []
    for run in runs:
        keyword_strings.extend(run.get("tags") or [])
        keyword_strings.extend(run.get("flow_tags") or [])
        keyword_strings.extend(run.get("keywords") or [])
    for flow in flows:
        keyword_strings.extend(flow.get("tags") or [])
    keywords = split_keywords(keyword_strings)
    return {kw: hash_uri("Keyword", kw) for kw in keywords}


def normalize_dataset_record(record: Dict[str, Any]) -> Dict[str, Any]:
    dataset_id = record.get("dataset_id")
    openml_url = record.get("openml_url") or f"https://www.openml.org/d/{dataset_id}"
    identifiers = make_identifier(openml_url, "Dataset", dataset_id)

    payload = {
        "identifier": identifiers,
        "name": record.get("name", f"dataset-{dataset_id}"),
        "url": openml_url,
        "sameAs": [openml_url],
        "description": record.get("description"),
        "license": None,
        "conformsTo": "http://mlcommons.org/croissant/1.0",
        "citeAs": None,
        "keywords": [],
        "creator": None,
        "datePublished": None,
        "dateModified": None,
        "extraction_metadata": {
            "source": "OpenML_dataset",
            "dataset_id": dataset_id,
            "status": record.get("status"),
            "likes": record.get("likes"),
            "downloads": record.get("downloads"),
        },
    }
    return CroissantDataset(**payload).model_dump(mode="json", by_alias=True)


def normalize_task_record(record: Dict[str, Any]) -> Dict[str, Any]:
    task_id = record.get("task_id")
    task_url = record.get("url") or f"https://www.openml.org/t/{task_id}"
    identifiers = make_identifier(task_url, "Task", task_id)

    description_parts = []
    if record.get("evaluation_measure"):
        description_parts.append(f"evaluation_measure: {record['evaluation_measure']}")
    if record.get("estimation_procedure"):
        description_parts.append(f"estimation: {record['estimation_procedure']}")
    description = "; ".join(description_parts) if description_parts else None

    payload = {
        "identifier": identifiers,
        "name": record.get("task_type") or f"task-{task_id}",
        "url": task_url,
        "sameAs": [task_url],
        "termCode": str(task_id) if task_id is not None else None,
        "inDefinedTermSet": ["https://www.openml.org/tasks"],
        "description": description,
        "alternateName": [],
        "extraction_metadata": {"source": "OpenML_task", "task_id": task_id},
    }
    return DefinedTerm(**payload).model_dump(mode="json", by_alias=True)


def build_keyword_terms(keyword_map: Dict[str, str]) -> List[Dict[str, Any]]:
    terms: List[Dict[str, Any]] = []
    for kw, uri in keyword_map.items():
        payload = {
            "identifier": [uri],
            "name": kw,
            "url": None,
            "sameAs": [],
            "termCode": kw,
            "inDefinedTermSet": ["https://www.openml.org/keywords"],
            "description": None,
            "alternateName": [],
            "extraction_metadata": {"source": "OpenML_keywords"},
        }
        try:
            terms.append(DefinedTerm(**payload).model_dump(mode="json", by_alias=True))
        except Exception as exc:
            logger.warning("Skipping keyword %s due to error %s", kw, exc)
    return terms


def normalize_runs(
    runs: List[Dict[str, Any]],
    dataset_uri_map: Dict[Any, str],
    task_uri_map: Dict[Any, str],
    flow_uri_map: Dict[Any, str],
    keyword_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for run in runs:
        run_id = run.get("run_id")
        run_url = run.get("openml_url") or f"https://www.openml.org/r/{run_id}"
        run_hash = hash_uri("Run", run_id)

        dataset_uri = dataset_uri_map.get(run.get("dataset_id"))
        task_uri = task_uri_map.get(run.get("task_id"))
        flow_uri = flow_uri_map.get(run.get("flow_id"))

        kw_strings = []
        kw_strings.extend(run.get("tags") or [])
        kw_strings.extend(run.get("flow_tags") or [])
        kw_strings.extend(run.get("keywords") or [])
        kw_uris = [_collect_uri(keyword_map, k) for k in split_keywords(kw_strings)]

        normalized.append(
            {
                "identifier": [run_url, run_hash],
                "name": f"openml-run-{run_id}",
                "url": run_url,
                "author": run.get("uploader_name") or str(run.get("uploader")),
                "flow": flow_uri,
                "dataset": dataset_uri,
                "task": task_uri,
                "evaluations": run.get("evaluations") or {},
                "dateUploaded": run.get("upload_time"),
                "datePublished": run.get("upload_time"),
                "keywords": [uri for uri in kw_uris if uri],
                "extraction_metadata": {
                    "source": "OpenML_run",
                    "run_id": run_id,
                    "flow_id": run.get("flow_id"),
                    "dataset_id": run.get("dataset_id"),
                    "task_id": run.get("task_id"),
                },
            }
        )
    return normalized


def _collect_uri(keyword_map: Dict[str, str], keyword: str) -> Optional[str]:
    if keyword in keyword_map:
        return keyword_map[keyword]
    if keyword:
        return hash_uri("Keyword", keyword)
    return None


def build_entity_links(runs: List[Dict[str, Any]], flow_uri_map: Dict[Any, str]) -> Dict[str, Dict[str, List[str]]]:
    flow_links: Dict[str, Dict[str, List[str]]] = {}
    for flow_uri in flow_uri_map.values():
        flow_links[flow_uri] = {"datasets": [], "tasks": [], "runs": [], "keywords": []}

    for run in runs:
        flow_uri = run.get("flow")
        if not flow_uri or flow_uri not in flow_links:
            continue
        link = flow_links[flow_uri]
        for key, value in [
            ("datasets", run.get("dataset")),
            ("tasks", run.get("task")),
            ("runs", run.get("identifier")[1] if run.get("identifier") else None),
        ]:
            if value and value not in link[key]:
                link[key].append(value)
        for kw in run.get("keywords") or []:
            if kw not in link["keywords"]:
                link["keywords"].append(kw)

    return flow_links


def normalize_models(
    flows: List[Dict[str, Any]],
    runs: List[Dict[str, Any]],
    keyword_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    # Group runs by flow URI
    runs_by_flow: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        flow_uri = run.get("flow")
        if not flow_uri:
            continue
        runs_by_flow.setdefault(flow_uri, []).append(run)

    normalized_models: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for flow in flows:
        flow_id = flow.get("flow_id")
        flow_uri = hash_uri("Flow", flow_id)
        flow_url = flow.get("url") or f"https://www.openml.org/f/{flow_id}"
        flow_runs = runs_by_flow.get(flow_uri, [])

        authors: Set[str] = set()
        datasets_set: Set[str] = set()
        tasks_set: Set[str] = set()
        keyword_strings: List[str] = flow.get("tags") or []

        has_evals: List[str] = []
        for run in flow_runs:
            if run.get("author"):
                authors.add(run["author"])
            if run.get("dataset"):
                datasets_set.add(run["dataset"])
            if run.get("task"):
                tasks_set.add(run["task"])
            for kw in run.get("keywords") or []:
                if kw not in keyword_strings:
                    keyword_strings.append(kw)
            identifiers = run.get("identifier") or []
            run_w3id = identifiers[1] if len(identifiers) > 1 else (identifiers[0] if identifiers else None)
            if run_w3id:
                has_evals.append(run_w3id)

        keyword_uris = []
        for kw in split_keywords(keyword_strings):
            kw_uri = keyword_map.get(kw) or hash_uri("Keyword", kw)
            if kw_uri not in keyword_uris:
                keyword_uris.append(kw_uri)

        payload = {
            "identifier": [flow_url, flow_uri],
            "name": flow.get("name", f"flow-{flow_id}"),
            "url": flow_url,
            "author": list(authors) if authors else flow.get("uploader"),
            "sharedBy": list(authors) if authors else flow.get("uploader"),
            "dateCreated": flow.get("upload_date"),
            "dateModified": flow.get("upload_date"),
            "datePublished": flow.get("upload_date"),
            "description": flow.get("description"),
            "keywords": keyword_uris,
            "inLanguage": [flow.get("language")] if flow.get("language") else [],
            "license": None,
            "referencePublication": [],
            "mlTask": list(tasks_set),
            "modelCategory": [],
            "fineTunedFrom": [],
            "intendedUse": None,
            "usageInstructions": None,
            "codeSampleSnippet": None,
            "modelRisksBiasLimitations": None,
            "ethicalSocial": None,
            "legal": None,
            "trainedOn": list(datasets_set),
            "testedOn": list(datasets_set),
            "validatedOn": list(datasets_set),
            "evaluatedOn": list(datasets_set),
            "evaluationMetrics": [],
            "discussionUrl": None,
            "archivedAt": None,
            "readme": None,
            "issueTracker": None,
            "memoryRequirements": None,
            "hasCO2eEmissions": None,
            "metrics": {},
            "hasEvaluation": has_evals,
            "extraction_metadata": {
                "source": {
                    "extraction_method": "OpenML_flow",
                    "confidence": 1.0,
                    "source_field": "flow_id",
                    "notes": f"OpenML flow {flow_id}",
                }
            },
        }

        try:
            normalized_models.append(MLModel(**payload).model_dump(mode="json", by_alias=True))
        except Exception as exc:
            errors.append({"flow_id": flow_id, "error": str(exc), "payload": payload})

    if errors:
        logger.warning("Model normalization encountered %s errors", len(errors))
    return normalized_models

