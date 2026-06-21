"""Primary data store (SQLite) for query -> count.

This is the durable source of truth. The Trie is an in-memory index built from
it; the cache sits in front of it. Every read/write is counted so we can report
DB read/write reduction (the whole point of batching + caching).

SQLite is used because it needs zero setup ("easy to run locally") yet is a real
disk-backed relational store with transactions. The access pattern (bulk load,
single-row upserts in a transaction on flush) maps cleanly onto any RDBMS.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Dict, List, Tuple


class PrimaryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")  # durability + concurrency
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queries (
                query TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                last_searched REAL DEFAULT 0
            )
            """
        )
        self._conn.commit()
        self.reads = 0
        self.writes = 0

    def is_empty(self) -> bool:
        cur = self._conn.execute("SELECT 1 FROM queries LIMIT 1")
        return cur.fetchone() is None

    def count_rows(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM queries")
        return cur.fetchone()[0]

    def bulk_load(self, rows: List[Tuple[str, int]]) -> int:
        """Initial dataset ingestion (one bulk write, not counted per-row)."""
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO queries (query, count) VALUES (?, ?)", rows
            )
            self._conn.commit()
        return len(rows)

    def load_all(self) -> List[Tuple[str, int]]:
        """Read the whole table to build the in-memory Trie (one big read)."""
        with self._lock:
            self.reads += 1
            cur = self._conn.execute("SELECT query, count FROM queries")
            return cur.fetchall()

    def get(self, query: str) -> int:
        with self._lock:
            self.reads += 1
            cur = self._conn.execute(
                "SELECT count FROM queries WHERE query = ?", (query,)
            )
            row = cur.fetchone()
            return row[0] if row else 0

    def apply_increments(self, increments: Dict[str, int], now: float) -> List[Tuple[str, int]]:
        """Apply a batch of aggregated increments in ONE transaction.

        Returns the list of (query, new_count) so callers can refresh the Trie
        and cache. ``writes`` is incremented once per affected row (the real
        number of DB row-writes), which is what we compare against the number of
        raw submissions to prove write reduction.
        """
        results: List[Tuple[str, int]] = []
        with self._lock:
            cur = self._conn.cursor()
            for query, delta in increments.items():
                cur.execute(
                    """
                    INSERT INTO queries (query, count, last_searched)
                    VALUES (?, ?, ?)
                    ON CONFLICT(query) DO UPDATE SET
                        count = count + excluded.count,
                        last_searched = excluded.last_searched
                    """,
                    (query, delta, now),
                )
                results.append((query, delta))
            self._conn.commit()
            self.writes += len(increments)
            # read back the new totals (single batched read)
            self.reads += 1
            qmarks = ",".join("?" for _ in increments)
            cur.execute(
                f"SELECT query, count FROM queries WHERE query IN ({qmarks})",
                list(increments.keys()),
            )
            return cur.fetchall()

    def top_overall(self, limit: int) -> List[Tuple[str, int]]:
        with self._lock:
            self.reads += 1
            cur = self._conn.execute(
                "SELECT query, count FROM queries ORDER BY count DESC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def stats(self) -> dict:
        return {"db_reads": self.reads, "db_writes": self.writes,
                "rows": self.count_rows()}

    def close(self) -> None:
        self._conn.close()
