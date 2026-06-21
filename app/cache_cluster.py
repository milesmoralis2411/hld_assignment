"""Distributed cache made of several logical CacheNodes.

A consistent-hash ring decides which node owns each prefix key. This models a
sharded cache cluster (e.g. multiple Redis nodes) running inside one process so
the whole thing stays "easy to run locally" while still demonstrating real
distribution behaviour: even key spread, per-shard stats, and minimal remapping
when the topology changes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .cache import CacheNode
from .consistent_hash import ConsistentHashRing


class CacheCluster:
    def __init__(self, num_nodes: int, capacity_per_node: int,
                 ttl_seconds: float, virtual_nodes: int):
        self.nodes: Dict[str, CacheNode] = {
            f"cache-{i}": CacheNode(f"cache-{i}", capacity_per_node, ttl_seconds)
            for i in range(num_nodes)
        }
        self.ring = ConsistentHashRing(list(self.nodes.keys()), virtual_nodes)

    def _node_for(self, key: str) -> CacheNode:
        return self.nodes[self.ring.get_node(key)]

    def get(self, key: str) -> Optional[Any]:
        return self._node_for(key).get(key)

    def set(self, key: str, value: Any) -> None:
        self._node_for(key).set(key, value)

    def invalidate(self, key: str) -> bool:
        return self._node_for(key).invalidate(key)

    def add_node(self, node_id: str, capacity: int, ttl: float) -> None:
        self.nodes[node_id] = CacheNode(node_id, capacity, ttl)
        self.ring.add_node(node_id)

    def debug(self, key: str) -> dict:
        """Show how a key is routed and whether it is currently a hit/miss."""
        routing = self.ring.debug(key)
        owner = routing["owner_node"]
        node = self.nodes.get(owner)
        is_hit = node.contains_fresh(key) if node else False
        return {
            **routing,
            "cache_status": "HIT" if is_hit else "MISS",
            "owner_node_size": len(node._data) if node else 0,
        }

    def key_distribution(self, sample_keys: List[str]) -> Dict[str, int]:
        """How many of the sample keys land on each node (load-balance proof)."""
        dist = {nid: 0 for nid in self.nodes}
        for k in sample_keys:
            dist[self.ring.get_node(k)] += 1
        return dist

    def stats(self) -> dict:
        per_node = [n.stats() for n in self.nodes.values()]
        hits = sum(n["hits"] for n in per_node)
        misses = sum(n["misses"] for n in per_node)
        total = hits + misses
        return {
            "num_nodes": len(self.nodes),
            "total_hits": hits,
            "total_misses": misses,
            "overall_hit_rate": round(hits / total, 4) if total else 0.0,
            "per_node": per_node,
        }
