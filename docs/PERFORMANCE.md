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
> 2s, **dataset = 333,333 real keywords** (Google Web Trillion Word Corpus),
> 805,917 Trie nodes). Workload: 3,000 searches + 5,000 suggestion reads,
> concurrency 16. Numbers vary by machine — regenerate with the command above.

### Suggestion read latency

| metric | client‑measured (incl. HTTP) | server‑side (`/metrics`) |
|---|---|---|
| samples | 5000 | 5000 |
| p50 | 32.897 ms | **0.036 ms** |
| **p95** | 37.426 ms | **0.057 ms** |
| p99 | 41.668 ms | 0.111 ms |
| avg | 33.018 ms | 0.036 ms |
| max | 136.425 ms | 0.545 ms |

Server‑side latency excludes HTTP/loopback/threading overhead, so it is the
truest measure of the suggestion engine itself: **p95 ≈ 0.06 ms** even over a
333k‑keyword index. Cache hits are sub‑millisecond; misses pay the Trie lookup +
ranking (max 0.55 ms). The client‑measured figures are dominated by Python's
loopback HTTP round‑trip under 16 concurrent threads, not by the engine.

### Distributed cache

| metric | value |
|---|---|
| nodes | 4 |
| **hit rate** | **99.29 %** |
| hits / misses | 5464 / 39 |
| per‑node spread | cache‑0: 1981 · cache‑1: 1483 · cache‑2: 1088 · cache‑3: 912 |

A high hit rate on a Zipf workload is expected — the head prefixes dominate
traffic and stay cached, which is exactly why p95 stays sub‑millisecond. Keys
are spread across all four nodes by the consistent‑hash ring (the head prefixes
happen to weight cache‑0 a little heavier).

### Database (primary store)

| metric | value |
|---|---|
| DB reads | 14 |
| DB writes | 121 |
| rows | 333,343 |

Despite 5,000 reads + 3,000 searches, the DB saw only **14 reads** (cache + Trie
absorb the read traffic) and **121 writes** (everything is batched). Rows grew
past 333,333 because the benchmark submits a few queries not already in the set.

### Write reduction (batching)

| metric | value |
|---|---|
| raw submissions | 3015 |
| row writes performed | 121 |
| writes saved | 2894 |
| **write reduction** | **95.99 %** |
| flushes | 13 |

3,015 `POST /search` calls collapsed into 121 DB row‑writes — a **96 % reduction**
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
