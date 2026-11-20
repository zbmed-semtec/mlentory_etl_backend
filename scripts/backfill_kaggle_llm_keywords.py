#!/usr/bin/env python3
"""
Backfill LLM keywords for untagged Kaggle parents and reload Neo4j + ES.

Uses the latest raw/normalized Kaggle run artifacts. Does not re-crawl Kaggle
or run vector backfill.

Usage (inside dagster container):
  python scripts/backfill_kaggle_llm_keywords.py
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_kaggle_llm_keywords")

RAW_ROOT = Path(os.getenv("KAGGLE_RAW_ROOT", "/data/1_raw/kaggle"))
NORM_ROOT = Path(os.getenv("KAGGLE_NORM_ROOT", "/data/2_normalized/kaggle"))
KEYWORDS_PRED = "https://schema.org/keywords"
IDENTIFIER_PRED = "https://schema.org/identifier"
NAME_PRED = "https://schema.org/name"


def _latest_dir(root: Path) -> Path:
    dirs = [p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")]
    if not dirs:
        raise FileNotFoundError(f"No run folders under {root}")
    return max(dirs, key=lambda p: p.stat().st_mtime)


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def _card_text(model: Dict[str, Any]) -> str:
    return str(
        model.get("abstract")
        or model.get("intendedUse")
        or model.get("documentation_content")
        or ""
    ).strip()


def _tag_refs(model: Dict[str, Any]) -> List[str]:
    from etl_extractors.kaggle.entity_identifiers.keyword_identifier import (
        KeywordIdentifier,
    )

    return KeywordIdentifier.extract_from_tags(model.get("keywords", ""))


def _first_mlentory_iri(identifiers: Any) -> Optional[str]:
    if not isinstance(identifiers, list):
        return None
    for value in identifiers:
        text = str(value or "").strip()
        if text.startswith("https://w3id.org/mlentory/mlentory_graph/"):
            return text
    return None


def main() -> int:
    from etl_extractors.kaggle.clients.keywords_client import KaggleKeywordsClient
    from etl_extractors.kaggle.kaggle_helper import KaggleHelper
    from etl_loaders.index_loader import check_elasticsearch_connection, index_models
    from etl_loaders.elasticsearch_store import ElasticsearchConfig
    from etl_loaders.rdf_loader import (
        build_and_persist_defined_terms_rdf,
        build_and_persist_models_rdf,
    )
    from etl_loaders.rdf_store import get_neo4j_store_config_from_env
    from etl_transformers.common.llm_keywords import (
        LLM_KEYWORDS_CONFIDENCE,
        LLM_KEYWORDS_METHOD,
        extract_keywords_with_llm,
    )
    from schemas.schemaorg.defined_term import DefinedTerm
    from pydantic import ValidationError

    raw_run = _latest_dir(RAW_ROOT)
    norm_run = _latest_dir(NORM_ROOT)
    logger.info("Raw run: %s", raw_run)
    logger.info("Normalized run: %s", norm_run)

    models_path = raw_run / "models.json"
    instances_path = raw_run / "instances.json"
    raw_keywords_path = raw_run / "keywords.json"
    llm_out_path = raw_run / "llm_keywords_results.json"

    models = _load_json(models_path)
    instances = _load_json(instances_path)
    raw_keywords = _load_json(raw_keywords_path) if raw_keywords_path.exists() else []
    if not isinstance(models, list) or not isinstance(instances, list):
        raise ValueError("models.json / instances.json must be lists")
    if not isinstance(raw_keywords, list):
        raise ValueError("keywords.json must be a list")

    existing_refs: Set[str] = {
        str(row.get("keywordId") or "").strip()
        for row in raw_keywords
        if isinstance(row, dict) and str(row.get("keywordId") or "").strip()
    }

    texts: Dict[str, str] = {}
    for model in models:
        if not isinstance(model, dict):
            continue
        model_id = str(model.get("modelId") or "").strip()
        if not model_id or _tag_refs(model):
            continue
        text = _card_text(model)
        if text:
            texts[model_id] = text

    logger.info("Untagged parents with card text: %d", len(texts))
    if not texts:
        logger.info("Nothing to do")
        return 0

    llm_keywords = extract_keywords_with_llm(
        texts, existing_refs=existing_refs, log=logger
    )
    _save_json(llm_out_path, llm_keywords)

    filled = {mid: refs for mid, refs in llm_keywords.items() if refs}
    logger.info("Parents receiving LLM keywords: %d", len(filled))
    if not filled:
        logger.info("LLM returned no keywords; aborting load")
        return 0

    # --- raw keyword entities ---
    by_ref = {
        str(row.get("keywordId") or "").strip(): row
        for row in raw_keywords
        if isinstance(row, dict) and str(row.get("keywordId") or "").strip()
    }
    client = KaggleKeywordsClient(
        records_data={"data": [], "timestamp": datetime.utcnow().isoformat()}
    )
    new_refs: Set[str] = set()
    for refs in filled.values():
        new_refs.update(refs)
    synthesized = 0
    for ref in sorted(new_refs):
        if ref in by_ref:
            continue
        row = client.fetch_keyword_metadata(
            ref,
            {
                "ref": ref,
                "name": ref,
                "description": "",
                "fullPath": f"llm > {ref}",
            },
        )
        prior_meta = row.get("extraction_metadata")
        extraction_time = ""
        if isinstance(prior_meta, dict):
            extraction_time = str(prior_meta.get("extraction_time") or "")
        row["extraction_metadata"] = {
            "extraction_method": LLM_KEYWORDS_METHOD,
            "confidence": LLM_KEYWORDS_CONFIDENCE,
            "extraction_time": extraction_time,
            "source_field": "card",
            "notes": "LLM-proposed keyword; not present in Kaggle tag catalog",
        }
        by_ref[ref] = row
        synthesized += 1
    raw_keywords = list(by_ref.values())
    _save_json(raw_keywords_path, raw_keywords)
    logger.info(
        "Raw keywords now %d (+%d synthesized)", len(raw_keywords), synthesized
    )

    # --- normalized keywords.json ---
    norm_keywords_path = norm_run / "keywords.json"
    normalized_keywords = (
        _load_json(norm_keywords_path) if norm_keywords_path.exists() else []
    )
    if not isinstance(normalized_keywords, list):
        normalized_keywords = []
    existing_norm_iris = {
        _first_mlentory_iri(row.get(IDENTIFIER_PRED))
        for row in normalized_keywords
        if isinstance(row, dict)
    }
    existing_norm_iris.discard(None)

    added_norm = 0
    for ref in sorted(new_refs):
        row = by_ref[ref]
        mlentory_id = str(row.get("mlentory_id") or "").strip()
        if not mlentory_id or mlentory_id in existing_norm_iris:
            continue
        category = str(row.get("category") or "").strip()
        payload: Dict[str, Any] = {
            "identifier": [mlentory_id],
            "name": str(row.get("name") or ref).strip() or ref,
            "url": None,
            "term_code": str(row.get("name") or ref).strip() or ref,
            "description": str(row.get("description") or "").strip() or None,
            "extraction_metadata": row.get("extraction_metadata") or {},
        }
        if category:
            payload["in_defined_term_set"] = [category]
        try:
            obj = DefinedTerm(**payload)
            normalized_keywords.append(obj.model_dump(mode="json", by_alias=True))
            existing_norm_iris.add(mlentory_id)
            added_norm += 1
        except ValidationError as exc:
            logger.warning("Skip keyword %s: %s", ref, exc)
    _save_json(norm_keywords_path, normalized_keywords)
    logger.info(
        "Normalized keywords now %d (+%d)", len(normalized_keywords), added_norm
    )

    # --- entity_linking.json ---
    linking_path = norm_run / "entity_linking.json"
    linking = _load_json(linking_path) if linking_path.exists() else {}
    if not isinstance(linking, dict):
        linking = {}
    parents_updated = 0
    for model_id, refs in filled.items():
        iris = [
            KaggleHelper.generate_mlentory_entity_hash_id(
                "Keyword", ref, platform="Kaggle"
            )
            for ref in refs
        ]
        entry = linking.get(model_id) or {
            "keywords": [],
            "licenses": [],
            "frameworks": [],
            "sharedby": [],
            "inLanguage": [],
            "sources": [],
        }
        if entry.get("keywords"):
            # Only fill gaps; do not overwrite curated tags.
            continue
        entry["keywords"] = iris
        linking[model_id] = entry
        parents_updated += 1
    _save_json(linking_path, linking)
    logger.info("Updated entity_linking for %d parents", parents_updated)

    # --- mlmodels.json (variations inherit parent keywords) ---
    parent_to_keyword_iris: Dict[str, List[str]] = {
        model_id: (linking.get(model_id) or {}).get("keywords") or []
        for model_id in filled
    }
    instance_to_parent: Dict[str, str] = {}
    for inst in instances:
        if not isinstance(inst, dict):
            continue
        parent = str(inst.get("modelId") or "").strip()
        iri = str(inst.get("mlentory_id") or "").strip()
        if parent in parent_to_keyword_iris and iri:
            instance_to_parent[iri] = parent

    mlmodels_path = norm_run / "mlmodels.json"
    mlmodels = _load_json(mlmodels_path)
    if not isinstance(mlmodels, list):
        raise ValueError("mlmodels.json must be a list")

    models_updated = 0
    for model in mlmodels:
        if not isinstance(model, dict):
            continue
        model_iri = _first_mlentory_iri(model.get(IDENTIFIER_PRED))
        if not model_iri:
            continue
        parent_id = instance_to_parent.get(model_iri)
        if not parent_id:
            continue
        new_keywords = parent_to_keyword_iris.get(parent_id) or []
        if not new_keywords:
            continue
        current = model.get(KEYWORDS_PRED) or []
        if isinstance(current, list) and current:
            continue
        model[KEYWORDS_PRED] = list(new_keywords)
        models_updated += 1
    _save_json(mlmodels_path, mlmodels)
    logger.info("Updated keywords on %d variation MLModels", models_updated)

    # --- translation_mapping.json ---
    mapping_path = norm_run / "translation_mapping.json"
    translation = _load_json(mapping_path) if mapping_path.exists() else {}
    if not isinstance(translation, dict):
        translation = {}
    for row in normalized_keywords:
        if not isinstance(row, dict):
            continue
        uri = _first_mlentory_iri(row.get(IDENTIFIER_PRED))
        name = str(row.get(NAME_PRED) or "").strip()
        if uri and name:
            translation[uri] = name
    _save_json(mapping_path, translation)
    logger.info("Translation mapping entries: %d", len(translation))

    # --- Neo4j load (keywords + models) ---
    rdf_run = Path(
        os.getenv("KAGGLE_RDF_ROOT", "/data/3_rdf/kaggle")
    ) / norm_run.name
    rdf_run.mkdir(parents=True, exist_ok=True)
    store_cfg = get_neo4j_store_config_from_env(
        batching=True,
        batch_size=5000,
    )

    kw_stats = build_and_persist_defined_terms_rdf(
        json_path=str(norm_keywords_path),
        config=store_cfg,
        output_ttl_path=str(rdf_run / "keywords.ttl"),
        entity_label="keywords",
    )
    logger.info("Neo4j keywords load: %s", kw_stats)

    model_stats = build_and_persist_models_rdf(
        json_path=str(mlmodels_path),
        config=store_cfg,
        output_ttl_path=str(rdf_run / "mlmodels.ttl"),
        batch_size=50,
    )
    logger.info("Neo4j models load: %s", model_stats)

    # --- Elasticsearch (no vectors) ---
    es_status = check_elasticsearch_connection()
    logger.info("Elasticsearch: %s", es_status.get("status") or es_status)
    es_cfg = ElasticsearchConfig.from_env()
    index_name = os.getenv("ELASTIC_KAGGLE_MODELS_INDEX", "kaggle_models")
    es_stats = index_models(
        json_path=str(mlmodels_path),
        translation_mapping_path=str(mapping_path),
        index_name=index_name,
        es_config=es_cfg,
    )
    _save_json(rdf_run / "elasticsearch_report.json", es_stats)
    logger.info("Elasticsearch index: %s", es_stats)

    report = {
        "raw_run": str(raw_run),
        "normalized_run": str(norm_run),
        "parents_candidate": len(texts),
        "parents_filled": len(filled),
        "variations_updated": models_updated,
        "keywords_synthesized": synthesized,
        "neo4j_keywords": kw_stats,
        "neo4j_models": model_stats,
        "elasticsearch": es_stats,
    }
    _save_json(rdf_run / "llm_keywords_backfill_report.json", report)
    logger.info("Backfill complete: %s", report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        logger.exception("Backfill failed")
        raise SystemExit(1)
