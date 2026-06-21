# Performance Report

This covers the non‑functional requirements: suggestion **read latency
(incl. p95)**, **cache hit rate**, **DB read/write counts**, and **write
reduction** from batching.

## How to reproduce

```bash
# terminal 1
python run.py

# terminal 2
python -m scripts.benchmark --suggest-requests 5000 --search-requests 3000 --concurrency 16
```

The benchmark:
1. fires `--search-requests` searches across a small set of queries, then forces
   a flush → demonstrates **write reduction** (many submissions, few DB writes);
2. warms the cache, then fires `--suggest-requests` suggestion reads over a
   Zipf‑biased prefix mix (so some prefixes are hot) → measures **latency** and
   **cache hit rate**;
3. reads `/metrics` for the server‑side numbers.

You can also read `/metrics` at any time from the UI's metrics panel.

## Results

> Sample run on the development machine (Windows 11, Python 3.12, default
> config: 4 cache nodes × 150 vnodes, TTL 30s, batch size 200, flush interval
> 2s, **dataset = 120,000 queries**, 749,356 Trie nodes). Workload:
> 3,000 searches + 5,000 suggestion reads, concurrency 16. Numbers vary by
> machine — regenerate with the command above.

### Suggestion read latency

| metric | client‑measured (incl. HTTP) | server‑side (`/metrics`) |
|---|---|---|
| samples | 5000 | 5000 |
| p50 | 14.772 ms | **0.017 ms** |
| **p95** | 27.518 ms | **0.021 ms** |
| p99 | 31.362 ms | 0.039 ms |
| avg | 15.510 ms | 0.019 ms |
| max | 71.825 ms | 3.611 ms |

Server‑side latency excludes HTTP/loopback/threading overhead, so it is the
truest measure of the suggestion engine itself: **p95 ≈ 0.02 ms**. Cache hits
are sub‑millisecond; the only multi‑ms sample (max 3.6 ms) is a cold broad‑prefix
miss that then gets cached. The client‑measured figures are dominated by Python's
loopback HTTP round‑trip under 16 concurrent threads, not by the engine.

### Distributed cache

| metric | value |
|---|---|
| nodes | 4 |
| **hit rate** | **99.29 %** |
| hits / misses | 5466 / 39 |
| per‑node spread | cache‑0: 1981 · cache‑1: 1483 · cache‑2: 1088 · cache‑3: 914 |

A high hit rate on a Zipf workload is expected — the head prefixes dominate
traffic and stay cached, which is exactly why p95 stays sub‑millisecond. Keys
are spread across all four nodes by the consistent‑hash ring (the head prefixes
happen to weight cache‑0 a little heavier).

### Database (primary store)

| metric | value |
|---|---|
| DB reads | 8 |
| DB writes | 53 |
| rows | 120000 |

Despite 5,000 reads + 3,000 searches, the DB saw only **8 reads** (cache + Trie
absorb the read traffic) and **53 writes** (everything is batched).

### Write reduction (batching)

| metric | value |
|---|---|
| raw submissions | 3026 |
| row writes performed | 53 |
| writes saved | 2973 |
| **write reduction** | **98.25 %** |
| flushes | 7 |

3,026 `POST /search` calls collapsed into 53 DB row‑writes — a **98 % reduction**
in write pressure, because repeated queries within a flush window aggregate into
a single increment.

## Interpreting the trade‑offs

- **Latency vs. freshness (cache TTL):** higher TTL → higher hit rate / lower
  latency but staler suggestions after a write. We mitigate staleness by
  invalidating a changed query's short prefixes on flush.
- **Throughput vs. durability (batching):** bigger batches / longer intervals →
  fewer DB writes but a larger in‑memory window that is lost on a crash. Tune
  `TYPEAHEAD_BATCH_SIZE` / `TYPEAHEAD_FLUSH_INTERVAL`.
- **Freshness vs. stability (recency):** shorter `half_life` / higher
  `recency_weight` → trendier but jumpier ranking. Decay prevents permanent
  over‑ranking.
- **Memory vs. cold‑prefix latency (Trie precompute depth):** deeper
  precomputation → faster broad‑prefix lookups but more memory.
