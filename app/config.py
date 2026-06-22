"""Central configuration for the typeahead system.

All tunables are exposed here (and overridable via environment variables) so
that design trade-offs can be demonstrated easily during a demo / viva.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _get_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


@dataclass
class Config:
    # ---- Storage ----
    db_path: str = os.getenv("TYPEAHEAD_DB", "data/typeahead.db")
    dataset_path: str = os.getenv("TYPEAHEAD_DATASET", "data/queries.csv")
    # Real open dataset: Google Web Trillion Word Corpus unigrams (Peter Norvig).
    # Real keywords with real frequency counts; fetched automatically on first run.
    dataset_url: str = os.getenv(
        "TYPEAHEAD_DATASET_URL", "https://norvig.com/ngrams/count_1w.txt"
    )
    # Cap rows loaded from the real dataset (0 = load all 333,333).
    dataset_limit: int = _get_int("TYPEAHEAD_DATASET_LIMIT", 0)
    # Size used only by the offline synthetic fallback generator.
    dataset_size: int = _get_int("TYPEAHEAD_DATASET_SIZE", 120_000)

    # ---- Suggestions ----
    max_suggestions: int = _get_int("TYPEAHEAD_MAX_SUGGESTIONS", 10)
    # We precompute a larger candidate pool so recency re-ranking has room to work.
    candidate_pool: int = _get_int("TYPEAHEAD_CANDIDATE_POOL", 50)
    # Precompute candidate lists only for shallow prefixes (broad fan-out).
    # Deeper prefixes have small subtrees and are computed on demand. This keeps
    # memory bounded while keeping the expensive broad-prefix lookups O(1).
    precompute_depth: int = _get_int("TYPEAHEAD_PRECOMPUTE_DEPTH", 4)

    # ---- Distributed cache ----
    num_cache_nodes: int = _get_int("TYPEAHEAD_CACHE_NODES", 4)
    cache_capacity_per_node: int = _get_int("TYPEAHEAD_CACHE_CAPACITY", 5_000)
    cache_ttl_seconds: float = _get_float("TYPEAHEAD_CACHE_TTL", 30.0)
    virtual_nodes: int = _get_int("TYPEAHEAD_VNODES", 150)
    # When a write touches a query we invalidate cache entries for its prefixes
    # up to this length (bounded work); the rest expire via TTL.
    invalidate_prefix_len: int = _get_int("TYPEAHEAD_INVALIDATE_PREFIX_LEN", 8)

    # ---- Batch writes ----
    batch_size: int = _get_int("TYPEAHEAD_BATCH_SIZE", 200)
    flush_interval_seconds: float = _get_float("TYPEAHEAD_FLUSH_INTERVAL", 2.0)

    # ---- Trending / recency ----
    # Half-life of the decaying "recent activity" counter, in seconds.
    recency_half_life_seconds: float = _get_float("TYPEAHEAD_RECENCY_HALFLIFE", 300.0)
    # Weight applied to recent activity when ranking == "recent". Blended against
    # log1p(count), so this is on a log scale (a few searches can out-rank a
    # higher-count neighbour, then decays back).
    recency_weight: float = _get_float("TYPEAHEAD_RECENCY_WEIGHT", 6.0)
    trending_size: int = _get_int("TYPEAHEAD_TRENDING_SIZE", 10)

    frontend_dir: str = os.getenv("TYPEAHEAD_FRONTEND", "frontend")


config = Config()
