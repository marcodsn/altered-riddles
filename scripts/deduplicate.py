#!/usr/bin/env python3
"""deduplicate.py — Deduplicate the benchmark file by comparing altered riddles.

Uses exact matching (after normalisation) and fuzzy matching via
`difflib.SequenceMatcher` to find duplicate or near-duplicate entries.
For each group of duplicates the entry with the most accepted answers is kept.

Usage examples:
    python -m scripts.deduplicate
    python -m scripts.deduplicate --dry-run
    python -m scripts.deduplicate --pool data/pool.jsonl --similarity-threshold 0.9
    python -m scripts.deduplicate --dry-run --similarity-threshold 0.8
    python -m scripts.deduplicate --benchmark data/benchmark.jsonl
    python -m scripts.deduplicate --benchmark ""  # skip benchmark cross-check
"""

from __future__ import annotations

import argparse
import logging
import re
import string
from difflib import SequenceMatcher
from typing import Any

from scripts.core.io_utils import load_jsonl, write_jsonl

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("deduplicate")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Pre-compile a translation table that strips all punctuation
_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def normalise(text: str) -> str:
    """Lower-case, strip punctuation, and collapse whitespace."""
    text = text.lower().translate(_PUNCT_TABLE)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    """Return SequenceMatcher ratio between two strings."""
    return SequenceMatcher(None, a, b).ratio()


def accepted_answer_count(entry: dict[str, Any]) -> int:
    """Return the number of altered accepted answers for ranking purposes."""
    answers = entry.get("altered_accepted_answers", [])
    if isinstance(answers, list):
        return len(answers)
    return 1


def is_duplicate_pair(
    a: dict[str, Any],
    b: dict[str, Any],
    norm_cache: dict[int, str],
    threshold: float,
) -> bool:
    """Determine whether entries *a* and *b* are duplicates.

    Two entries are considered duplicates if either:
      1. Their normalised `altered_riddle` texts are identical, OR
      2. Their `altered_riddle` texts have fuzzy similarity >= *threshold*, OR
      3. Their `original_riddle` texts are very similar (>= *threshold*) AND
         their `altered_answer` texts are also very similar (>= *threshold*),
         indicating the same base riddle was altered in the same way.
    """
    id_a = id(a)  # Use object id for cache keys
    id_b = id(b)

    # --- normalised altered riddles ---
    if id_a not in norm_cache:
        norm_cache[id_a] = normalise(a.get("altered_riddle", ""))
    if id_b not in norm_cache:
        norm_cache[id_b] = normalise(b.get("altered_riddle", ""))

    norm_a = norm_cache[id_a]
    norm_b = norm_cache[id_b]

    # Check 1: exact match on normalised altered riddle
    if norm_a and norm_b and norm_a == norm_b:
        return True

    # Check 2: fuzzy match on altered riddle
    if norm_a and norm_b and similarity(norm_a, norm_b) >= threshold:
        return True

    # Check 3: same original riddle + same altered answer concept
    orig_a = normalise(a.get("original_riddle", ""))
    orig_b = normalise(b.get("original_riddle", ""))
    ans_a = normalise(a.get("altered_answer", ""))
    ans_b = normalise(b.get("altered_answer", ""))

    if (
        orig_a
        and orig_b
        and ans_a
        and ans_b
        and similarity(orig_a, orig_b) >= threshold
        and similarity(ans_a, ans_b) >= threshold
    ):
        return True

    return False


# ---------------------------------------------------------------------------
# Union-Find for grouping duplicates
# ---------------------------------------------------------------------------


class UnionFind:
    """Simple union-find (disjoint-set) data structure."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]  # path compression
            x = self.parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1

    def groups(self) -> dict[int, list[int]]:
        """Return a mapping of root → list of member indices."""
        from collections import defaultdict

        g: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            g[self.find(i)].append(i)
        return dict(g)


# ---------------------------------------------------------------------------
# Main deduplication logic
# ---------------------------------------------------------------------------


def remove_benchmark_duplicates(
    pool: list[dict[str, Any]],
    benchmark: list[dict[str, Any]],
    threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Remove pool entries that are near-duplicates of existing benchmark entries.

    Returns `(kept, removed)`.
    """
    if not benchmark:
        return pool, []

    norm_cache: dict[int, str] = {}
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []

    for pool_entry in pool:
        is_dup = False
        for bench_entry in benchmark:
            if is_duplicate_pair(pool_entry, bench_entry, norm_cache, threshold):
                logger.info(
                    "  Pool %s duplicates benchmark %s — removing from pool.",
                    pool_entry.get("id", "?"),
                    bench_entry.get("id", "?"),
                )
                is_dup = True
                break
        (removed if is_dup else kept).append(pool_entry)

    return kept, removed


