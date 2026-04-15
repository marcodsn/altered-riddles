#!/usr/bin/env python3
"""promote.py — Promote riddles from pool to benchmark.

Subcommands:
    add               Move riddles from pool -> benchmark
    status            Show benchmark / pool composition
    refresh-auxiliary  Replace auxiliary entries with fresh pool riddles
    split             One-shot fixed/auxiliary split from pool

Usage:
    python -m scripts.promote add --count 100 --set fixed
    python -m scripts.promote add --count 200 --set auxiliary
    python -m scripts.promote status
    python -m scripts.promote refresh-auxiliary --count 200
    python -m scripts.promote split --fixed-count 100 --auxiliary-count 250
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scripts.core.config import DEFAULT_BENCHMARK, DEFAULT_BENCHMARK_FIXED, DEFAULT_POOL
from scripts.core.io_utils import append_jsonl, load_jsonl_if_exists, write_jsonl

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

FIXED_PATH = DEFAULT_BENCHMARK_FIXED


def _make_id(n: int) -> str:
    return f"alt_{n:04d}"


def _normalize(text: str) -> str:
    return text.strip().lower()


def _get_max_id(entries: list[dict]) -> int:
    max_id = 0
    for e in entries:
        m = re.match(r"alt_(\d+)", e.get("id", ""))
        if m:
            max_id = max(max_id, int(m.group(1)))
    return max_id


def _pick_balanced(
    pool: list[dict],
    count: int,
    max_per_original: int | None = None,
    existing_entries: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Pick count entries using round-robin over source values.
    Returns (selected, remaining).
    """
    original_counts: dict[str, int] = defaultdict(int)
    if existing_entries:
        for e in existing_entries:
            key = _normalize(e.get("original_riddle", ""))
            if key:
                original_counts[key] += 1

    buckets: dict[str, list[int]] = defaultdict(list)
    for i, entry in enumerate(pool):
        buckets[entry.get("source", "__unknown__")].append(i)

    sources = list(buckets.keys())
    selected_indices: list[int] = []
    skipped: set[int] = set()

    while len(selected_indices) < count:
        made_progress = False
        for src in sources:
            if len(selected_indices) >= count:
                break
            while buckets[src]:
                idx = buckets[src].pop(0)
                entry = pool[idx]
                orig_key = _normalize(entry.get("original_riddle", ""))
                if max_per_original and orig_key and original_counts[orig_key] >= max_per_original:
                    skipped.add(idx)
                    continue
                selected_indices.append(idx)
                if orig_key:
                    original_counts[orig_key] += 1
                made_progress = True
                break
        if not made_progress:
            break

    selected_set = set(selected_indices)
    selected = [pool[i] for i in selected_indices]
    remaining = [pool[i] for i in range(len(pool)) if i not in selected_set and i not in skipped]
    remaining.extend(pool[i] for i in sorted(skipped))
    return selected, remaining


def _source_breakdown(entries: list[dict], label: str):
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e.get("source", "?")] += 1
    breakdown = ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
    logger.info("%s source breakdown: %s", label, breakdown)


# ── Subcommands ───────────────────────────────────────────────────────


def cmd_add(args):
    pool = load_jsonl_if_exists(args.pool)
    if not pool:
        logger.error("Pool is empty or missing.")
        raise SystemExit(1)

    count = min(args.count, len(pool))
    existing = load_jsonl_if_exists(args.benchmark)
    existing_fixed = load_jsonl_if_exists(FIXED_PATH)
    all_existing = existing + existing_fixed

    to_promote, remaining = _pick_balanced(pool, count, args.max_per_original, all_existing)
    max_id = max(_get_max_id(existing), _get_max_id(existing_fixed))

    for i, entry in enumerate(to_promote, start=max_id + 1):
        entry["id"] = _make_id(i)
        entry["set"] = args.set

    target = FIXED_PATH if args.set == "fixed" else args.benchmark
    for entry in to_promote:
        append_jsonl(target, entry)
    write_jsonl(args.pool, remaining)

    logger.info(
        "Promoted %d riddles -> %s (set=%s). Pool: %d remaining.",
        len(to_promote),
        target,
        args.set,
        len(remaining),
    )
    _source_breakdown(to_promote, "Promoted")


def cmd_status(args):
    benchmark = load_jsonl_if_exists(args.benchmark)
    fixed = load_jsonl_if_exists(FIXED_PATH)
    pool = load_jsonl_if_exists(args.pool)

    pool_sources: dict[str, int] = defaultdict(int)
    for e in pool:
        pool_sources[e.get("source", "?")] += 1

    print()
    print("+" + "-" * 40 + "+")
    print("|  Altered Riddles — Status              |")
    print("+" + "-" * 40 + "+")
    print(f"|  Benchmark (auxiliary) : {len(benchmark):<14d}|")
    print(f"|  Benchmark (fixed)     : {len(fixed):<14d}|")
    print(f"|  Total benchmark       : {len(benchmark) + len(fixed):<14d}|")
    print(f"|  Pool (pending)        : {len(pool):<14d}|")
    if pool_sources:
        print("+" + "-" * 40 + "+")
        print("|  Pool by source                        |")
        for src, n in sorted(pool_sources.items()):
            print(f"|    {src:<22s}: {n:<12d}|")
    print("+" + "-" * 40 + "+")
    print()


