from typing import Optional


class VectorClock:
    def __init__(self, clock: Optional[dict[str, int]] = None):
        self.clock: dict[str, int] = clock or {}

    def increment(self, node_id: str) -> "VectorClock":
        new_clock = dict(self.clock)
        new_clock[node_id] = new_clock.get(node_id, 0) + 1
        return VectorClock(new_clock)

    def merge(self, other: "VectorClock") -> "VectorClock":
        merged = dict(self.clock)
        for k, v in other.clock.items():
            merged[k] = max(merged.get(k, 0), v)
        return VectorClock(merged)

    def is_newer_than(self, other: "VectorClock") -> bool:
        """True if self dominates other (all values >=, at least one >)."""
        all_ge = all(self.clock.get(k, 0) >= v for k, v in other.clock.items())
        any_gt = any(self.clock.get(k, 0) > v for k, v in other.clock.items()) or \
                 any(k not in other.clock for k in self.clock)
        return all_ge and any_gt

    def to_dict(self) -> dict:
        return self.clock

    @classmethod
    def from_dict(cls, d: dict) -> "VectorClock":
        return cls(d)