def deduplicate(args: argparse.Namespace) -> None:
    """Run the deduplication pipeline according to parsed CLI *args*."""
    pool_path = args.pool
    threshold = args.similarity_threshold
    dry_run = args.dry_run

    entries = load_jsonl(pool_path)
    n = len(entries)

    logger.info("Pool      : %s", pool_path)
    logger.info("Entries   : %d", n)
    logger.info("Threshold : %.2f", threshold)
    logger.info("Dry run   : %s", dry_run)

    # ------------------------------------------------------------------
    # Optional cross-check: remove pool entries that duplicate benchmark
    # ------------------------------------------------------------------
    if args.benchmark:
        from scripts.core.io_utils import load_jsonl_if_exists as _load_if

        benchmark_entries = _load_if(args.benchmark)
        if benchmark_entries:
            logger.info(
                "Cross-checking %d pool entries against %d benchmark entries …",
                n,
                len(benchmark_entries),
            )
            entries, bench_removed = remove_benchmark_duplicates(
                entries, benchmark_entries, threshold
            )
            n = len(entries)
            logger.info(
                "Removed %d pool entries that duplicate benchmark entries. "
                "Pool size now: %d",
                len(bench_removed),
                n,
            )
        else:
            logger.info(
                "Benchmark file %s not found or empty — skipping cross-check.",
                args.benchmark,
            )

    if n <= 1:
        logger.info("Nothing to deduplicate (0–1 entries).")
        if not dry_run:
            write_jsonl(pool_path, entries)
        return

    # Build duplicate groups using union-find
    uf = UnionFind(n)
    norm_cache: dict[int, str] = {}  # keyed by id(entry)
    duplicates_found = 0

    logger.info("Comparing %d entry pairs …", n * (n - 1) // 2)

    for i in range(n):
        for j in range(i + 1, n):
            if uf.find(i) == uf.find(j):
                # Already in the same group — skip the (potentially expensive) comparison
                continue
            if is_duplicate_pair(entries[i], entries[j], norm_cache, threshold):
                uf.union(i, j)
                duplicates_found += 1
                logger.debug(
                    "Duplicate: %s ↔ %s",
                    entries[i].get("id", i),
                    entries[j].get("id", j),
                )

    groups = uf.groups()
    duplicate_groups = {
        root: members for root, members in groups.items() if len(members) > 1
    }

    # Report duplicate groups
    if duplicate_groups:
        logger.info("Found %d duplicate group(s):", len(duplicate_groups))
        for group_idx, (_, members) in enumerate(duplicate_groups.items(), start=1):
            member_ids = [entries[m].get("id", f"idx_{m}") for m in members]
            logger.info("  Group %d: %s", group_idx, ", ".join(member_ids))
    else:
        logger.info("No duplicates found.")

    # Select the best entry from each group (most altered_accepted_answers, or first)
    keep_indices: set[int] = set()
    for root, members in groups.items():
        if len(members) == 1:
            keep_indices.add(members[0])
        else:
            # Sort by accepted answer count descending, then by original index ascending
            best = max(members, key=lambda m: (accepted_answer_count(entries[m]), -m))
            keep_indices.add(best)
            removed_ids = [
                entries[m].get("id", f"idx_{m}") for m in members if m != best
            ]
            logger.info(
                "  Keeping %s, removing: %s",
                entries[best].get("id", f"idx_{best}"),
                ", ".join(removed_ids),
            )

    # Build the deduplicated list preserving original order
    deduped = [entries[i] for i in sorted(keep_indices)]
    removed_count = n - len(deduped)

    # Renumber IDs sequentially
    for idx, entry in enumerate(deduped, start=1):
        entry["id"] = f"pool_{idx:04d}"

    # Summary
    logger.info("=" * 60)
    logger.info("Entries before : %d", n)
    logger.info("Entries after  : %d", len(deduped))
    logger.info("Duplicates removed : %d", removed_count)

    if dry_run:
        logger.info("Dry run — no changes written to disk.")
    else:
        write_jsonl(pool_path, deduped)
        logger.info("Pool rewritten to %s", pool_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deduplicate the pool JSONL file by comparing altered riddles.",
    )
    parser.add_argument(
        "--pool",
        default="data/pool.jsonl",
        help="Path to pool JSONL file (default: data/pool.jsonl)",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.85,
        help="Fuzzy matching threshold 0–1 (default: 0.85)",
    )
    parser.add_argument(
        "--benchmark",
        default="data/benchmark.jsonl",
        help=(
            "Path to benchmark JSONL file used to cross-check pool entries. "
            "Pool entries that are near-duplicates of existing benchmark entries "
            "are removed. Set to empty string to skip. "
            "(default: data/benchmark.jsonl)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="If set, just report duplicates without modifying the file",
    )
    return parser


if __name__ == "__main__":
    deduplicate(build_parser().parse_args())
