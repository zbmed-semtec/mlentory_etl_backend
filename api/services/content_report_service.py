"""Save a visitor's content report.

A report does not change contentSafety. It records the model, page, and
reason so a person can review it. When a GitLab project is configured, it
also opens an issue there. The token must be a project or group access
token, so GitLab attributes the issue to that bot instead of a person.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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


def _gitlab_settings() -> Optional[Tuple[str, str, str]]:
    """Return URL, project, and token. Issues go to the mlentory project."""
    base = os.getenv("GITLAB_URL", "https://gitlab.zbmed.de").strip().rstrip("/")
    project = os.getenv("GITLAB_REPORTS_PROJECT", "zbmed-semtec/mlentory").strip().strip("/")
    token = os.getenv("GITLAB_REPORTS_TOKEN", "").strip()
    if not token:
        return None
    if not base.startswith(("http://", "https://")):
        raise ValueError("GITLAB_URL must start with http:// or https://")
    if not re.fullmatch(r"\d+|[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", project):
        raise ValueError("GITLAB_REPORTS_PROJECT must be a numeric id or a path like group/project")
    return base, project, token


def _gitlab_request(method: str, url: str, token: str, payload: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "PRIVATE-TOKEN": token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "mlentory-content-reports",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitLab request failed ({exc.code}): {detail}") from exc
    parsed = json.loads(body) if body else {}
    if not isinstance(parsed, dict):
        raise RuntimeError("GitLab response was not an object")
    return parsed


def _is_bot_user(user: Dict[str, Any]) -> bool:
    """Project and group access tokens belong to a bot user, not a person."""
    if user.get("bot") is True:
        return True
    if user.get("bot") is False:
        return False
    username = str(user.get("username") or "")
    return re.fullmatch(r"(?:project|group)_\d+_bot_[0-9a-fA-F]+", username) is not None


def _require_bot_token(base: str, token: str) -> None:
    user = _gitlab_request("GET", f"{base}/api/v4/user", token)
    if _is_bot_user(user):
        return
    raise ValueError(
        "GITLAB_REPORTS_TOKEN must be a project or group access token so the issue is opened by a bot"
    )


def create_gitlab_issue(report: Dict[str, str]) -> Optional[str]:
    """Open a review issue as the configured bot. Skip when GitLab is not configured."""
    settings = _gitlab_settings()
    if settings is None:
        return None
    base, project, token = settings
    _require_bot_token(base, token)

    project_id = urllib.parse.quote(project, safe="")
    created = _gitlab_request(
        "POST",
        f"{base}/api/v4/projects/{project_id}/issues",
        token,
        {
            "title": f"Content report {report['report_id']}",
            "description": (
                f"Model: {report['model_id']}\n\n"
                f"Page: {report['page_url']}\n\n"
                f"Reason:\n\n{report['reason']}\n"
            ),
        },
    )
    issue_url = created.get("web_url")
    return issue_url if isinstance(issue_url, str) else None


def close_gitlab_issue(issue_url: str) -> None:
    """Close the review issue after the report is accepted. A failure is logged only."""
    settings = _gitlab_settings()
    if settings is None:
        return
    base, _project, token = settings
    match = re.fullmatch(r"(https?://[^/]+)/(.+)/-/(?:issues|work_items)/(\d+)/?", issue_url or "")
    if not match or match.group(1) != base:
        return
    project_id = urllib.parse.quote(match.group(2), safe="")
    number = match.group(3)
    try:
        _gitlab_request(
            "PUT",
            f"{base}/api/v4/projects/{project_id}/issues/{number}",
            token,
            {"state_event": "close"},
        )
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
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
    issue_url = create_gitlab_issue(report)
    if issue_url:
        report["gitlab_issue"] = issue_url
        save_report(report, directory)
    return {
        "report_id": report["report_id"],
        "model_id": report["model_id"],
        "status": "received",
        "gitlab_issue": issue_url,
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
    close_gitlab_issue(str(report.get("gitlab_issue") or ""))
    return {
        "report_id": report["report_id"],
        "model_id": decision["model_id"],
        "contentSafety": decision["contentSafety"],
        "status": "accepted",
    }
