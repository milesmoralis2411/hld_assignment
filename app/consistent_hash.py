"""Consistent hashing ring.

Used to decide which logical cache node "owns" a given prefix key. Virtual
nodes (replicas) are placed on the ring so keys are spread evenly and so that
adding/removing a node only remaps a small fraction of keys.
"""
from __future__ import annotations

import bisect
import hashlib
from typing import Dict, List, Optional


class ConsistentHashRing:
    def __init__(self, nodes: Optional[List[str]] = None, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self._ring: Dict[int, str] = {}       # hash position -> node id
        self._sorted_keys: List[int] = []     # sorted hash positions
        self.nodes: List[str] = []
        for node in nodes or []:
            self.add_node(node)

    @staticmethod
    def _hash(key: str) -> int:
        return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)

    def add_node(self, node: str) -> None:
        if node in self.nodes:
            return
        self.nodes.append(node)
        for i in range(self.virtual_nodes):
            h = self._hash(f"{node}#{i}")
            self._ring[h] = node
            bisect.insort(self._sorted_keys, h)

    def remove_node(self, node: str) -> None:
        if node not in self.nodes:
            return
        self.nodes.remove(node)
        for i in range(self.virtual_nodes):
            h = self._hash(f"{node}#{i}")
            self._ring.pop(h, None)
            idx = bisect.bisect_left(self._sorted_keys, h)
            if idx < len(self._sorted_keys) and self._sorted_keys[idx] == h:
                self._sorted_keys.pop(idx)

    def get_node(self, key: str) -> Optional[str]:
        """Return the node id that owns ``key`` (first node clockwise)."""
        if not self._ring:
            return None
        h = self._hash(key)
        idx = bisect.bisect(self._sorted_keys, h) % len(self._sorted_keys)
        return self._ring[self._sorted_keys[idx]]

    def debug(self, key: str) -> dict:
        """Explain how ``key`` is routed - used by GET /cache/debug."""
        h = self._hash(key)
        owner = self.get_node(key)
        idx = bisect.bisect(self._sorted_keys, h) % len(self._sorted_keys) if self._sorted_keys else 0
        vnode_pos = self._sorted_keys[idx] if self._sorted_keys else None
        return {
            "key": key,
            "key_hash": h,
            "owner_node": owner,
            "matched_vnode_hash": vnode_pos,
            "total_nodes": len(self.nodes),
            "virtual_nodes_per_node": self.virtual_nodes,
            "total_points_on_ring": len(self._sorted_keys),
        }