def cmd_refresh_auxiliary(args):
    bench_path = Path(args.benchmark)
    if bench_path.exists():
        backup_dir = Path(args.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        shutil.copy2(args.benchmark, backup_dir / f"benchmark_{ts}.jsonl")
        logger.info("Benchmark backed up.")

    pool = load_jsonl_if_exists(args.pool)
    if not pool:
        logger.error("Pool is empty.")
        raise SystemExit(1)

    fixed_entries = load_jsonl_if_exists(FIXED_PATH)
    count = min(args.count, len(pool))

    to_promote, remaining = _pick_balanced(pool, count, args.max_per_original, fixed_entries)

    max_id = _get_max_id(fixed_entries)
    for i, entry in enumerate(to_promote, start=max_id + 1):
        entry["id"] = _make_id(i)
        entry["set"] = "auxiliary"

    write_jsonl(args.benchmark, to_promote)
    write_jsonl(args.pool, remaining)

    logger.info(
        "Refreshed auxiliary: %d entries. Pool: %d remaining.", len(to_promote), len(remaining)
    )
    _source_breakdown(to_promote, "New auxiliary")


def cmd_split(args):
    pool = load_jsonl_if_exists(args.pool)
    if not pool:
        logger.error("Pool is empty.")
        raise SystemExit(1)

    fixed_count = args.fixed_count
    aux_count = args.auxiliary_count
    total_needed = fixed_count + aux_count

    if total_needed > len(pool):
        logger.warning("Requested %d but pool has %d. Adjusting.", total_needed, len(pool))
        ratio = fixed_count / total_needed
        fixed_count = int(len(pool) * ratio)
        aux_count = len(pool) - fixed_count

    # Pick fixed first
    fixed_entries, remaining = _pick_balanced(pool, fixed_count, args.max_per_original)
    # Then auxiliary from remaining
    aux_entries, final_remaining = _pick_balanced(
        remaining, aux_count, args.max_per_original, fixed_entries
    )

    idx = 0
    for entry in fixed_entries:
        idx += 1
        entry["id"] = _make_id(idx)
        entry["set"] = "fixed"

    for entry in aux_entries:
        idx += 1
        entry["id"] = _make_id(idx)
        entry["set"] = "auxiliary"

    write_jsonl(FIXED_PATH, fixed_entries)
    write_jsonl(args.benchmark, aux_entries)
    write_jsonl(args.pool, final_remaining)

    logger.info(
        "Split complete: %d fixed, %d auxiliary. Pool: %d remaining.",
        len(fixed_entries),
        len(aux_entries),
        len(final_remaining),
    )
    _source_breakdown(fixed_entries, "Fixed")
    _source_breakdown(aux_entries, "Auxiliary")


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser(description="Promote riddles from pool to benchmark.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Move riddles from pool -> benchmark")
    p_add.add_argument("--count", type=int, required=True)
    p_add.add_argument("--set", choices=["fixed", "auxiliary"], default="auxiliary")
    p_add.add_argument("--pool", default=DEFAULT_POOL)
    p_add.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    p_add.add_argument("--max-per-original", type=int, default=3)
    p_add.set_defaults(func=cmd_add)

    p_status = sub.add_parser("status", help="Show benchmark / pool status")
    p_status.add_argument("--pool", default=DEFAULT_POOL)
    p_status.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    p_status.set_defaults(func=cmd_status)

    p_refresh = sub.add_parser("refresh-auxiliary", help="Replace auxiliary entries")
    p_refresh.add_argument("--count", type=int, required=True)
    p_refresh.add_argument("--pool", default=DEFAULT_POOL)
    p_refresh.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    p_refresh.add_argument("--backup-dir", default="data/backups")
    p_refresh.add_argument("--max-per-original", type=int, default=3)
    p_refresh.set_defaults(func=cmd_refresh_auxiliary)

    p_split = sub.add_parser("split", help="One-shot fixed/auxiliary split")
    p_split.add_argument("--fixed-count", type=int, required=True)
    p_split.add_argument("--auxiliary-count", type=int, required=True)
    p_split.add_argument("--pool", default=DEFAULT_POOL)
    p_split.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    p_split.add_argument("--max-per-original", type=int, default=3)
    p_split.set_defaults(func=cmd_split)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
