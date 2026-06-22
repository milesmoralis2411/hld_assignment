"""FastAPI application: HTTP layer for the Search Typeahead System.

Endpoints (see README for full docs):
  GET  /suggest?q=<prefix>&ranking=count|recent   -> typeahead suggestions
  POST /search           {"query": "..."}          -> dummy search + buffer write
  GET  /trending                                    -> recency-aware trending
  GET  /cache/debug?prefix=<p>                       -> consistent-hash routing
  GET  /metrics                                      -> latency / cache / db / batch
  POST /admin/flush                                  -> force a batch flush (demo)
  GET  /health
  GET  /                                             -> frontend UI
"""
from __future__ import annotations

import asyncio
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .cache_cluster import CacheCluster
from .config import config
from .loader import ensure_dataset, load_into_store
from .metrics import Metrics
from .service import SuggestionService
from .store import PrimaryStore
from .trending import TrendingTracker
from .trie import Trie


class SearchBody(BaseModel):
    query: str


async def _flush_loop(service: SuggestionService, stop: asyncio.Event) -> None:
    """Background task: periodically flush the batch buffer."""
    interval = max(0.2, service.config.flush_interval_seconds / 4)
    while not stop.is_set():
        try:
            if service.batch.should_flush():
                service.flush_now()
        except Exception as exc:  # never let the loop die silently
            print(f"[flush_loop] error: {exc}")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    # 1) dataset + primary store
    ensure_dataset(config.dataset_path, config.dataset_url,
                   config.dataset_limit, config.dataset_size)
    store = PrimaryStore(config.db_path)
    if store.is_empty():
        n = load_into_store(store, config.dataset_path)
        print(f"[startup] loaded {n} queries into primary store")
    else:
        print(f"[startup] primary store already has {store.count_rows()} rows")

    # 2) build in-memory index from the store
    rows = store.load_all()
    trie = Trie(config.max_suggestions, config.candidate_pool, config.precompute_depth)
    trie.build(rows)
    print(f"[startup] trie built: {trie.num_words} words, {trie.num_nodes} nodes")

    # 3) distributed cache + trending + metrics + service
    cache = CacheCluster(config.num_cache_nodes, config.cache_capacity_per_node,
                         config.cache_ttl_seconds, config.virtual_nodes)
    trending = TrendingTracker(config.recency_half_life_seconds, config.trending_size)
    metrics = Metrics()
    service = SuggestionService(config, store, trie, cache, trending, metrics)
    app.state.service = service

    # 4) background batch flusher
    stop = asyncio.Event()
    task = asyncio.create_task(_flush_loop(service, stop))
    print(f"[startup] ready in {time.time() - t0:.2f}s")

    try:
        yield
    finally:
        stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        service.flush_now()  # flush remaining buffer on graceful shutdown
        store.close()
        print("[shutdown] flushed buffer and closed store")


app = FastAPI(title="Search Typeahead System", version="1.0.0", lifespan=lifespan)


def svc() -> SuggestionService:
    return app.state.service


@app.get("/suggest")
async def suggest(q: str = Query("", description="prefix the user has typed"),
                  ranking: str = Query("count", pattern="^(count|recent)$")):
    return svc().suggest(q, ranking)


@app.post("/search")
async def search(body: SearchBody):
    return svc().submit_search(body.query)


@app.get("/trending")
async def trending():
    return svc().trending_now()


@app.get("/cache/debug")
async def cache_debug(prefix: str = Query(..., description="prefix key to route"),
                      ranking: str = Query("count", pattern="^(count|recent)$")):
    s = svc()
    key = f"{ranking}:{s.normalize(prefix)}"
    return s.cache.debug(key)


@app.get("/metrics")
async def metrics():
    return svc().metrics_snapshot()


@app.post("/admin/flush")
async def admin_flush():
    updated = svc().flush_now()
    return {"flushed": len(updated), "updated": updated[:20]}


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---- frontend (served last so API routes win) ----
_FRONTEND = os.path.abspath(config.frontend_dir)
if os.path.isdir(_FRONTEND):
    app.mount("/static", StaticFiles(directory=_FRONTEND), name="static")

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(_FRONTEND, "index.html"))
else:
    @app.get("/")
    async def index_missing():
        return JSONResponse({"message": "frontend not found", "api_docs": "/docs"})
