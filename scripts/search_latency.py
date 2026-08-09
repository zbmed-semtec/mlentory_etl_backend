"""Measure STELLA page-1 latency vs direct MLentory endpoints, rankers and ES page 2.

Sections:
  1) Path comparison: direct BASE/EXP endpoints, via ranker containers, full STELLA
  2) Page 1 vs page 2: STELLA vs Elasticsearch (with page-1 exclude_ids)
  3) STELLA cache: first call vs cached repeats (same query + session_id)

Example:
  python3 scripts/search_latency.py
  python3 scripts/search_latency.py --api http://localhost:8008/api/v1 --calls 5
  python3 scripts/search_latency.py --skip-compare --skip-cache
  python3 scripts/search_latency.py --skip-cache --path-calls 3
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

# Edit these to test different queries
DEFAULT_QUERIES = [
    "bert",
    "image classification",
    "llama",
    "medical",
    "transformer",
]

# Edit these to test different facets
COMMON_FACETS = {
    "filters": "{}",
    "facets": '["mlTask","license","keywords"]',
    "facet_size": "20",
    "facet_query": "{}",
}


def timed_get(url: str, *, timeout: float) -> tuple[int, float, dict | None, str]:
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read()
            elapsed_ms = (time.perf_counter() - t0) * 1000
            return resp.status, elapsed_ms, json.loads(body.decode()), ""
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return e.code, elapsed_ms, None, e.read().decode()[:200]
    except Exception as e:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return 0, elapsed_ms, None, str(e)[:200]


def n_models(data: dict | None) -> int:
    return len((data or {}).get("models") or [])


def common_params(query: str, *, limit: int, page: int = 1) -> dict[str, str]:
    return {
        **COMMON_FACETS,
        "query": query,
        "page": str(page),
        "limit": str(limit),
    }


def url_direct_search(api_base: str, query: str, *, limit: int) -> str:
    params = common_params(query, limit=limit)
    return f"{api_base.rstrip('/')}/models/search?{urllib.parse.urlencode(params)}"


def url_direct_vector(api_base: str, query: str, *, limit: int) -> str:
    params = common_params(query, limit=limit)
    return f"{api_base.rstrip('/')}/models/search_with_vector?{urllib.parse.urlencode(params)}"


def url_via_ranker(ranker_base: str, backend_path: str, query: str, *, limit: int) -> str:
    params = common_params(query, limit=limit)
    return (
        f"{ranker_base.rstrip('/')}/{backend_path.strip('/')}"
        f"?{urllib.parse.urlencode(params)}"
    )


def url_stella(api_base: str, query: str, session_id: str, *, limit: int) -> str:
    params = {**common_params(query, limit=limit), "session_id": session_id}
    return f"{api_base.rstrip('/')}/stella/search_with_stella?{urllib.parse.urlencode(params)}"


def url_es_search(
    api_base: str,
    query: str,
    *,
    page: int,
    page_size: int,
    exclude_ids: list[str] | None = None,
) -> str:
    """Faceted ES search as used by frontend page 2+ (page_size, optional exclude_ids)."""
    params = {
        **COMMON_FACETS,
        "query": query,
        "page": str(page),
        "page_size": str(page_size),
    }
    if exclude_ids:
        params["exclude_ids"] = json.dumps(exclude_ids)
    return f"{api_base.rstrip('/')}/models/search?{urllib.parse.urlencode(params)}"


def extract_exclude_ids(models: list[dict]) -> list[str]:
    """Mirror frontend extractModelDedupeKeys for ES exclude_ids."""
    keys: set[str] = set()
    for model in models:
        mlentory_id = model.get("mlentory_id")
        if mlentory_id is not None and str(mlentory_id) not in ("", "-1"):
            keys.add(str(mlentory_id))
        db_id = model.get("db_identifier")
        if isinstance(db_id, list):
            for item in db_id:
                if item:
                    keys.add(str(item))
        elif db_id:
            keys.add(str(db_id))
    return sorted(keys)


def summarize(times: list[float]) -> str:
    return (
        f"n={len(times)} mean={statistics.mean(times):.0f} "
        f"median={statistics.median(times):.0f} "
        f"min={min(times):.0f} max={max(times):.0f}"
    )


def measure_path(
    label: str,
    url_fn: Callable[[str], str],
    queries: list[str],
    *,
    calls: int,
    timeout: float,
    show_rid: bool = False,
) -> tuple[list[float], int]:
    print(f"\n=== {label} ===")
    header = f'{"query":<22} {"#":>2} {"ms":>8}'
    if show_rid:
        header += f' {"rid":>8}'
    header += f' {"models":>7} {"status":>6}'
    print(header)
    print("-" * len(header))

    times: list[float] = []
    failures = 0
    for query in queries:
        for n in range(1, calls + 1):
            code, ms, data, err = timed_get(url_fn(query), timeout=timeout)
            ok = code == 200 and bool(data and data.get("models") is not None) and "error" not in (data or {})
            if code == 200 and data and data.get("models"):
                ok = True
            rid = ((data or {}).get("_stella") or {}).get("rid")
            times.append(ms)
            if not ok:
                failures += 1
            line = f"{query:<22} {n:>2} {ms:>8.0f}"
            if show_rid:
                line += f" {str(rid):>8}"
            line += f" {n_models(data):>7} {'OK' if ok else 'FAIL'}"
            print(line)
            if not ok and err:
                print(f"  error: {err}")

    print(f"→ {summarize(times)}")
    return times, failures


def run_path_comparison(
    *,
    api_base: str,
    base_ranker: str,
    exp_ranker: str,
    backend_path: str,
    queries: list[str],
    calls: int,
    limit: int,
    timeout: float,
) -> int:
    print("\n########## Path comparison (direct vs rankers vs STELLA) ##########")
    print(f"api = {api_base}")
    print(f"base_ranker = {base_ranker}")
    print(f"exp_ranker = {exp_ranker}")
    print(f"backend_path = {backend_path}")
    print(f"path_calls per query = {calls}")
    print("STELLA uses a fresh session_id each call (uncached).")

    # Warmup once each so cold starts don't dominate.
    warmup_urls = [
        ("search", url_direct_search(api_base, "warmup", limit=1)),
        ("vector", url_direct_vector(api_base, "warmup", limit=1)),
        ("base", url_via_ranker(base_ranker, backend_path, "warmup", limit=1)),
        ("exp", url_via_ranker(exp_ranker, backend_path, "warmup", limit=1)),
        ("stella", url_stella(api_base, "warmup", f"warmup-{int(time.time())}", limit=1)),
    ]
    print("\nWarmup:")
    for name, url in warmup_urls:
        code, ms, data, err = timed_get(url, timeout=timeout)
        status = "OK" if code == 200 else f"FAIL({code})"
        print(f"  {name}: {status} {ms:.0f} ms models={n_models(data)}" + (f" {err}" if err else ""))

    ms_search, f1 = measure_path(
        "1) Direct BASE endpoint: GET /models/search",
        lambda q: url_direct_search(api_base, q, limit=limit),
        queries,
        calls=calls,
        timeout=timeout,
    )
    ms_vector, f2 = measure_path(
        "2) Direct EXP endpoint: GET /models/search_with_vector",
        lambda q: url_direct_vector(api_base, q, limit=limit),
        queries,
        calls=calls,
        timeout=timeout,
    )
    ms_base, f3 = measure_path(
        "3) Via BASE container → /models/search",
        lambda q: url_via_ranker(base_ranker, backend_path, q, limit=limit),
        queries,
        calls=calls,
        timeout=timeout,
    )
    ms_exp, f4 = measure_path(
        "4) Via EXP container → /models/search_with_vector",
        lambda q: url_via_ranker(exp_ranker, backend_path, q, limit=limit),
        queries,
        calls=calls,
        timeout=timeout,
    )

    stella_counter = {"n": 0}

    def stella_url(q: str) -> str:
        stella_counter["n"] += 1
        sid = f"path-cmp-{int(time.time() * 1000)}-{q.replace(' ', '_')}-{stella_counter['n']}"
        return url_stella(api_base, q, sid, limit=limit)

    ms_stella, f5 = measure_path(
        "5) Full STELLA: GET /stella/search_with_stella (fresh session each call)",
        stella_url,
        queries,
        calls=calls,
        timeout=timeout,
        show_rid=True,
    )

    mean_search = statistics.mean(ms_search)
    mean_vector = statistics.mean(ms_vector)
    mean_base = statistics.mean(ms_base)
    mean_exp = statistics.mean(ms_exp)
    mean_stella = statistics.mean(ms_stella)
    parallel_floor = max(mean_base, mean_exp)
    serial_floor = mean_base + mean_exp

    print("\n=== Path summary (mean ms) ===")
    print(f"{mean_search:>8.0f} ms  Direct /models/search (BASE target)")
    print(f"{mean_vector:>8.0f} ms  Direct /models/search_with_vector (EXP target)")
    print(f"{mean_base:>8.0f} ms  Via mlentory-base container")
    print(f"{mean_exp:>8.0f} ms  Via mlentory-experiment container")
    print(f"{mean_stella:>8.0f} ms  Full search_with_stella (uncached)")

    print("\n=== Path overhead ===")
    print(f"BASE container hop (vs direct search):   {mean_base - mean_search:+.0f} ms")
    print(f"EXP container hop (vs direct vector):    {mean_exp - mean_vector:+.0f} ms")
    print(
        f"STELLA vs parallel floor max(base,exp):  "
        f"{mean_stella - parallel_floor:+.0f} ms  (floor={parallel_floor:.0f})"
    )
    print(
        f"STELLA vs serial floor base+exp:         "
        f"{mean_stella - serial_floor:+.0f} ms  (floor={serial_floor:.0f})"
    )
    print(f"STELLA / direct search:                  {mean_stella / mean_search:.1f}x")
    print(f"STELLA / direct vector:                  {mean_stella / mean_vector:.1f}x")

    return f1 + f2 + f3 + f4 + f5


def run_page1_vs_page2(
    *,
    api_base: str,
    queries: list[str],
    calls: int,
    limit: int,
    timeout: float,
) -> int:
    """Cached STELLA page 1 vs ES page 2 (frontend continuation with exclude_ids)."""
    print("\n########## Page 1 (STELLA cached) vs page 2 (Elasticsearch) ##########")
    print(f"api = {api_base}")
    print(f"cached page_calls per query = {calls}")
    print(f"page_size / limit = {limit}")
    print("Per query: 1 uncached STELLA (prime cache) → N cached STELLA + ES page 2.")
    print("ES page 2: /models/search with exclude_ids from STELLA page-1 results.\n")

    print("Warmup:")
    for name, url in [
        ("stella", url_stella(api_base, "warmup", f"p1p2-warmup-{int(time.time())}", limit=limit)),
        ("es_p2", url_es_search(api_base, "warmup", page=2, page_size=limit)),
    ]:
        code, ms, data, err = timed_get(url, timeout=timeout)
        status = "OK" if code == 200 else f"FAIL({code})"
        print(f"  {name}: {status} {ms:.0f} ms models={n_models(data)}" + (f" {err}" if err else ""))

    print(
        f'\n{"query":<22} {"kind":<8} {"#":>2} {"ms":>8} {"rid":>8} '
        f'{"models":>7} {"excl":>5} {"status":>6}'
    )
    print("-" * 72)

    first_times: list[float] = []
    cached_times: list[float] = []
    es_times: list[float] = []
    failures = 0
    prefix = f"p1p2-cached-{int(time.time())}"

    for query in queries:
        sid = f"{prefix}-{query.replace(' ', '_')}"

        # Prime STELLA cache (uncached page 1)
        s_code, s_ms, s_data, s_err = timed_get(
            url_stella(api_base, query, sid, limit=limit),
            timeout=timeout,
        )
        s_ok = s_code == 200 and bool(s_data and s_data.get("models"))
        exclude_ids = extract_exclude_ids((s_data or {}).get("models") or []) if s_ok else []
        rid = ((s_data or {}).get("_stella") or {}).get("rid")
        first_times.append(s_ms)
        if not s_ok:
            failures += 1
        print(
            f"{query:<22} {'first':<8} {1:>2} {s_ms:>8.0f} {str(rid):>8} "
            f"{n_models(s_data):>7} {len(exclude_ids):>5} {'OK' if s_ok else 'FAIL':>6}"
        )
        if not s_ok and s_err:
            print(f"  stella error: {s_err}")

        q_cached: list[float] = []
        q_es: list[float] = []

        for n in range(1, calls + 1):
            c_code, c_ms, c_data, c_err = timed_get(
                url_stella(api_base, query, sid, limit=limit),
                timeout=timeout,
            )
            c_ok = c_code == 200 and bool(c_data and c_data.get("models"))
            c_rid = ((c_data or {}).get("_stella") or {}).get("rid")
            # Prefer ids from cached response; fall back to primed set
            c_exclude = extract_exclude_ids((c_data or {}).get("models") or []) if c_ok else exclude_ids

            e_code, e_ms, e_data, e_err = timed_get(
                url_es_search(
                    api_base,
                    query,
                    page=2,
                    page_size=limit,
                    exclude_ids=c_exclude or None,
                ),
                timeout=timeout,
            )
            e_ok = e_code == 200 and e_data is not None and "models" in e_data

            cached_times.append(c_ms)
            es_times.append(e_ms)
            q_cached.append(c_ms)
            q_es.append(e_ms)
            if not c_ok or not e_ok:
                failures += 1

            print(
                f"{query:<22} {'cached':<8} {n:>2} {c_ms:>8.0f} {str(c_rid):>8} "
                f"{n_models(c_data):>7} {len(c_exclude):>5} {'OK' if c_ok else 'FAIL':>6}"
            )
            print(
                f"{query:<22} {'es_p2':<8} {n:>2} {e_ms:>8.0f} {'-':>8} "
                f"{n_models(e_data):>7} {len(c_exclude):>5} {'OK' if e_ok else 'FAIL':>6}"
            )
            if not c_ok and c_err:
                print(f"  stella cached error: {c_err}")
            if not e_ok and e_err:
                print(f"  es error: {e_err}")

        print(
            f"  → first={s_ms:.0f} ms | cached mean={statistics.mean(q_cached):.0f} ms | "
            f"es_p2 mean={statistics.mean(q_es):.0f} ms | "
            f"cached/es={statistics.mean(q_cached) / statistics.mean(q_es):.2f}x | "
            f"rid stable={rid == ((c_data or {}).get('_stella') or {}).get('rid') if calls else False}"
        )
        print()

    print("=== Page 1 (cached) vs page 2 overall ===")
    print(f"STELLA page 1 first (uncached): {summarize(first_times)}")
    print(f"STELLA page 1 cached:           {summarize(cached_times)}")
    print(f"ES page 2 (+exclude_ids):       {summarize(es_times)}")
    print(
        f"Cached STELLA / ES = {statistics.mean(cached_times) / statistics.mean(es_times):.2f}x "
        f"(delta {statistics.mean(cached_times) - statistics.mean(es_times):+.0f} ms)"
    )
    print(
        f"First STELLA / ES = {statistics.mean(first_times) / statistics.mean(es_times):.2f}x "
        f"(delta {statistics.mean(first_times) - statistics.mean(es_times):+.0f} ms)"
    )
    print(f"Failures: {failures}")
    return failures


def run_cache_latency(
    *,
    api_base: str,
    queries: list[str],
    calls: int,
    limit: int,
    timeout: float,
    session_prefix: str,
) -> int:
    print("\n########## STELLA cache: first vs cached (same session_id) ##########")
    print(f"api = {api_base}")
    print(f"session_prefix = {session_prefix}")
    print(f"calls per query = {calls} (expect call1 slower; later calls ~cached)\n")
    print(f'{"query":<22} {"#":>2} {"ms":>8} {"rid":>8} {"models":>7} {"status":>6}')
    print("-" * 60)

    all_first: list[float] = []
    all_cached: list[float] = []
    failures = 0

    for query in queries:
        sid = f"{session_prefix}-{query.replace(' ', '_')}"
        times: list[float] = []
        rids: list[object] = []

        for n in range(1, calls + 1):
            code, ms, data, err = timed_get(
                url_stella(api_base, query, sid, limit=limit),
                timeout=timeout,
            )
            ok = code == 200 and bool(data and data.get("models"))
            rid = ((data or {}).get("_stella") or {}).get("rid")
            times.append(ms)
            rids.append(rid)
            if n == 1:
                all_first.append(ms)
            else:
                all_cached.append(ms)
            if not ok:
                failures += 1
            print(
                f"{query:<22} {n:>2} {ms:>8.0f} {str(rid):>8} {n_models(data):>7} "
                f'{"OK" if ok else "FAIL"}'
            )
            if not ok and err:
                print(f"  error: {err}")

        cached = times[1:]
        print(
            f"  → first={times[0]:.0f} ms | cached(2-{calls}) "
            f"mean={statistics.mean(cached):.0f} "
            f"median={statistics.median(cached):.0f} "
            f"min={min(cached):.0f} max={max(cached):.0f} | "
            f"speedup={times[0] / statistics.mean(cached):.1f}x | "
            f"rid stable={len(set(rids)) == 1}"
        )
        print()

    print("=== Cache overall ===")
    print(
        f"First calls  (n={len(all_first)}): mean={statistics.mean(all_first):.0f} ms  "
        f"median={statistics.median(all_first):.0f}  "
        f"min={min(all_first):.0f}  max={max(all_first):.0f}"
    )
    print(
        f"Cached 2–{calls}  (n={len(all_cached)}): mean={statistics.mean(all_cached):.0f} ms  "
        f"median={statistics.median(all_cached):.0f}  "
        f"min={min(all_cached):.0f}  max={max(all_cached):.0f}"
    )
    print(
        f"Avg first / avg cached = "
        f"{statistics.mean(all_first) / statistics.mean(all_cached):.1f}x"
    )
    print(f"Failures: {failures}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "STELLA page-1 latency: path comparison, STELLA vs ES page 2, "
            "and first vs cached STELLA calls."
        ),
    )
    parser.add_argument(
        "--api",
        default="http://localhost:8008/api/v1",
        help="API base URL (default: http://localhost:8008/api/v1)",
    )
    parser.add_argument(
        "--base-ranker",
        default="http://localhost:5000",
        help="mlentory-base host URL (default: http://localhost:5000)",
    )
    parser.add_argument(
        "--exp-ranker",
        default="http://localhost:5001",
        help="mlentory-experiment host URL (default: http://localhost:5001)",
    )
    parser.add_argument(
        "--backend-path",
        default="mlentory-api:8000/api/v1/models",
        help="Path STELLA forwards into rankers (default: mlentory-api:8000/api/v1/models)",
    )
    parser.add_argument(
        "--queries",
        nargs="+",
        default=DEFAULT_QUERIES,
        help="Queries to measure (default: built-in list)",
    )
    parser.add_argument(
        "--calls",
        type=int,
        default=5,
        help="STELLA cache calls per query with the same session_id (default: 5)",
    )
    parser.add_argument(
        "--path-calls",
        type=int,
        default=3,
        help="Repeats per query for path comparison (default: 3)",
    )
    parser.add_argument(
        "--page-calls",
        type=int,
        default=3,
        help="Repeats per query for STELLA page1 vs ES page2 (default: 3)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="limit / page size (default: 20)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-request timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--session-prefix",
        default="",
        help="Optional prefix for STELLA cache session ids (default: timestamp-based)",
    )
    parser.add_argument(
        "--skip-compare",
        action="store_true",
        help="Skip path comparison (direct / rankers / STELLA)",
    )
    parser.add_argument(
        "--skip-pages",
        action="store_true",
        help="Skip STELLA page1 vs ES page2 section",
    )
    parser.add_argument(
        "--skip-cache",
        action="store_true",
        help="Skip STELLA first-vs-cached section",
    )
    args = parser.parse_args()

    if args.skip_compare and args.skip_pages and args.skip_cache:
        print(
            "Nothing to run: --skip-compare, --skip-pages, and --skip-cache all set",
            file=sys.stderr,
        )
        return 2

    if not args.skip_cache and args.calls < 2:
        print("--calls must be >= 2 (need a first call and at least one cached call)", file=sys.stderr)
        return 2

    if not args.skip_compare and args.path_calls < 1:
        print("--path-calls must be >= 1", file=sys.stderr)
        return 2

    if not args.skip_pages and args.page_calls < 1:
        print("--page-calls must be >= 1", file=sys.stderr)
        return 2

    failures = 0

    if not args.skip_compare:
        failures += run_path_comparison(
            api_base=args.api,
            base_ranker=args.base_ranker,
            exp_ranker=args.exp_ranker,
            backend_path=args.backend_path,
            queries=args.queries,
            calls=args.path_calls,
            limit=args.limit,
            timeout=args.timeout,
        )

    if not args.skip_pages:
        failures += run_page1_vs_page2(
            api_base=args.api,
            queries=args.queries,
            calls=args.page_calls,
            limit=args.limit,
            timeout=args.timeout,
        )

    if not args.skip_cache:
        prefix = args.session_prefix or f"stella-cache-latency-{int(time.time())}"
        failures += run_cache_latency(
            api_base=args.api,
            queries=args.queries,
            calls=args.calls,
            limit=args.limit,
            timeout=args.timeout,
            session_prefix=prefix,
        )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
