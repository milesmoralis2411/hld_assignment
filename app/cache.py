"""A single logical cache node: in-memory LRU with per-entry TTL.

Several of these make up the distributed cache (see cache_cluster.py). Each one
is independent, with its own capacity, eviction and hit/miss counters - exactly
how an individual Redis/Memcached shard would behave.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Optional


class CacheNode:
    def __init__(self, node_id: str, capacity: int, ttl_seconds: float):
        self.id = node_id
        self.capacity = capacity
        self.ttl = ttl_seconds
        self._data: "OrderedDict[str, tuple[Any, float]]" = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        entry = self._data.get(key)
        if entry is not None:
            value, expires_at = entry
            if expires_at >= now:
                self._data.move_to_end(key)  # mark as recently used
                self.hits += 1
                return value
            # expired
            del self._data[key]
            self.expirations += 1
        self.misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        self._data[key] = (value, time.time() + self.ttl)
        self._data.move_to_end(key)
        while len(self._data) > self.capacity:
            self._data.popitem(last=False)  # evict least-recently-used
            self.evictions += 1

    def contains_fresh(self, key: str) -> bool:
        entry = self._data.get(key)
        return entry is not None and entry[1] >= time.time()

    def invalidate(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    def clear(self) -> None:
        self._data.clear()

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "node_id": self.id,
            "size": len(self._data),
            "capacity": self.capacity,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
        }
