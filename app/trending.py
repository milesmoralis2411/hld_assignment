"""Recency-aware trending tracker (the +20% "enhanced ranking" part).

Each query carries a *decaying* activity score. On every search we do:

    score = score * 0.5 ** (dt / half_life) + 1

This is an exponentially time-decayed counter. Key properties:
- A burst of recent searches pushes a query up immediately.
- The boost FADES on its own (half-life), so a query that was popular for a
  short period does NOT stay over-ranked forever - it decays back down. This is
  exactly the "avoid permanently over-ranking" requirement.
- It is O(1) per update and needs no background sweeping or sliding-window
  buffers (we lazily decay on read/write using timestamps).

The enhanced suggestion ranking blends durable popularity (count, from the
store/Trie) with this recency score. The count is log-compressed so the recency
term stays meaningful regardless of the dataset's absolute count scale:

    final = log1p(count) + recency_weight * recent_score(query)

Trade-offs are documented in docs/PERFORMANCE.md and the README.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Dict, List, Tuple


class TrendingTracker:
    def __init__(self, half_life_seconds: float, trending_size: int):
        self.half_life = half_life_seconds
        self.trending_size = trending_size
        self._scores: Dict[str, float] = {}
        self._last: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _decay_factor(self, dt: float) -> float:
        if dt <= 0:
            return 1.0
        return 0.5 ** (dt / self.half_life)

    def record(self, query: str, now: float | None = None) -> None:
        """Register one search for ``query`` (called immediately on submit)."""
        now = now or time.time()
        with self._lock:
            last = self._last.get(query, now)
            decayed = self._scores.get(query, 0.0) * self._decay_factor(now - last)
            self._scores[query] = decayed + 1.0
            self._last[query] = now

    def score(self, query: str, now: float | None = None) -> float:
        """Current decayed recency score for one query."""
        now = now or time.time()
        s = self._scores.get(query)
        if s is None:
            return 0.0
        return s * self._decay_factor(now - self._last.get(query, now))

    def top(self, limit: int | None = None, now: float | None = None) -> List[Tuple[str, float]]:
        """Most-trending queries right now (decayed scores, descending)."""
        now = now or time.time()
        limit = limit or self.trending_size
        with self._lock:
            scored = [
                (q, s * self._decay_factor(now - self._last.get(q, now)))
                for q, s in self._scores.items()
            ]
        scored = [(q, s) for q, s in scored if s > 1e-6]
        scored.sort(key=lambda x: (-x[1], x[0]))
        return scored[:limit]

    def matching(self, prefix: str, now: float | None = None) -> List[Tuple[str, float]]:
        """Trending queries that start with ``prefix`` (for enhanced ranking)."""
        now = now or time.time()
        with self._lock:
            items = list(self._scores.items())
            last = dict(self._last)
        out = []
        for q, s in items:
            if q.startswith(prefix):
                ds = s * self._decay_factor(now - last.get(q, now))
                if ds > 1e-6:
                    out.append((q, ds))
        return out

    def stats(self) -> dict:
        return {"tracked_queries": len(self._scores),
                "half_life_seconds": self.half_life}
