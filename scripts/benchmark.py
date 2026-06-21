"""Performance benchmark for the running typeahead server.

Measures the things the assignment's non-functional section asks for:
  * suggestion read latency (p50/p95/p99)
  * cache hit rate
  * DB read/write counts
  * write reduction from batching

It drives the server purely over HTTP (stdlib only), so start the server first:

    python run.py            # in one terminal
    python -m scripts.benchmark   # in another

Useful flags: --suggest-requests, --search-requests, --concurrency, --base-url
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

PREFIX_SEEDS = [
    "i", "ip", "iph", "iphone", "best", "best ", "che", "cheap", "lap", "laptop",
    "sam", "samsung", "nike", "py", "python", "java", "how", "how to", "wir",
    "wireless", "gam", "gaming", "head", "head", "air", "mon", "monitor", "ssd",
    "key", "mou", "mouse", "wat", "watch", "buy", "down", "amazon", "sony", "dell",
]
SEARCH_SEEDS = [
    "iphone 15", "python tutorial", "best laptop", "cheap headphones",
    "nike shoes", "wireless mouse", "gaming keyboard", "samsung galaxy",
    "airpods pro", "system design interview questions",
]


def _get(base: str, path: str) -> dict:
    with urllib.request.urlopen(base + path, timeout=30) as r:
        return json.loads(r.read().decode())


def _post(base: str, path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _zipf_prefix(rng: random.Random) -> str:
    # bias toward the front of the list so some prefixes are "hot" (cache-friendly)
    idx = min(len(PREFIX_SEEDS) - 1, int(rng.expovariate(1 / 6)))
    base = PREFIX_SEEDS[idx]
    return base


def run_suggest_load(base: str, n: int, concurrency: int, ranking: str) -> list:
    rng = random.Random(7)
    prefixes = [_zipf_prefix(rng) for _ in range(n)]
    latencies: list = []

    def hit(p: str) -> float:
        t0 = time.perf_counter()
        try:
            urllib.request.urlopen(
                f"{base}/suggest?q={urllib.parse.quote(p)}&ranking={ranking}", timeout=30
            ).read()
        except urllib.error.URLError as e:
            print("request failed:", e)
            return -1.0
        return (time.perf_counter() - t0) * 1000

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for ms in ex.map(hit, prefixes):
            if ms >= 0:
                latencies.append(ms)
    return latencies


def run_search_load(base: str, n: int, concurrency: int) -> None:
    rng = random.Random(11)
    queries = [rng.choice(SEARCH_SEEDS) for _ in range(n)]

    def hit(q: str) -> None:
        try:
            _post(base, "/search", {"query": q})
        except urllib.error.URLError as e:
            print("search failed:", e)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(ex.map(hit, queries))


def pct(data: list, p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return s[k]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--suggest-requests", type=int, default=5000)
    ap.add_argument("--search-requests", type=int, default=3000)
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--ranking", default="count", choices=["count", "recent"])
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    try:
        _get(base, "/health")
    except Exception as e:
        print(f"Cannot reach server at {base}: {e}\nStart it with: python run.py")
        sys.exit(1)

    print("=" * 64)
    print("  SEARCH TYPEAHEAD - PERFORMANCE BENCHMARK")
    print("=" * 64)

    # ---- write path: demonstrate batch write reduction ----
    print(f"\n[1] Submitting {args.search_requests} searches (batched writes)…")
    run_search_load(base, args.search_requests, args.concurrency)
    _post(base, "/admin/flush", {})  # ensure everything is persisted
    time.sleep(0.3)

    # ---- read path: latency under load ----
    print(f"[2] Warming cache + measuring {args.suggest_requests} suggestion reads "
          f"(ranking={args.ranking}, concurrency={args.concurrency})…")
    run_suggest_load(base, min(500, args.suggest_requests), args.concurrency, args.ranking)  # warm
    latencies = run_suggest_load(base, args.suggest_requests, args.concurrency, args.ranking)

    m = _get(base, "/metrics")

    print("\n--- Suggestion read latency (client-measured, ms) ---")
    print(f"  requests      : {len(latencies)}")
    print(f"  avg           : {statistics.fmean(latencies):.3f}")
    print(f"  p50           : {pct(latencies, 50):.3f}")
    print(f"  p95           : {pct(latencies, 95):.3f}")
    print(f"  p99           : {pct(latencies, 99):.3f}")
    print(f"  max           : {max(latencies):.3f}")

    print("\n--- Server-side suggestion latency (/metrics) ---")
    for k, v in m["latency"].items():
        print(f"  {k:<12}: {v}")

    print("\n--- Distributed cache ---")
    c = m["cache"]
    print(f"  nodes         : {c['num_nodes']}")
    print(f"  hits/misses   : {c['total_hits']} / {c['total_misses']}")
    print(f"  hit rate      : {c['overall_hit_rate'] * 100:.2f}%")
    for n in c["per_node"]:
        print(f"    {n['node_id']}: size={n['size']} hits={n['hits']} "
              f"misses={n['misses']} hit_rate={n['hit_rate']*100:.1f}%")

    print("\n--- Database (primary store) ---")
    print(f"  reads         : {m['database']['db_reads']}")
    print(f"  writes        : {m['database']['db_writes']}")
    print(f"  rows          : {m['database']['rows']}")

    print("\n--- Batch writes (write reduction) ---")
    b = m["batch_writes"]
    print(f"  raw submissions : {b['raw_submissions']}")
    print(f"  row writes      : {b['row_writes']}")
    print(f"  writes saved    : {b['writes_saved']}")
    print(f"  write reduction : {b['write_reduction'] * 100:.2f}%")
    print(f"  flushes         : {b['flushes']}")

    print("\n" + "=" * 64)
    print("Done. (Copy these numbers into docs/PERFORMANCE.md)")


if __name__ == "__main__":
    main()
