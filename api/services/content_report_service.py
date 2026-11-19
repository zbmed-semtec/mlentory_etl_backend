"""Save a visitor's content report.

A report does not change contentSafety. It records the model, page, and
reason so a person can review it. When a private GitHub repo is configured,
it also opens an issue there.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.services.content_safety_service import (
    _canonical_id,
    apply_content_safety,
    find_model_documents,
)

logger = logging.getLogger(__name__)

MAX_REASON_LENGTH = 2000
MAX_PAGE_URL_LENGTH = 2000


def reports_dir() -> Path:
    """Folder of one JSON file per report. Override with CONTENT_REPORTS_DIR."""
    return Path(os.getenv("CONTENT_REPORTS_DIR", "/data/moderation/reports"))


def _clean_report(page_url: str, reason: str) -> tuple[str, str]:
    cleaned_reason = (reason or "").strip()
    cleaned_url = (page_url or "").strip()
    if not cleaned_reason:
        raise ValueError("A reason is required")
    if len(cleaned_reason) > MAX_REASON_LENGTH:
        raise ValueError("Reason is too long")
    if not cleaned_url.startswith(("http://", "https://")):
        raise ValueError("Page URL must start with http:// or https://")
    if len(cleaned_url) > MAX_PAGE_URL_LENGTH:
        raise ValueError("Page URL is too long")
    return cleaned_url, cleaned_reason


def report_path(report_id: str, directory: Optional[Path] = None) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", report_id or ""):
        raise LookupError(report_id)
    return (directory or reports_dir()) / f"{report_id}.json"


def load_report(report_id: str, directory: Optional[Path] = None) -> Dict[str, Any]:
    target = report_path(report_id, directory)
    if not target.exists():
        raise LookupError(report_id)
    report = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not report.get("model_id"):
        raise LookupError(report_id)
    return report


def save_report(report: Dict[str, str], directory: Optional[Path] = None) -> Path:
    target_dir = directory or reports_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{report['report_id']}.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target


def create_github_issue(report: Dict[str, str]) -> Optional[str]:
    """Open a review issue when both repo and token are set. Otherwise skip."""
    repo = os.getenv("GITHUB_REPORTS_REPO", "").strip()
    token = os.getenv("GITHUB_REPORTS_TOKEN", "").strip()
    if not repo or not token:
        return None
    if repo.count("/") != 1:
        raise ValueError("GITHUB_REPORTS_REPO must look like owner/repo")

    payload = json.dumps(
        {
            "title": f"Content report {report['report_id']}",
            "body": (
                f"Model: {report['model_id']}\n"
                f"Page: {report['page_url']}\n\n"
                f"Reason:\n{report['reason']}\n"
            ),
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "mlentory-content-reports",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            created = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub issue was not created ({exc.code}): {detail}") from exc
    return created.get("html_url")


def close_github_issue(issue_url: str) -> None:
    """Close the review issue after the report is accepted. A failure is logged only."""
    match = re.fullmatch(r"https://github.com/([^/]+/[^/]+)/issues/(\d+)", issue_url or "")
    token = os.getenv("GITHUB_REPORTS_TOKEN", "").strip()
    if not match or not token:
        return
    repo, number = match.group(1), match.group(2)
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues/{number}",
        data=json.dumps({"state": "closed"}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "mlentory-content-reports",
        },
        method="PATCH",
    )
    try:
        with urllib.request.urlopen(request, timeout=15):
            return
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("Could not close content report issue %s: %s", issue_url, exc)


def submit_content_report(
    client: Any,
    indices: List[str],
    model_id: str,
    page_url: str,
    reason: str,
    directory: Optional[Path] = None,
) -> Dict[str, Optional[str]]:
    """Record one report. The model's safe or inappropriate mark stays unchanged."""
    cleaned_url, cleaned_reason = _clean_report(page_url, reason)
    hits = find_model_documents(client, indices, model_id)
    if not hits:
        raise LookupError(model_id)

    report = {
        "report_id": uuid.uuid4().hex,
        "model_id": _canonical_id(hits[0], model_id),
        "page_url": cleaned_url,
        "reason": cleaned_reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    save_report(report, directory)
    issue_url = create_github_issue(report)
    if issue_url:
        report["github_issue"] = issue_url
        save_report(report, directory)
    return {
        "report_id": report["report_id"],
        "model_id": report["model_id"],
        "status": "received",
        "github_issue": issue_url,
    }


def accept_content_report(
    client: Any,
    indices: List[str],
    report_id: str,
    directory: Optional[Path] = None,
    store_path: Optional[Path] = None,
) -> Dict[str, str]:
    """Hide the reported model. The report itself does not do this."""
    report = load_report(report_id, directory)
    decision = apply_content_safety(
        client,
        indices,
        report["model_id"],
        "inappropriate",
        store_path,
    )
    report["status"] = "accepted"
    report["contentSafety"] = decision["contentSafety"]
    report["accepted_at"] = datetime.now(timezone.utc).isoformat()
    save_report(report, directory)
    close_github_issue(str(report.get("github_issue") or ""))
    return {
        "report_id": report["report_id"],
        "model_id": decision["model_id"],
        "contentSafety": decision["contentSafety"],
        "status": "accepted",
    }
