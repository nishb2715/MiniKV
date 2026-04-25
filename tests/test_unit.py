import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.hash_ring import HashRing
from app.vector_clock import VectorClock


# ── HashRing ──────────────────────────────────────────────────────────────────
def make_ring():
    r = HashRing(virtual_nodes=150)
    for i in range(1, 6):
        r.add_node(f"redis{i}")
    return r


def test_ring_returns_node():
    r = make_ring()
    assert r.get_node("hello") is not None


def test_ring_get_n_distinct():
    r = make_ring()
    nodes = r.get_nodes("somekey", 5)
    assert len(nodes) == 5
    assert len(set(nodes)) == 5


def test_ring_distribution():
    """Each node should own ~20% of keys (±10%)."""
    r = make_ring()
    counts = {f"redis{i}": 0 for i in range(1, 6)}
    for i in range(1000):
        counts[r.get_node(f"key:{i}")] += 1
    for node, count in counts.items():
        assert 100 < count < 300, f"{node} has {count}/1000 keys"


def test_ring_remove_node():
    r = make_ring()
    r.remove_node("redis3")
    for i in range(100):
        node = r.get_node(f"key:{i}")
        assert node != "redis3"


# ── VectorClock ───────────────────────────────────────────────────────────────
def test_vc_increment():
    vc = VectorClock().increment("A")
    assert vc.clock == {"A": 1}
    vc2 = vc.increment("A")
    assert vc2.clock == {"A": 2}


def test_vc_merge():
    a = VectorClock({"A": 3, "B": 1})
    b = VectorClock({"A": 1, "B": 4, "C": 2})
    merged = a.merge(b)
    assert merged.clock == {"A": 3, "B": 4, "C": 2}


def test_vc_newer_than():
    old = VectorClock({"A": 1})
    new = VectorClock({"A": 2})
    assert new.is_newer_than(old)
    assert not old.is_newer_than(new)


def test_vc_concurrent():
    a = VectorClock({"A": 2, "B": 1})
    b = VectorClock({"A": 1, "B": 2})
    assert not a.is_newer_than(b)
    assert not b.is_newer_than(a)