"""Tests for scripts/promote.py — _pick_balanced and _make_id helpers."""

from scripts.promote import _make_id, _pick_balanced

# ── _make_id ──────────────────────────────────────────────────────────


def test_make_id_single_digit():
    assert _make_id(1) == "alt_001"


def test_make_id_three_digits():
    assert _make_id(123) == "alt_123"


def test_make_id_four_digits():
    assert _make_id(1000) == "alt_1000"


def test_make_id_zero():
    assert _make_id(0) == "alt_000"


# ── _pick_balanced ────────────────────────────────────────────────────


def _pool_with_sources(*counts: tuple[str, int]) -> list[dict]:
    """Build a synthetic pool with the given (source, count) pairs."""
    pool: list[dict] = []
    for source, n in counts:
        for i in range(n):
            pool.append({"source": source, "value": f"{source}_{i}"})
    return pool


def test_pick_balanced_even_split():
    """When requesting the same count as sources can equally provide, each
    source contributes the same number of entries."""
    pool = _pool_with_sources(("A", 5), ("B", 5), ("C", 5))
    selected, remaining = _pick_balanced(pool, 6)

    assert len(selected) == 6
    assert len(remaining) == 9

    source_counts = {}
    for entry in selected:
        src = entry["source"]
        source_counts[src] = source_counts.get(src, 0) + 1

    # Round-robin with 3 sources and 6 picks → 2 each
    assert source_counts == {"A": 2, "B": 2, "C": 2}


def test_pick_balanced_uneven_request():
    """When count isn't divisible by #sources, the remainder goes to
    whichever sources come first in round-robin order."""
    pool = _pool_with_sources(("A", 5), ("B", 5))
    selected, remaining = _pick_balanced(pool, 3)

    assert len(selected) == 3
    assert len(remaining) == 7

    source_counts = {}
    for entry in selected:
        src = entry["source"]
        source_counts[src] = source_counts.get(src, 0) + 1

    # 3 picks from 2 sources → one gets 2, the other gets 1
    assert source_counts["A"] == 2
    assert source_counts["B"] == 1


def test_pick_balanced_exhausts_small_bucket():
    """When one source has fewer entries than others, the algorithm draws
    more from the remaining sources."""
    pool = _pool_with_sources(("A", 1), ("B", 10))
    selected, remaining = _pick_balanced(pool, 5)

    assert len(selected) == 5

    source_counts = {}
    for entry in selected:
        src = entry["source"]
        source_counts[src] = source_counts.get(src, 0) + 1

    assert source_counts["A"] == 1
    assert source_counts["B"] == 4


def test_pick_balanced_request_more_than_pool():
    """When count exceeds pool size, return everything available."""
    pool = _pool_with_sources(("A", 2), ("B", 2))
    selected, remaining = _pick_balanced(pool, 100)

    assert len(selected) == 4
    assert len(remaining) == 0


def test_pick_balanced_preserves_order_within_source():
    """Each source's entries should be picked in their original pool order."""
    pool = _pool_with_sources(("A", 3), ("B", 3))
    selected, _ = _pick_balanced(pool, 6)

    a_entries = [e["value"] for e in selected if e["source"] == "A"]
    b_entries = [e["value"] for e in selected if e["source"] == "B"]

    assert a_entries == ["A_0", "A_1", "A_2"]
    assert b_entries == ["B_0", "B_1", "B_2"]


def test_pick_balanced_zero_count():
    """Requesting zero entries returns nothing and leaves the pool intact."""
    pool = _pool_with_sources(("A", 3))
    selected, remaining = _pick_balanced(pool, 0)

    assert len(selected) == 0
    assert len(remaining) == 3
