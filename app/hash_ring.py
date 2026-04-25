import hashlib
import bisect
from typing import Optional


class HashRing:
    """Consistent hashing ring with virtual nodes."""

    def __init__(self, virtual_nodes: int = 150):
        self.virtual_nodes = virtual_nodes
        self.ring: dict[int, str] = {}
        self.sorted_keys: list[int] = []
        self.nodes: set[str] = set()

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: str) -> None:
        self.nodes.add(node)
        for i in range(self.virtual_nodes):
            vnode_key = self._hash(f"{node}#vn{i}")
            self.ring[vnode_key] = node
            bisect.insort(self.sorted_keys, vnode_key)

    def remove_node(self, node: str) -> None:
        self.nodes.discard(node)
        for i in range(self.virtual_nodes):
            vnode_key = self._hash(f"{node}#vn{i}")
            self.ring.pop(vnode_key, None)
            idx = bisect.bisect_left(self.sorted_keys, vnode_key)
            if idx < len(self.sorted_keys) and self.sorted_keys[idx] == vnode_key:
                self.sorted_keys.pop(idx)

    def get_node(self, key: str) -> Optional[str]:
        if not self.ring:
            return None
        h = self._hash(key)
        idx = bisect.bisect(self.sorted_keys, h) % len(self.sorted_keys)
        return self.ring[self.sorted_keys[idx]]

    def get_nodes(self, key: str, n: int) -> list[str]:
        """Return n distinct physical nodes starting from successor of key."""
        if not self.ring or n == 0:
            return []
        h = self._hash(key)
        idx = bisect.bisect(self.sorted_keys, h) % len(self.sorted_keys)
        seen: set[str] = set()
        result: list[str] = []
        for i in range(len(self.sorted_keys)):
            node = self.ring[self.sorted_keys[(idx + i) % len(self.sorted_keys)]]
            if node not in seen:
                seen.add(node)
                result.append(node)
            if len(result) == n:
                break
        return result