"""Batch writer: absorbs search submissions and reduces DB write pressure.

POST /search does NOT write to the primary store synchronously. Instead each
submission is appended to an in-memory buffer. A background flusher drains the
buffer when either:
  * the buffer reaches ``batch_size``, or
  * ``flush_interval`` seconds have elapsed.

Before writing, repeated queries in the buffer are AGGREGATED into a single
increment per query, so 50 searches for "iphone" become one DB row-write of
+50 instead of 50 writes. This is what produces the write-reduction numbers in
the performance report.

Failure trade-off (discussed in README): the buffer is in-memory, so a crash
before a flush loses the un-flushed submissions. Mitigations would be a durable
append-only log / persistent queue (e.g. Kafka, or fsync'd WAL) at the cost of
latency. We deliberately favour low write-latency for this assignment and on
graceful shutdown we flush the remaining buffer.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, List, Tuple


class BatchWriter:
    def __init__(self, batch_size: int, flush_interval: float,
                 flush_fn: Callable[[Dict[str, int]], List[Tuple[str, int]]]):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._flush_fn = flush_fn
        self._buffer: Deque[str] = deque()
        self._lock = threading.Lock()
        # metrics
        self.total_submissions = 0     # raw POST /search count
        self.total_flushes = 0
        self.total_rows_written = 0    # aggregated row-writes actually performed
        self.last_flush_ts = time.time()

    def add(self, query: str) -> None:
        with self._lock:
            self._buffer.append(query)
            self.total_submissions += 1

    def buffer_size(self) -> int:
        with self._lock:
            return len(self._buffer)

    def should_flush(self) -> bool:
        with self._lock:
            if not self._buffer:
                return False
            if len(self._buffer) >= self.batch_size:
                return True
        return (time.time() - self.last_flush_ts) >= self.flush_interval

    def _drain_and_aggregate(self) -> Dict[str, int]:
        with self._lock:
            if not self._buffer:
                return {}
            pending = list(self._buffer)
            self._buffer.clear()
        agg: Dict[str, int] = {}
        for q in pending:
            agg[q] = agg.get(q, 0) + 1
        return agg

    def flush(self) -> List[Tuple[str, int]]:
        """Drain, aggregate, persist. Returns [(query, new_count), ...]."""
        agg = self._drain_and_aggregate()
        self.last_flush_ts = time.time()
        if not agg:
            return []
        updated = self._flush_fn(agg)
        self.total_flushes += 1
        self.total_rows_written += len(agg)
        return updated

    def stats(self) -> dict:
        saved = self.total_submissions - self.total_rows_written
        reduction = (saved / self.total_submissions) if self.total_submissions else 0.0
        return {
            "raw_submissions": self.total_submissions,
            "row_writes": self.total_rows_written,
            "writes_saved": saved,
            "write_reduction": round(reduction, 4),
            "flushes": self.total_flushes,
            "pending_in_buffer": self.buffer_size(),
            "batch_size": self.batch_size,
            "flush_interval_seconds": self.flush_interval,
        }
