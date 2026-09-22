"""
Fetch a Kaggle model README.md (file explorer) without downloading weights.

In MLentory a Kaggle FAIR4ML model is a Kaggle variation (framework + slug).
Its File Explorer often shows a README.md that already combines the parent
Kaggle card and variation-specific notes. That file is not on models/get; it
lives in the variation file list. When it is missing, fall back to parent
card + overview + usage from the API.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

import requests

from etl_extractors.kaggle.kaggle_crawler import KAGGLE_BASE, KaggleCrawler, RETRY_STATUS

logger = logging.getLogger(__name__)


def _text(value: Any) -> str:
    """Stringify a record field, treating None / NaN as empty."""
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


README_BASENAME = re.compile(r"^readme\.md$", re.IGNORECASE)
MAX_README_BYTES = 2 * 1024 * 1024
FILES_PAGE_SIZE = 100
FILES_MAX_PAGES = 3


def compose_model_documentation(
    *,
    parent_card: str = "",
    overview: str = "",
    usage: str = "",
    readme_markdown: str = "",
) -> str:
    """
    Build documentation for a Kaggle FAIR4ML model (a Kaggle variation).

    Prefer the uploaded README.md when present. Otherwise join the parent
    Kaggle card with overview/usage, skipping empty parts and parts already
    contained in the parent card.
    """
    readme = str(readme_markdown or "").strip()
    if readme:
        return readme

    parent = str(parent_card or "").strip()
    overview_text = str(overview or "").strip()
    usage_text = str(usage or "").strip()

    parts: List[str] = []
    if parent:
        parts.append(parent)
    if overview_text and overview_text not in parent:
        parts.append(overview_text)
    if usage_text and usage_text not in parent and usage_text != overview_text:
        parts.append(usage_text)
    return "\n\n".join(parts)


def documentation_source_notes(readme_markdown: str = "") -> Tuple[str, str]:
    """Extraction-method notes for abstract."""
    if str(readme_markdown or "").strip():
        return (
            "README.md",
            "Uploaded README.md from the Kaggle model file list",
        )
    return (
        "model card",
        "No variation README.md; used the parent model card, joined "
        "with variation overview and usage when present",
    )


def attach_description_and_abstract(records: Iterable[Dict[str, Any]]) -> int:
    """
    Set FAIR4ML ``abstract`` on extracted instance records.

    Prefers ``readme_markdown`` when a variation README was fetched; otherwise
    joins parent card + overview + usage. Stores ``overview`` separately so
    the short API overview is not lost. Returns how many records received a
    non-empty abstract.
    """
    filled = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        overview = _text(record.get("overview")) or _text(record.get("description"))
        if not _text(record.get("overview")):
            record["overview"] = overview
        readme = _text(record.get("readme_markdown"))
        docs = compose_model_documentation(
            parent_card=_text(record.get("parent_description")),
            overview=overview,
            usage=_text(record.get("usage")),
            readme_markdown=readme,
        )
        source, notes = documentation_source_notes(readme)
        record["abstract"] = docs
        record["documentation_source"] = source
        record["documentation_notes"] = notes
        if docs:
            filled += 1
    return filled


def _file_name(entry: Dict[str, Any]) -> str:
    return str(entry.get("name") or entry.get("fileName") or "").strip()


def _file_size(entry: Dict[str, Any]) -> int:
    raw = entry.get("size")
    if raw is None:
        raw = entry.get("totalBytes")
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def select_readme_file(
    files: Sequence[Dict[str, Any]],
    *,
    max_bytes: int = MAX_README_BYTES,
) -> Optional[Dict[str, Any]]:
    """
    Pick README.md from a Kaggle model file list.

    Prefers a top-level README.md over nested copies. Skips files larger than
    ``max_bytes`` so a mislabeled weight is not treated as markdown.
    """
    candidates: List[Tuple[int, str, int]] = []
    for entry in files:
        if not isinstance(entry, dict):
            continue
        name = _file_name(entry)
        if not name:
            continue
        basename = name.rsplit("/", 1)[-1]
        if not README_BASENAME.match(basename):
            continue
        size = _file_size(entry)
        if size > max_bytes:
            logger.info("Skipping oversized README %s (%d bytes)", name, size)
            continue
        candidates.append((name.count("/"), name, size))
    if not candidates:
        return None
    candidates.sort()
    _depth, name, size = candidates[0]
    return {"name": name, "size": size}


def split_instance_ref(instance_id: str) -> Optional[Tuple[str, str, str, str]]:
    """Parse ``owner/model/framework/variation`` from a Kaggle model id or URL path."""
    ref = str(instance_id or "").strip().strip("/")
    marker = "/models/"
    if marker in ref:
        ref = ref.split(marker, 1)[1].strip("/")
    parts = [p for p in ref.split("/") if p]
    if len(parts) != 4:
        return None
    return parts[0], parts[1], parts[2], parts[3]


class KaggleModelReadmeFetcher:
    """List a Kaggle model's files and download README.md only."""

    def __init__(
        self,
        crawler: KaggleCrawler,
        *,
        cache_dir: Optional[Path] = None,
        max_bytes: int = MAX_README_BYTES,
        force_refresh: bool = False,
    ) -> None:
        self.crawler = crawler
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_bytes = max_bytes
        self.force_refresh = force_refresh
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def attach_readmes(self, records: Iterable[Dict[str, Any]]) -> int:
        """
        Set ``readme_markdown`` on each model record when a README exists.

        Returns the number of records that received markdown.
        """
        rows = [record for record in records if isinstance(record, dict)]
        if not rows:
            return 0

        def _fill(record: Dict[str, Any]) -> bool:
            instance_id = str(record.get("instanceId") or "").strip()
            version = str(record.get("version") or "1").strip() or "1"
            markdown = self.fetch_readme(instance_id, version)
            record["readme_markdown"] = markdown or ""
            return bool(markdown)

        workers = max(1, int(getattr(self.crawler, "threads", 4) or 4))
        found = 0
        if workers == 1 or len(rows) == 1:
            return sum(1 for record in rows if _fill(record))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_fill, record) for record in rows]
            for index, future in enumerate(as_completed(futures), 1):
                if future.result():
                    found += 1
                if index % 200 == 0 or index == len(futures):
                    logger.info(
                        "Kaggle model README fetch %d/%d (found %d)",
                        index,
                        len(futures),
                        found,
                    )
        return found

    def fetch_readme(self, instance_id: str, version: str) -> Optional[str]:
        parsed = split_instance_ref(instance_id)
        if parsed is None:
            logger.debug("Cannot parse Kaggle model ref %s", instance_id)
            return None

        cached = self._read_cache(instance_id, version)
        if cached is not None:
            return cached or None

        try:
            files = self._list_files(parsed)
            picked = select_readme_file(files, max_bytes=self.max_bytes)
            if picked is None:
                self._write_cache(instance_id, version, "")
                return None
            body = self._download_file(parsed, version, picked["name"])
        except Exception:
            logger.warning(
                "Failed to fetch README for %s@%s", instance_id, version, exc_info=True
            )
            return None

        if body:
            self._write_cache(instance_id, version, body)
        else:
            self._write_cache(instance_id, version, "")
        return body or None

    def _cache_path(self, instance_id: str, version: str) -> Path:
        key = hashlib.sha1(f"{instance_id}@{version}".encode("utf-8")).hexdigest()
        assert self.cache_dir is not None
        return self.cache_dir / f"{key}.md"

    def _read_cache(self, instance_id: str, version: str) -> Optional[str]:
        if self.force_refresh or self.cache_dir is None:
            return None
        path = self._cache_path(instance_id, version)
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        return text

    def _write_cache(self, instance_id: str, version: str, body: str) -> None:
        if self.cache_dir is None:
            return
        self._cache_path(instance_id, version).write_text(body, encoding="utf-8")

    def _list_files(
        self, parsed: Tuple[str, str, str, str]
    ) -> List[Dict[str, Any]]:
        owner, model, framework, variation = parsed
        files: List[Dict[str, Any]] = []
        page_token = ""
        for _ in range(FILES_MAX_PAGES):
            url = (
                f"{KAGGLE_BASE}/models/{quote(owner, safe='')}/"
                f"{quote(model, safe='')}/{quote(framework, safe='')}/"
                f"{quote(variation, safe='')}/files"
            )
            params: Dict[str, Any] = {"pageSize": FILES_PAGE_SIZE}
            if page_token:
                params["pageToken"] = page_token
            payload = self._get_json(url, params=params)
            batch = payload.get("files") or payload.get("Files") or []
            if isinstance(batch, list):
                files.extend([item for item in batch if isinstance(item, dict)])
            if select_readme_file(files, max_bytes=self.max_bytes):
                break
            page_token = str(
                payload.get("nextPageToken") or payload.get("next_page_token") or ""
            ).strip()
            if not page_token:
                break
        return files

    def _download_file(
        self,
        parsed: Tuple[str, str, str, str],
        version: str,
        file_name: str,
    ) -> Optional[str]:
        owner, model, framework, variation = parsed
        path = quote(file_name, safe="/")
        url = (
            f"{KAGGLE_BASE}/models/{quote(owner, safe='')}/"
            f"{quote(model, safe='')}/{quote(framework, safe='')}/"
            f"{quote(variation, safe='')}/{quote(str(version), safe='')}/"
            f"download/{path}"
        )
        response = self._get(url, accept="*/*", stream=True)
        if response is None:
            return None
        chunks: List[bytes] = []
        total = 0
        try:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > self.max_bytes:
                    logger.info("Aborted README download over %d bytes: %s", total, url)
                    return None
                chunks.append(chunk)
        finally:
            response.close()
        raw = b"".join(chunks)
        if not raw:
            return None
        if b"\x00" in raw[:1024]:
            logger.info("Skipped binary README download for %s", url)
            return None
        text = raw.decode("utf-8", errors="replace").strip()
        return text or None

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self._get(url, params=params, accept="application/json")
        if response is None:
            return {}
        try:
            payload = response.json()
        except ValueError:
            logger.warning("Invalid JSON from %s", url)
            return {}
        finally:
            response.close()
        return payload if isinstance(payload, dict) else {}

    def _get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        accept: str = "application/json",
        stream: bool = False,
    ) -> Optional[requests.Response]:
        session = self.crawler._session()
        timeout = self.crawler.timeout
        for attempt in range(1, self.crawler.max_retries + 1):
            try:
                response = session.get(
                    url,
                    params=params,
                    timeout=timeout,
                    stream=stream,
                    headers={"Accept": accept},
                    allow_redirects=True,
                )
            except requests.RequestException:
                if attempt == self.crawler.max_retries:
                    raise
                continue
            if response.status_code == 429:
                response.close()
                time.sleep(min(2 ** attempt, 30))
                continue
            if response.status_code in RETRY_STATUS:
                response.close()
                if attempt == self.crawler.max_retries:
                    return None
                continue
            if response.status_code in (404, 400, 401, 403, 410):
                response.close()
                return None
            if response.ok:
                return response
            response.close()
            return None
        return None
