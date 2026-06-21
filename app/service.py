"""SuggestionService - wires every component together.

Read path  (GET /suggest):  cache  ->  Trie  ->  (rank)  ->  cache.set
Write path (POST /search):  trending.record (instant)  ->  batch buffer
Flush path (background):     aggregate  ->  store  ->  Trie  ->  cache invalidate

This is the single place that knows about all the moving parts, which keeps the
HTTP layer (main.py) thin.
"""
from __future__ import annotations

import time
from typing import Dict, List, Tuple

from .batch_writer import BatchWriter
from .cache_cluster import CacheCluster
from .config import Config
from .metrics import Metrics
from .store import PrimaryStore
from .trending import TrendingTracker
from .trie import Trie


class SuggestionService:
    def __init__(self, config: Config, store: PrimaryStore, trie: Trie,
                 cache: CacheCluster, trending: TrendingTracker, metrics: Metrics):
        self.config = config
        self.store = store
        self.trie = trie
        self.cache = cache
        self.trending = trending
        self.metrics = metrics
        # batch writer flushes through self._flush_increments
        self.batch = BatchWriter(
            batch_size=config.batch_size,
            flush_interval=config.flush_interval_seconds,
            flush_fn=self._flush_increments,
        )

    # ---------------- read path ----------------
    @staticmethod
    def normalize(text: str) -> str:
        return (text or "").strip().lower()

    def suggest(self, prefix: str, ranking: str = "count") -> dict:
        """Return up to max_suggestions completions for ``prefix``.

        ranking == "count"  -> basic: order by overall search count.
        ranking == "recent" -> enhanced: blend count with decaying recency.
        """
        start = time.perf_counter()
        prefix = self.normalize(prefix)
        ranking = ranking if ranking in ("count", "recent") else "count"

        if not prefix:
            self.metrics.record_suggest_latency((time.perf_counter() - start) * 1000)
            return {"prefix": prefix, "ranking": ranking, "source": "empty",
                    "suggestions": []}

        cache_key = f"{ranking}:{prefix}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.metrics.record_suggest_latency((time.perf_counter() - start) * 1000)
            return {"prefix": prefix, "ranking": ranking, "source": "cache",
                    "suggestions": cached}

        # cache miss -> consult the in-memory index (backed by primary store)
        candidates = self.trie.candidates_for(prefix)

        if ranking == "recent":
            suggestions = self._rank_recent(prefix, candidates)
        else:
            suggestions = [
                {"query": q, "count": c}
                for c, q in candidates[: self.config.max_suggestions]
            ]

        self.cache.set(cache_key, suggestions)
        self.metrics.record_suggest_latency((time.perf_counter() - start) * 1000)
        return {"prefix": prefix, "ranking": ranking, "source": "store",
                "suggestions": suggestions}

    def _rank_recent(self, prefix: str, candidates: List[Tuple[int, str]]) -> List[dict]:
        now = time.time()
        w = self.config.recency_weight
        # candidate set = popular completions + currently-trending completions
        pool: Dict[str, int] = {q: c for c, q in candidates}
        for q, _s in self.trending.matching(prefix, now):
            pool.setdefault(q, self.trie.get_count(q))
        scored = []
        for q, count in pool.items():
            rs = self.trending.score(q, now)
            final = count + w * rs
            scored.append((final, count, rs, q))
        scored.sort(key=lambda x: (-x[0], x[3]))
        return [
            {"query": q, "count": count, "recency_score": round(rs, 3),
             "rank_score": round(final, 2)}
            for final, count, rs, q in scored[: self.config.max_suggestions]
        ]

    # ---------------- write path ----------------
    def submit_search(self, query: str) -> dict:
        """Dummy search endpoint: record recency now, buffer the count write."""
        q = self.normalize(query)
        self.metrics.record_search()
        if q:
            self.trending.record(q)     # recency reflects immediately
            self.batch.add(q)           # count write is batched
        return {"message": "Searched", "query": q}

    def _flush_increments(self, increments: Dict[str, int]) -> List[Tuple[str, int]]:
        """Called by BatchWriter: persist aggregated counts, refresh index+cache."""
        now = time.time()
        updated = self.store.apply_increments(increments, now)
        for query, new_count in updated:
            self.trie.upsert(query, new_count)
            self._invalidate_prefixes(query)
        return updated

    def _invalidate_prefixes(self, query: str) -> None:
        """Invalidate cached suggestion entries for a changed query's prefixes."""
        upto = min(len(query), self.config.invalidate_prefix_len)
        for i in range(1, upto + 1):
            p = query[:i]
            self.cache.invalidate(f"count:{p}")
            self.cache.invalidate(f"recent:{p}")

    def flush_now(self) -> List[Tuple[str, int]]:
        return self.batch.flush()

    # ---------------- trending ----------------
    def trending_now(self) -> dict:
        items = self.trending.top(self.config.trending_size)
        return {
            "trending": [
                {"query": q, "recency_score": round(s, 3),
                 "count": self.trie.get_count(q)}
                for q, s in items
            ]
        }

    # ---------------- metrics ----------------
    def metrics_snapshot(self) -> dict:
        return {
            "latency": self.metrics.latency_stats(),
            "cache": self.cache.stats(),
            "database": self.store.stats(),
            "batch_writes": self.batch.stats(),
            "trending": self.trending.stats(),
            "index": {"words": self.trie.num_words, "nodes": self.trie.num_nodes},
            "requests": {
                "suggest": self.metrics.suggest_requests,
                "search": self.metrics.search_requests,
            },
        }
