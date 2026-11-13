"""
One-time reports for ETL runs that finished before run reports existed.

Reads the Elasticsearch and Neo4j load reports already on disk, counts the
indexes as they are now, and writes the same summary.json / report.md files
that later runs write themselves.

Run inside the Dagster container:

    python -m etl_loaders.backfill_etl_run_reports
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from etl_loaders.etl_run_report import _now, collect_ui_gate, write_run_report

logger = logging.getLogger(__name__)

DATA_ROOT = Path("/data")
RDF_ROOT = DATA_ROOT / "3_rdf"

PLATFORMS = (
    {"platform": "kaggle", "index": "kaggle_models"},
    {"platform": "ai4life", "index": "ai4life_models"},
    {"platform": "hf", "index": "hf_models"},
)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for spec in PLATFORMS:
        _backfill_platform(spec["platform"], spec["index"])


def _backfill_platform(platform: str, index_name: str) -> None:
    gate = collect_ui_gate(index_name)
    runs = _load_historical_runs(platform)
    notes = _platform_notes(platform, runs)
    snapshot: Dict[str, Any] = {
        "platform": platform,
        "run_id": f"backfill-{_now()[:10]}",
        "kind": "backfill",
        "reconstructed": True,
        "finished_at": _now(),
        "index": index_name,
        "stored_elasticsearch_now": gate["stored"],
        "visible_in_ui_now": gate["visible"],
        "gate_failures_now": gate["failures"],
        "historical_runs": runs,
        "notes": notes,
    }
    crawl = _kaggle_crawl_cache() if platform == "kaggle" else None
    if crawl:
        snapshot["downloaded"] = crawl.get("fetched")
        snapshot["download_failed"] = crawl.get("failed")
        snapshot["parent_cards_on_disk"] = crawl.get("total_records")
        snapshot["kaggle_crawl"] = crawl
    write_run_report(snapshot)

    for run in runs:
        run_summary: Dict[str, Any] = {
            "platform": platform,
            "run_id": run["run_id"],
            "kind": "historical_index",
            "reconstructed": True,
            "finished_at": run.get("finished_at"),
            "index": run.get("index") or index_name,
            "models_indexed_this_run": run.get("models_indexed"),
            "index_errors": run.get("index_errors"),
            "neo4j_models_processed": run.get("neo4j_models_processed"),
            "notes": [
                "Reconstructed from the Elasticsearch and Neo4j load reports "
                "saved with this run.",
                "The UI-gate counts for the catalog are in the backfill "
                "snapshot, not on this run. They were not recorded when the "
                "run finished.",
            ],
        }
        write_run_report(run_summary)
    logger.info(
        "%s: snapshot plus %d historical run report(s)", platform, len(runs)
    )


def _load_historical_runs(platform: str) -> List[Dict[str, Any]]:
    root = RDF_ROOT / platform
    if not root.exists():
        return []
    runs: List[Dict[str, Any]] = []
    for path in sorted(root.glob("*/elasticsearch_report.json")):
        report = _read_json(path)
        if not isinstance(report, dict):
            continue
        load_report = _read_json(path.parent / "mlmodels_load_report.json")
        finished_at = None
        neo4j_processed = None
        if isinstance(load_report, dict):
            finished_at = load_report.get("timestamp")
            neo4j_processed = load_report.get("models_processed")
        runs.append(
            {
                "run_id": path.parent.name,
                "index": report.get("index"),
                "models_indexed": report.get("models_indexed"),
                "index_errors": report.get("errors"),
                "neo4j_models_processed": neo4j_processed,
                "finished_at": finished_at,
                "input_file": report.get("input_file"),
            }
        )
    return runs


def _platform_notes(platform: str, runs: List[Dict[str, Any]]) -> List[str]:
    notes = [
        "Stored and visible counts include every model in the index, not "
        "only the models from the latest run.",
    ]
    if platform == "hf" and not runs:
        notes.append(
            "No Hugging Face Elasticsearch load report was found under "
            "/data/3_rdf/hf. Raw extraction folders exist under /data/1_raw/hf. "
            "The counts here are the current hf_models index."
        )
    if platform == "kaggle":
        notes.append(
            "Kaggle stores each variation as a model. A parent whose "
            "instances list is empty is not stored. mlTask and keywords are "
            "copied from the parent. The LLM fills them only when the parent "
            "has a description or subtitle, so variations of an empty parent "
            "stay hidden."
        )
    if runs:
        indexed = ", ".join(
            f"{run['run_id']} indexed {run.get('models_indexed')}"
            for run in runs
        )
        notes.append(f"Completed index runs found on disk: {indexed}.")
    return notes


def _kaggle_crawl_cache() -> Optional[Dict[str, Any]]:
    path = DATA_ROOT / "cache" / "kaggle" / "kaggle_model_get_progress.json"
    payload = _read_json(path)
    return payload if isinstance(payload, dict) else None


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Could not parse %s", path)
        return None


if __name__ == "__main__":
    main()
