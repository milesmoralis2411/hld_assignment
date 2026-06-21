"""Lightweight latency metrics for the suggestions API.

Keeps a rolling window of recent request latencies so we can report p50/p95/p99
(the non-functional requirement asks specifically for p95). Cache hit-rate and
DB read/write counts come from their own components and are stitched together in
the /metrics endpoint.
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Deque


class Metrics:
    def __init__(self, window: int = 5000):
        self._lat: Deque[float] = deque(maxlen=window)
        self._lock = threading.Lock()
        self.suggest_requests = 0
        self.search_requests = 0

    def record_suggest_latency(self, ms: float) -> None:
        with self._lock:
            self._lat.append(ms)
            self.suggest_requests += 1

    def record_search(self) -> None:
        with self._lock:
            self.search_requests += 1

    @staticmethod
    def _pct(values, p: float) -> float:
        if not values:
            return 0.0
        k = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
        return values[k]

    def latency_stats(self) -> dict:
        with self._lock:
            data = sorted(self._lat)
        if not data:
            return {"samples": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0,
                    "avg_ms": 0, "max_ms": 0}
        return {
            "samples": len(data),
            "p50_ms": round(self._pct(data, 50), 3),
            "p95_ms": round(self._pct(data, 95), 3),
            "p99_ms": round(self._pct(data, 99), 3),
            "avg_ms": round(sum(data) / len(data), 3),
            "max_ms": round(data[-1], 3),
        }
