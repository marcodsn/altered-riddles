#!/usr/bin/env python3
"""deduplicate.py — Deduplicate the validated riddles file.

All entries are kept in the file. Each entry gains two fields:
  - dedup_retained (bool): True if this entry is the representative of its group.
  - dedup_duplicate_of (str | null): ID of the retained entry when dedup_retained
    is False, otherwise null.

Re-running with different settings simply overwrites those two fields.

Two entries are duplicates if their altered_riddle texts are very similar.

Usage:
    python -m scripts.deduplicate
    python -m scripts.deduplicate --dry-run
    python -m scripts.deduplicate --threshold 0.97
"""

from __future__ import annotations

import argparse
import logging
import re
import string
from difflib import SequenceMatcher

from scripts.core.config import DEFAULT_VALIDATED
from scripts.core.io_utils import load_jsonl, write_jsonl

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("deduplicate")

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def normalise(text: str) -> str:
    text = text.lower().translate(_PUNCT_TABLE)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1

    def groups(self) -> dict[int, list[int]]:
        from collections import defaultdict

        g: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            g[self.find(i)].append(i)
        return dict(g)


def is_duplicate(a: dict, b: dict, threshold: float, cache: dict[int, str]) -> bool:
    """Check if two entries are duplicates."""
    id_a, id_b = id(a), id(b)
    if id_a not in cache:
        cache[id_a] = normalise(a.get("altered_riddle", ""))
    if id_b not in cache:
        cache[id_b] = normalise(b.get("altered_riddle", ""))

    norm_a, norm_b = cache[id_a], cache[id_b]

    # Exact match on altered riddle
    if norm_a and norm_b and norm_a == norm_b:
        return True

    # High similarity on altered riddle text alone
    if norm_a and norm_b and similarity(norm_a, norm_b) >= threshold:
        return True

    return False


def deduplicate(args):
    entries = load_jsonl(args.input)
    n = len(entries)
    logger.info("Input    : %s (%d entries)", args.input, n)
    logger.info("Threshold: %.2f", args.threshold)

    if n == 0:
        logger.info("Nothing to deduplicate.")
        return

    uf = UnionFind(n)
    cache: dict[int, str] = {}

    logger.info("Comparing %d pairs...", n * (n - 1) // 2)
    for i in range(n):
        for j in range(i + 1, n):
            if uf.find(i) == uf.find(j):
                continue
            if is_duplicate(entries[i], entries[j], args.threshold, cache):
                uf.union(i, j)

    groups = uf.groups()

    # For each group pick the best representative (most accepted answers).
    # Then annotate every entry in-place — no entries are removed.
    retained_count = 0
    duplicate_count = 0

    for _root, members in groups.items():
        if len(members) == 1:
            entries[members[0]]["dedup_retained"] = True
            entries[members[0]]["dedup_duplicate_of"] = None
            retained_count += 1
        else:
            best = max(
                members,
                key=lambda m: len(entries[m].get("altered_accepted_answers", [])),
            )
            best_id = entries[best].get("id", f"idx_{best}")

            entries[best]["dedup_retained"] = True
            entries[best]["dedup_duplicate_of"] = None
            retained_count += 1

            dupes = [m for m in members if m != best]
            removed_ids = [entries[m].get("id", f"idx_{m}") for m in dupes]
            logger.info(
                "Keeping %s, marking as duplicates: %s", best_id, ", ".join(removed_ids)
            )

            for m in dupes:
                entries[m]["dedup_retained"] = False
                entries[m]["dedup_duplicate_of"] = best_id
                duplicate_count += 1

    logger.info("=" * 60)
    logger.info(
        "Total: %d  Retained: %d  Duplicates: %d",
        n,
        retained_count,
        duplicate_count,
    )

    if args.dry_run:
        logger.info("Dry run — no changes written.")
    else:
        write_jsonl(args.input, entries)
        logger.info(
            "Updated : %s (all %d entries preserved, fields annotated)", args.input, n
        )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Deduplicate validated riddles (non-destructive)."
    )
    parser.add_argument("--input", default=DEFAULT_VALIDATED)
    parser.add_argument("--threshold", type=float, default=0.97)
    parser.add_argument("--dry-run", action="store_true")
    return parser


if __name__ == "__main__":
    deduplicate(build_parser().parse_args())
