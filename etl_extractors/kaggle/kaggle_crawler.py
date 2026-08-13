"""
Kaggle model-card crawler.

Fetches model cards from the Kaggle API for every model listed in the Meta
Kaggle dataset. Parallel, resumable, and incremental.

Rate limiting notes (measured against the live API, not guessed):
  Kaggle enforces a rolling hourly quota on models/get of roughly 7-9k
  records. Throttling occurs even at 0.5 req/s, which rules out a per-second
  speed cap. Multiple configurations converged on the same hourly total, so
  raising RPS does NOT increase throughput - it only produces more 429s and
  wastes quota on rejected requests. These values are class constants rather
  than config for that reason.

Baseline crawl of ~42k models takes ~6h. Incremental runs fetch only new or
changed models (~1k) and take ~10 min.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

KAGGLE_BASE = "https://www.kaggle.com/api/v1"

TERMINAL_STATUS = {400, 401, 403, 404, 410}
RETRY_STATUS = {500, 502, 503, 504}


# ==========================================================================
# Rate limiting
# ==========================================================================

class _RateLimiter:
    """
    Adaptive global rate limiter (AIMD - additive increase, multiplicative
    decrease). Shared across all worker threads.
    """

    def __init__(self, rps: float, min_rps: float, max_rps: float,
                 increase_after: int = 50, increase_step: float = 0.5):
        self.rps = float(rps)
        self.min_rps = float(min_rps)
        self.max_rps = float(max_rps)
        self.increase_after = increase_after
        self.increase_step = increase_step
        self._lock = threading.Lock()
        self._next_at = time.monotonic()
        self._streak = 0

    def acquire(self) -> None:
        with self._lock:
            interval = 1.0 / self.rps
            now = time.monotonic()
            self._next_at = max(self._next_at, now)
            wait = self._next_at - now
            self._next_at += interval
        if wait > 0:
            time.sleep(wait)

    def penalize(self) -> None:
        with self._lock:
            self._streak = 0
            new = max(self.min_rps, self.rps / 2.0)
            changed = new != self.rps
            self.rps = new
        if changed:
            logger.debug("Rate limit lowered to %.2f rps", new)

    def reward(self) -> None:
        with self._lock:
            self._streak += 1
            if self._streak < self.increase_after or self.rps >= self.max_rps:
                return
            self._streak = 0
            self.rps = min(self.max_rps, self.rps + self.increase_step)
            new = self.rps
        logger.debug("Rate limit raised to %.2f rps", new)


class _Brake:
    """On a 429, all workers pause together rather than piling on."""

    def __init__(self, limiter: _RateLimiter, stop: threading.Event):
        self._open = threading.Event()
        self._open.set()
        self._lock = threading.Lock()
        self._limiter = limiter
        self._stop = stop
        self.engagements = 0

    def wait(self) -> None:
        self._open.wait()

    def engage(self, seconds: float) -> None:
        with self._lock:
            if not self._open.is_set():
                return  # another thread is already braking
            self._open.clear()
            self.engagements += 1
        self._limiter.penalize()
        logger.info("Rate limited; pausing all workers %.0fs (pause #%d)",
                    seconds, self.engagements)
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self._stop.is_set():
            time.sleep(min(0.5, end - time.monotonic()))
        self._open.set()


# ==========================================================================
# Extractor
# ==========================================================================

class KaggleCrawler:
    """
    Extract Kaggle model cards into an append-only NDJSON log plus a final
    JSON array.

    Output layout under ``output_dir``::

        meta_kaggle/                    Models/Organizations/Users CSVs
        kaggle_all_model_refs.json      owner/slug list
        kaggle_models_raw.ndjson        append-only, drives resume + dedup
        kaggle_models_raw.json          final array
        kaggle_model_get_failures.json
        kaggle_model_get_progress.json
        kaggle_fetch_state.json         fingerprints for incremental runs
    """

    # Measured ceiling - see module docstring. Not exposed via config.
    RPS = 2.0
    MIN_RPS = 0.5
    MAX_RPS = 3.0

    def __init__(
        self,
        output_dir: str,
        threads: int = 8,
        max_retries: int = 6,
        request_timeout_seconds: int = 30,
        checkpoint_every: int = 200,
        meta_dataset: str = "kaggle/meta-kaggle",
        api_token: Optional[str] = None,
    ):
        self.output_dir = Path(output_dir)
        self.meta_dir = self.output_dir / "meta_kaggle"
        self.refs_file = self.output_dir / "kaggle_all_model_refs.json"
        self.ndjson_file = self.output_dir / "kaggle_models_raw.ndjson"
        self.output_file = self.output_dir / "kaggle_models_raw.json"
        self.failures_file = self.output_dir / "kaggle_model_get_failures.json"
        self.progress_file = self.output_dir / "kaggle_model_get_progress.json"
        self.state_file = self.output_dir / "kaggle_fetch_state.json"

        self.meta_dir.mkdir(parents=True, exist_ok=True)

        self.threads = threads
        self.max_retries = max_retries
        self.timeout = request_timeout_seconds
        self.checkpoint_every = checkpoint_every
        self.meta_dataset = meta_dataset

        # `import kaggle` authenticates on import and pops KAGGLE_API_TOKEN
        # out of os.environ (Kaggle/kaggle-cli#882), so capture it up front.
        self._token = (api_token or os.getenv("KAGGLE_API_TOKEN") or "").strip()
        if not self._token:
            token_file = Path.home() / ".kaggle" / "access_token"
            if token_file.exists():
                self._token = token_file.read_text(encoding="utf-8").strip()

        self._auth_mode: Optional[str] = None
        self._local = threading.local()
        self._stop = threading.Event()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _auth_candidates(self) -> List[Tuple[str, Dict[str, Any], str]]:
        out = []
        if self._token:
            out.append(("bearer",
                        {"headers": {"Authorization": f"Bearer {self._token}"}},
                        "KAGGLE_API_TOKEN"))
        user, key = os.getenv("KAGGLE_USERNAME"), os.getenv("KAGGLE_KEY")
        if user and key:
            out.append(("basic",
                        {"auth": (user.strip(), key.strip())},
                        "KAGGLE_USERNAME/KEY"))
        return out

    def check_credentials(self) -> bool:
        """Probe the API and remember which auth scheme works."""
        candidates = self._auth_candidates()
        if not candidates:
            raise RuntimeError(
                "No Kaggle credentials found. Set KAGGLE_API_TOKEN in .env "
                "(kaggle.com/settings -> API -> Generate New Token)."
            )

        errors = []
        for mode, kwargs, label in candidates:
            try:
                r = requests.get(f"{KAGGLE_BASE}/models/list",
                                 params={"pageSize": 1},
                                 timeout=self.timeout, **kwargs)
            except requests.RequestException as e:
                errors.append(f"{label}: {type(e).__name__}: {e}")
                continue
            if r.ok:
                self._auth_mode = mode
                logger.info("Kaggle credentials accepted (%s)", label)
                return True
            errors.append(f"{label}: HTTP {r.status_code}")

        raise RuntimeError("Kaggle rejected all credentials: " + "; ".join(errors))

    def _session(self) -> requests.Session:
        """One pooled Session per worker thread."""
        s = getattr(self._local, "session", None)
        if s is None:
            if self._auth_mode is None:
                self.check_credentials()
            s = requests.Session()
            if self._auth_mode == "bearer":
                s.headers["Authorization"] = f"Bearer {self._token}"
            else:
                s.auth = (os.environ["KAGGLE_USERNAME"].strip(),
                          os.environ["KAGGLE_KEY"].strip())
            s.headers["Accept"] = "application/json"
            s.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=4,
                                            max_retries=0))
            self._local.session = s
        return s

    def _kaggle_client(self):
        """The module-level pre-authenticated client (see #882)."""
        import kaggle
        api = getattr(kaggle, "api", None)
        if api is not None:
            return api
        from kaggle.api.kaggle_api_extended import KaggleApi
        api = KaggleApi()
        api.authenticate()
        return api

    # ------------------------------------------------------------------
    # Meta Kaggle -> refs
    # ------------------------------------------------------------------

    def ensure_meta_kaggle_csvs(self, force: bool = False) -> None:
        api = self._kaggle_client()
        for name in ("Models.csv", "Organizations.csv", "Users.csv"):
            path = self.meta_dir / name
            if path.exists() and not force:
                logger.info("Cached %s (%.1f MB)", name, path.stat().st_size / 1e6)
                continue
            logger.info("Downloading %s ...", name)
            api.dataset_download_file(self.meta_dataset, name,
                                      path=str(self.meta_dir), force=True, quiet=True)
            logger.info("Saved %s (%.1f MB)", name, path.stat().st_size / 1e6)

    def _join_model_rows(self) -> Iterator[Tuple[str, Dict[str, str]]]:
        """Yield (ref, row) for every model that resolves to an owner."""
        with open(self.meta_dir / "Models.csv", newline="", encoding="utf-8") as f:
            models = list(csv.DictReader(f))
        with open(self.meta_dir / "Organizations.csv", newline="", encoding="utf-8") as f:
            orgs = {r["Id"]: r["Slug"] for r in csv.DictReader(f)}

        needed = {r["OwnerUserId"].strip() for r in models
                  if (r.get("OwnerUserId") or "").strip()}
        users = {}
        with open(self.meta_dir / "Users.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["Id"] in needed:
                    users[row["Id"]] = row["UserName"]

        for row in models:
            slug = (row.get("CurrentSlug") or "").strip()
            if not slug:
                continue
            org_id = (row.get("OwnerOrganizationId") or "").strip()
            user_id = (row.get("OwnerUserId") or "").strip()
            owner = orgs.get(org_id) if org_id else users.get(user_id)
            if owner:
                yield f"{owner}/{slug}", row

    def build_refs(self) -> List[str]:
        refs = sorted({ref for ref, _ in self._join_model_rows()})
        self.refs_file.write_text(json.dumps(refs, indent=2), encoding="utf-8")
        logger.info("Built %d unique refs -> %s", len(refs), self.refs_file)
        return refs

    def load_or_build_refs(self, rebuild: bool = False) -> List[str]:
        if self.refs_file.exists() and not rebuild:
            refs = json.loads(self.refs_file.read_text(encoding="utf-8"))
            logger.info("Loaded %d refs from %s", len(refs), self.refs_file)
            return refs
        self.ensure_meta_kaggle_csvs()
        return self.build_refs()

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    @staticmethod
    def _change_columns(fieldnames: List[str]) -> List[str]:
        """
        Pick columns that signal a model changed. Meta Kaggle column names
        aren't guaranteed stable across releases, so detect rather than
        hardcode: anything date-ish or version-ish, plus the slug.
        """
        if not fieldnames:
            return []
        wanted = [n for n in fieldnames
                  if any(t in n.lower()
                         for t in ("date", "version", "updated", "lastactivity"))]
        if "CurrentSlug" in fieldnames:
            wanted.append("CurrentSlug")
        return sorted(set(wanted))

    def build_ref_fingerprints(self) -> Tuple[Dict[str, str], List[str]]:
        fps: Dict[str, str] = {}
        cols: Optional[List[str]] = None
        for ref, row in self._join_model_rows():
            if cols is None:
                cols = self._change_columns(list(row.keys()))
                logger.info("Change-signal columns: %s", cols or "(none)")
            if not cols:
                fps[ref] = ""
                continue
            blob = "|".join(str(row.get(c, "")) for c in cols)
            fps[ref] = hashlib.md5(blob.encode("utf-8")).hexdigest()[:12]
        return fps, (cols or [])

    def plan_incremental(self) -> Dict[str, Any]:
        """Return {new, changed, unchanged, gone, fingerprints, columns}."""
        fps, cols = self.build_ref_fingerprints()

        old: Dict[str, str] = {}
        if self.state_file.exists():
            old = json.loads(self.state_file.read_text(encoding="utf-8")).get(
                "fingerprints", {})

        have = self._load_done_refs()
        new, changed, unchanged = [], [], []
        for ref, fp in fps.items():
            if ref not in have:
                new.append(ref)
            elif cols and old.get(ref) != fp:
                changed.append(ref)
            else:
                unchanged.append(ref)

        plan = {"new": sorted(new), "changed": sorted(changed),
                "unchanged": sorted(unchanged), "gone": sorted(have - set(fps)),
                "fingerprints": fps, "columns": cols}
        logger.info("Plan: %d new, %d changed, %d unchanged",
                    len(new), len(changed), len(unchanged))
        return plan

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    def _fetch_one(self, ref, limiter, brake, out_q, fail_q, stats) -> None:
        if self._stop.is_set():
            return
        owner, _, slug = ref.partition("/")
        url = f"{KAGGLE_BASE}/models/{owner}/{slug}/get"

        for attempt in range(1, self.max_retries + 1):
            if self._stop.is_set():
                return
            brake.wait()
            limiter.acquire()

            try:
                r = self._session().get(url, timeout=self.timeout)
            except requests.RequestException as e:
                if attempt == self.max_retries:
                    fail_q.put({"ref": ref, "error": f"{type(e).__name__}: {e}"})
                    stats["failed"] += 1
                    return
                time.sleep(min(2 ** attempt, 30))
                continue

            if r.status_code == 429:
                stats["rate_limited"] += 1
                try:
                    wait = max(float(r.headers.get("Retry-After", 60)), 1.0)
                except (TypeError, ValueError):
                    wait = 60.0
                brake.engage(wait)
                continue

            if r.status_code in RETRY_STATUS:
                if attempt == self.max_retries:
                    fail_q.put({"ref": ref, "error": f"HTTP {r.status_code}"})
                    stats["failed"] += 1
                    return
                time.sleep(min(2 ** attempt, 30))
                continue

            if r.status_code in TERMINAL_STATUS:
                fail_q.put({"ref": ref, "error": f"HTTP {r.status_code}"})
                stats["failed"] += 1
                return

            if r.ok:
                try:
                    data = r.json()
                except ValueError:
                    fail_q.put({"ref": ref, "error": "invalid JSON"})
                    stats["failed"] += 1
                    return
                data.setdefault("ref", ref)
                out_q.put(data)
                stats["ok"] += 1
                limiter.reward()
                return

            fail_q.put({"ref": ref, "error": f"HTTP {r.status_code}"})
            stats["failed"] += 1
            return

        fail_q.put({"ref": ref, "error": "max_retries exceeded"})
        stats["failed"] += 1

    def _writer(self, q: "queue.Queue") -> None:
        """Single thread owns the file handle. Sentinel None ends it."""
        with open(self.ndjson_file, "a", encoding="utf-8") as f:
            n = 0
            while True:
                row = q.get()
                if row is None:
                    break
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                n += 1
                if n % self.checkpoint_every == 0:
                    f.flush()
                    os.fsync(f.fileno())
            f.flush()
            os.fsync(f.fileno())

    def _load_done_refs(self) -> Set[str]:
        done: Set[str] = set()
        if not self.ndjson_file.exists():
            return done
        with open(self.ndjson_file, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    ref = json.loads(line).get("ref")
                except ValueError:
                    continue  # tolerate a torn last line from a hard kill
                if ref:
                    done.add(ref)
        return done

    def _rewrite_json_array(self) -> int:
        """
        Stream NDJSON -> JSON array, keeping only the LAST record per ref.
        Incremental runs append fresh copies of changed models, so older
        copies must be dropped. Two passes keep memory flat.
        """
        if not self.ndjson_file.exists():
            return 0

        keep: Dict[str, int] = {}
        malformed = 0
        with open(self.ndjson_file, encoding="utf-8") as src:
            for i, line in enumerate(src):
                if not line.strip():
                    continue
                try:
                    ref = json.loads(line).get("ref")
                except ValueError:
                    malformed += 1
                    continue
                keep[ref or f"__noref_{i}"] = i
        winners = set(keep.values())

        tmp = str(self.output_file) + ".tmp"
        n = 0
        with open(self.ndjson_file, encoding="utf-8") as src, \
                open(tmp, "w", encoding="utf-8") as dst:
            dst.write("[")
            first = True
            for i, line in enumerate(src):
                if i not in winners:
                    continue
                if not first:
                    dst.write(",")
                dst.write(line.rstrip("\n"))
                first = False
                n += 1
            dst.write("]")
        os.replace(tmp, self.output_file)

        if malformed:
            logger.warning("Skipped %d malformed NDJSON line(s)", malformed)
        return n

    def fetch_model_cards(
        self,
        refs: Optional[List[str]] = None,
        limit: Optional[int] = None,
        skip_done: bool = True,
        retry_failed: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch model cards for ``refs``. Resumable and interrupt-safe.

        Returns a summary dict suitable for Dagster metadata.
        """
        self._stop.clear()
        if self._auth_mode is None:
            self.check_credentials()

        if refs is None:
            refs = self.load_or_build_refs()
        if limit:
            refs = refs[:limit]

        done = self._load_done_refs() if skip_done else set()

        failed: List[Dict[str, str]] = []
        if self.failures_file.exists():
            failed = json.loads(self.failures_file.read_text(encoding="utf-8"))
        failed_refs = set() if retry_failed else {r["ref"] for r in failed}
        if retry_failed:
            failed = []

        remaining = [r for r in refs if r not in done and r not in failed_refs]
        logger.info("Fetching %d refs (%d already held, %d previously failed)",
                    len(remaining), len(done), len(failed_refs))

        if not remaining:
            total = self._rewrite_json_array()
            return {"fetched": 0, "total_records": total, "failed": len(failed),
                    "elapsed_s": 0.0, "rate_limit_pauses": 0}

        limiter = _RateLimiter(self.RPS, self.MIN_RPS, self.MAX_RPS)
        brake = _Brake(limiter, self._stop)
        stats = {"ok": 0, "failed": 0, "rate_limited": 0}
        out_q: "queue.Queue" = queue.Queue(maxsize=2000)
        fail_q: "queue.Queue" = queue.Queue()

        writer = threading.Thread(target=self._writer, args=(out_q,), daemon=True)
        writer.start()

        t0 = time.monotonic()
        pool = ThreadPoolExecutor(max_workers=self.threads)
        futures = [pool.submit(self._fetch_one, ref, limiter, brake,
                               out_q, fail_q, stats) for ref in remaining]
        try:
            for i, _ in enumerate(as_completed(futures), 1):
                if i % 500 == 0 or i == len(futures):
                    elapsed = time.monotonic() - t0
                    rate = i / elapsed if elapsed else 0
                    logger.info("%d/%d ok=%d fail=%d 429s=%d %.1f/s eta %.0fm",
                                i, len(futures), stats["ok"], stats["failed"],
                                stats["rate_limited"], rate,
                                (len(futures) - i) / rate / 60 if rate else 0)
        except KeyboardInterrupt:
            logger.warning("Interrupted - flushing collected records")
            self._stop.set()
            for fut in futures:
                fut.cancel()
        finally:
            pool.shutdown(wait=True)
            out_q.put(None)
            writer.join()

        while not fail_q.empty():
            failed.append(fail_q.get())

        total = self._rewrite_json_array()
        elapsed = time.monotonic() - t0

        self._save_json(self.failures_file, failed)
        summary = {
            "fetched": stats["ok"],
            "total_records": total,
            "failed": len(failed),
            "rate_limited": stats["rate_limited"],
            "rate_limit_pauses": brake.engagements,
            "elapsed_s": round(elapsed, 1),
            "records_per_second": round(stats["ok"] / elapsed, 2) if elapsed else 0,
        }
        self._save_json(self.progress_file, summary)
        logger.info("Done: %d records in %.1f min (%.2f/s), %d failed",
                    total, elapsed / 60, summary["records_per_second"], len(failed))
        return summary

    def fetch_incremental(self, refresh_csvs: bool = True,
                          force_all: bool = False,
                          limit: Optional[int] = None) -> Dict[str, Any]:
        """Fetch only models that are new or changed since the last run."""
        if refresh_csvs:
            self.ensure_meta_kaggle_csvs(force=True)

        plan = self.plan_incremental()
        todo = sorted(plan["fingerprints"]) if force_all else plan["new"] + plan["changed"]

        if not todo:
            total = self._rewrite_json_array()
            logger.info("Nothing to fetch; %d records current", total)
            return {"fetched": 0, "total_records": total, "new": 0, "changed": 0}

        # skip_done=False because changed refs are already in the NDJSON and
        # must be refetched; _rewrite_json_array dedupes by ref afterwards.
        summary = self.fetch_model_cards(refs=todo, limit=limit, skip_done=False)

        # Record fingerprints only for refs actually held, so an interrupted
        # run never marks unfetched models as current.
        have = self._load_done_refs()
        self._save_json(self.state_file, {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "columns": plan["columns"],
            "fingerprints": {r: fp for r, fp in plan["fingerprints"].items()
                             if r in have},
        })
        summary.update({"new": len(plan["new"]), "changed": len(plan["changed"])})
        return summary

    def load_records(self) -> List[Dict[str, Any]]:
        """
        Return every fetched model card, newest copy per ref.

        Reads the deduplicated JSON array written by _rewrite_json_array so
        callers get the same records the file on disk holds.
        """
        if not self.output_file.exists():
            self._rewrite_json_array()
        if not self.output_file.exists():
            return []
        return json.loads(self.output_file.read_text(encoding="utf-8"))

    @staticmethod
    def _save_json(path, data) -> None:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp, path)