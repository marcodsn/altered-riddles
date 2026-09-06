"""Matched, item-balanced comparisons; no API dependencies.

Each item contributes its mean over samples, so different k values do not
change item weights. Both models must be familiar with the item's source.
Clusters are resampled jointly, preserving cross-model dependence. Intervals
are exploratory, pointwise 95% intervals, not multiplicity-adjusted ranks.
"""
from __future__ import annotations

import random
from collections import defaultdict
from itertools import combinations


def paired_comparison(a, b, clusters, *, n_boot=2000, seed=0):
    """Compare maps of item ID -> override probability on shared items (a-b)."""
    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    common = sorted(a.keys() & b.keys())
    if not common:
        return {"n_items": 0, "n_clusters": 0, "difference": None, "ci95": [None, None]}
    grouped = defaultdict(list)
    for uid in common:
        grouped[clusters[uid]].append(a[uid] - b[uid])
    keys = sorted(grouped)
    rng = random.Random(seed)
    draws = []
    for _ in range(n_boot):
        values = [v for key in rng.choices(keys, k=len(keys)) for v in grouped[key]]
        draws.append(sum(values) / len(values))
    draws.sort()
    return {
        "n_items": len(common), "n_clusters": len(keys),
        "difference": sum(a[u] - b[u] for u in common) / len(common),
        "ci95": [draws[int(.025 * n_boot)], draws[max(0, int(.975 * n_boot) - 1)]],
    }


def pairwise_comparisons(item_rates, clusters, *, n_boot=2000, seed=0):
    return [{"a": a, "b": b, **paired_comparison(item_rates[a], item_rates[b], clusters,
                                               n_boot=n_boot, seed=seed)}
            for a, b in combinations(sorted(item_rates), 2)]
