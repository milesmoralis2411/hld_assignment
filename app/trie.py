"""Prefix index (Trie) optimised for fast top-K typeahead lookups.

Design notes (important for the viva):
- Every node can answer "top-K completions of this prefix".
- We PRECOMPUTE a candidate pool (top-N by count) only for shallow nodes
  (depth <= precompute_depth). Shallow prefixes (e.g. "a", "ip") fan out to
  huge subtrees, so precomputing makes those lookups O(1) instead of O(subtree).
- Deeper nodes have small subtrees, so we compute their candidates on demand by
  a cheap bounded DFS. This keeps memory bounded (we don't store a list on every
  one of the ~1M nodes) while keeping latency low everywhere.
- Counts live on the terminal node, so reads always see the latest value and
  writes (batch flush) just update that node + the shallow candidate pools.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

Candidate = Tuple[int, str]  # (count, query)


class _Node:
    __slots__ = ("children", "is_word", "count", "word", "candidates")

    def __init__(self) -> None:
        self.children: Dict[str, "_Node"] = {}
        self.is_word: bool = False
        self.count: int = 0
        self.word: Optional[str] = None
        # Precomputed top-N pool, only set for shallow nodes; else None.
        self.candidates: Optional[List[Candidate]] = None


class Trie:
    def __init__(self, max_suggestions: int = 10, candidate_pool: int = 50,
                 precompute_depth: int = 4):
        self.root = _Node()
        self.max_suggestions = max_suggestions
        self.candidate_pool = candidate_pool
        self.precompute_depth = precompute_depth
        self.num_words = 0
        self.num_nodes = 1
        # Bound for on-demand DFS over deep subtrees (safety valve).
        self._dfs_cap = 20_000

    # ---------- build ----------
    def _insert(self, word: str, count: int) -> None:
        node = self.root
        for ch in word:
            nxt = node.children.get(ch)
            if nxt is None:
                nxt = _Node()
                node.children[ch] = nxt
                self.num_nodes += 1
            node = nxt
        if not node.is_word:
            self.num_words += 1
        node.is_word = True
        node.count = count
        node.word = word

    def build(self, items: List[Candidate]) -> None:
        """Bulk load (query, count) rows then precompute candidate pools."""
        for word, count in items:
            if word:
                self._insert(word, count)
        self._compute(self.root, 0)

    def _compute(self, node: _Node, depth: int) -> List[Candidate]:
        """Post-order: build each node's top-N pool by merging children.

        Returns the node's top-N pool so the parent can merge it. We only RETAIN
        the pool on the node itself for shallow depths to bound memory.
        """
        merged: List[Candidate] = []
        for child in node.children.values():
            merged.extend(self._compute(child, depth + 1))
        if node.is_word:
            merged.append((node.count, node.word))  # type: ignore[arg-type]
        merged.sort(key=lambda c: (-c[0], c[1]))
        if len(merged) > self.candidate_pool:
            merged = merged[: self.candidate_pool]
        node.candidates = merged if depth <= self.precompute_depth else None
        return merged

    # ---------- read ----------
    def _find(self, prefix: str) -> Optional[_Node]:
        node = self.root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return None
        return node

    def _collect(self, node: _Node, out: List[Candidate]) -> None:
        if node.is_word:
            out.append((node.count, node.word))  # type: ignore[arg-type]
        for child in node.children.values():
            if len(out) >= self._dfs_cap:
                return
            self._collect(child, out)

    def candidates_for(self, prefix: str) -> List[Candidate]:
        """Top-N candidate pool for a prefix (count-sorted). Empty if no match."""
        node = self._find(prefix)
        if node is None:
            return []
        if node.candidates is not None:        # shallow: precomputed
            return node.candidates
        pool: List[Candidate] = []             # deep: small subtree, compute now
        self._collect(node, pool)
        pool.sort(key=lambda c: (-c[0], c[1]))
        return pool[: self.candidate_pool]

    def suggest(self, prefix: str) -> List[Candidate]:
        """Basic ranking: top-K matching completions by overall count."""
        return self.candidates_for(prefix)[: self.max_suggestions]

    # ---------- write (called on batch flush) ----------
    def upsert(self, word: str, new_count: int) -> None:
        """Apply a count update: create the word if new, refresh shallow pools."""
        node = self.root
        depth = 0
        self._pool_upsert(node, new_count, word)  # root pool (empty prefix)
        for ch in word:
            nxt = node.children.get(ch)
            if nxt is None:
                nxt = _Node()
                node.children[ch] = nxt
                self.num_nodes += 1
            node = nxt
            depth += 1
            if node.candidates is not None:
                self._pool_upsert(node, new_count, word)
        if not node.is_word:
            self.num_words += 1
        node.is_word = True
        node.count = new_count
        node.word = word

    def _pool_upsert(self, node: _Node, count: int, word: str) -> None:
        pool = node.candidates
        if pool is None:
            return
        # drop any stale entry for this word, then insert fresh and re-trim
        for i, (_, w) in enumerate(pool):
            if w == word:
                pool.pop(i)
                break
        pool.append((count, word))
        pool.sort(key=lambda c: (-c[0], c[1]))
        if len(pool) > self.candidate_pool:
            del pool[self.candidate_pool:]

    def get_count(self, word: str) -> int:
        node = self._find(word)
        return node.count if node and node.is_word else 0
