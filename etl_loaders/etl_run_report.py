"""
Per-platform ETL run reports.

Each finished indexing run writes a JSON summary and a Markdown explanation
under ``/data/reports/<platform>/<run_id>/`` and appends one line to
``/data/reports/<platform>/runs.jsonl``. The numbers are the record. The
Markdown file is the explanation a person reads later.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Same fields as api.services.faceted_search._minimum_metadata_bool_filter.
UI_GATE_FIELDS = (
    "db_identifier",
    "name",
    "url",
    "shared_by",
    "datecreated",
    "datemodified",
    "description",
    "keywords",
    "license",
    "readme",
    "ml_tasks",
    "source",
)
UI_GATE_NONEMPTY_FIELDS = (
    "name",
    "description",
    "shared_by",
    "license",
    "readme",
    "source",
)
UI_GATE_MISSING_VALUES = ["", "Unknown"]

_GATE_EXPLANATION = (
    "Search shows a stored model only when every required field is present "
    "and the text fields are not empty or the placeholder Unknown. The "
    "required fields are db_identifier, name, url, shared_by, datecreated, "
    "datemodified, description, keywords, license, readme, ml_tasks, and "
    "source. A model can fail more than one field, so the field counts "
    "below add up to more than the number of hidden models."
)


def reports_root() -> Path:
    """Directory that holds run reports. Override with ETL_REPORTS_ROOT."""
    return Path(os.getenv("ETL_REPORTS_ROOT", "/data/reports"))


def write_run_report(summary: Dict[str, Any]) -> Path:
    """
    Write ``summary.json`` and ``report.md`` for one run and refresh its
    line in ``runs.jsonl``.

    Args:
        summary: JSON-serializable report body. Must include ``platform``
            and ``run_id``.

    Returns:
        Path of the run directory.
    """
    platform = str(summary["platform"])
    run_id = str(summary["run_id"])
    run_dir = reports_root() / platform / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    summary_path = run_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (run_dir / "report.md").write_text(render_report(summary), encoding="utf-8")
    _upsert_ledger_line(reports_root() / platform / "runs.jsonl", summary)
    logger.info("Wrote ETL run report %s", run_dir)
    return run_dir


def publish_index_report(
    *,
    platform: str,
    run_id: str,
    index_name: str,
    models_indexed: Optional[int] = None,
    index_errors: Optional[int] = None,
    neo4j_models_processed: Optional[int] = None,
) -> Optional[Path]:
    """
    Write the report for a pipeline indexing step.

    Failures here are logged and swallowed so a report problem does not
    fail a load that already succeeded.
    """
    try:
        gate = collect_ui_gate(index_name)
        summary: Dict[str, Any] = {
            "platform": platform,
            "run_id": run_id,
            "kind": "index",
            "reconstructed": False,
            "finished_at": _now(),
            "index": index_name,
            "models_indexed_this_run": models_indexed,
            "index_errors": index_errors,
            "neo4j_models_processed": neo4j_models_processed,
            "stored_elasticsearch_now": gate["stored"],
            "visible_in_ui_now": gate["visible"],
            "gate_failures_now": gate["failures"],
            "notes": [
                "Visible-in-UI and the gate failures are the whole index "
                "after this load, including models stored by earlier runs.",
                _GATE_EXPLANATION,
            ],
        }
        return write_run_report(summary)
    except Exception:
        logger.exception("ETL run report failed for %s %s", platform, run_id)
        return None


def collect_ui_gate(index_name: str) -> Dict[str, Any]:
    """Count stored documents and how many fail each UI-gate field."""
    from etl_loaders.elasticsearch_store import create_elasticsearch_client

    client = create_elasticsearch_client()
    stored = int(client.count(index=index_name).get("count", 0))
    visible = int(
        client.count(index=index_name, body={"query": _gate_query()}).get("count", 0)
    )
    failures: Dict[str, int] = {}
    for field in UI_GATE_FIELDS:
        missing = int(
            client.count(
                index=index_name,
                body={"query": {"bool": {"must_not": [{"exists": {"field": field}}]}}},
            ).get("count", 0)
        )
        placeholder = 0
        if field in UI_GATE_NONEMPTY_FIELDS:
            placeholder = int(
                client.count(
                    index=index_name,
                    body={"query": {"terms": {field: UI_GATE_MISSING_VALUES}}},
                ).get("count", 0)
            )
        failures[field] = missing + placeholder
    return {"stored": stored, "visible": visible, "failures": failures}


def render_report(summary: Dict[str, Any]) -> str:
    """Turn a summary dict into the Markdown explanation."""
    platform = _platform_title(str(summary.get("platform", "ETL")))
    run_id = summary.get("run_id", "")
    lines: List[str] = [f"# {platform} ETL report", "", f"Run `{run_id}`."]
    if summary.get("finished_at"):
        lines.append(f"Finished at {summary['finished_at']}.")
    if summary.get("reconstructed"):
        lines.extend(
            [
                "",
                "This report was reconstructed after the run had already "
                "finished. Stage durations were not saved.",
            ]
        )
        if summary.get("gate_failures_now"):
            lines.append(
                "The UI-gate counts are the index at reconstruction time, "
                "not the index on the day a run finished."
            )
    lines.extend(["", "## Counts", ""])
    for label, key in (
        ("Indexed in this run", "models_indexed_this_run"),
        ("Index errors in this run", "index_errors"),
        ("Loaded to Neo4j in this run", "neo4j_models_processed"),
        ("Stored in Elasticsearch now", "stored_elasticsearch_now"),
        ("Visible in the UI now", "visible_in_ui_now"),
        ("Downloaded in the latest crawl", "downloaded"),
        ("Download failures in the latest crawl", "download_failed"),
        ("Parent cards on disk", "parent_cards_on_disk"),
    ):
        value = summary.get(key)
        if value is not None:
            lines.append(f"- {label}: {value}")
    index_name = summary.get("index")
    if index_name:
        lines.append(f"- Elasticsearch index: `{index_name}`")

    failures = summary.get("gate_failures_now") or {}
    if failures:
        lines.extend(
            [
                "",
                "## Why stored models stay out of the UI",
                "",
                _GATE_EXPLANATION,
                "",
            ]
        )
        hidden = None
        stored = summary.get("stored_elasticsearch_now")
        visible = summary.get("visible_in_ui_now")
        if isinstance(stored, int) and isinstance(visible, int):
            hidden = stored - visible
            lines.append(f"{hidden} stored models are hidden.")
            lines.append("")
        for field, count in failures.items():
            if count:
                lines.append(f"- `{field}`: {count}")

    notes = [str(note) for note in (summary.get("notes") or []) if str(note).strip()]
    if notes:
        lines.extend(["", "## Notes", ""])
        for note in notes:
            lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _gate_query() -> Dict[str, Any]:
    must = [{"exists": {"field": field}} for field in UI_GATE_FIELDS]
    must_not = [
        {"terms": {field: list(UI_GATE_MISSING_VALUES)}}
        for field in UI_GATE_NONEMPTY_FIELDS
    ]
    return {"bool": {"must": must, "must_not": must_not}}


def _upsert_ledger_line(path: Path, summary: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run_id = str(summary["run_id"])
    kept: List[str] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if str(existing.get("run_id")) == run_id:
                continue
            kept.append(line)
    kept.append(json.dumps(summary, ensure_ascii=False))
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")


def _platform_title(platform: str) -> str:
    return {"hf": "Hugging Face", "ai4life": "AI4Life", "kaggle": "Kaggle"}.get(
        platform, platform
    )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
