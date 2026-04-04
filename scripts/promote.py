"""promote.py — Manage the riddle pool and promote riddles to the benchmark.

Moves validated riddles from `data/pool.jsonl` to `data/benchmark.jsonl`,
optionally tagging them as **fixed** (longitudinal baseline, never regenerated)
or **auxiliary** (refreshed each run).

Subcommands
───────────
    add                 Move riddles from pool → benchmark
    status              Show current benchmark / pool composition
    refresh-auxiliary   Replace all auxiliary entries with fresh pool riddles

Examples
────────
    python -m scripts.promote add --count 150 --set fixed
    python -m scripts.promote add --count 50 --set auxiliary
    python -m scripts.promote status
    python -m scripts.promote refresh-auxiliary --count 100
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scripts.core.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_POOL,
    VERSION_FILE,
    get_benchmark_version,
)
from scripts.core.io_utils import (
    append_jsonl,
    get_max_benchmark_id,
    load_jsonl_if_exists,
    write_jsonl,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────


def _make_id(n: int) -> str:
    """Format a numeric ID as `alt_NNN` (zero-padded to 3+ digits)."""
    return f"alt_{n:03d}"


def _current_yymm() -> str:
    return datetime.now(timezone.utc).strftime("%y%m")


def _bump_version() -> str:
    """Write the current YYMM to `data/VERSION` and return it."""
    version = _current_yymm()
    vf = Path(VERSION_FILE)
    vf.parent.mkdir(parents=True, exist_ok=True)
    vf.write_text(version + "\n", encoding="utf-8")
    logger.info("Bumped VERSION → %s", version)
    return version


def _pick_balanced(pool: list[dict], count: int) -> tuple[list[dict], list[dict]]:
    """Pick *count* entries from *pool* spread evenly across `source` values.

    Uses round-robin over source buckets (preserving each bucket's original
    order), so every source contributes as equally as possible.

    Returns `(selected, remaining)`.
    """
    # Group pool indices by source, preserving insertion order.
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, entry in enumerate(pool):
        source = entry.get("source", "__unknown__")
        buckets[source].append(i)

    sources = list(buckets.keys())
    selected_indices: list[int] = []

    # Round-robin until we have enough or all buckets are exhausted.
    while len(selected_indices) < count:
        made_progress = False
        for src in sources:
            if len(selected_indices) >= count:
                break
            if buckets[src]:
                selected_indices.append(buckets[src].pop(0))
                made_progress = True
        if not made_progress:
            break

    selected_set = set(selected_indices)
    selected = [pool[i] for i in selected_indices]
    remaining = [pool[i] for i in range(len(pool)) if i not in selected_set]

    # Emit a per-source breakdown at DEBUG level.
    if logger.isEnabledFor(logging.DEBUG):
        counts: dict[str, int] = defaultdict(int)
        for entry in selected:
            counts[entry.get("source", "__unknown__")] += 1
        breakdown = ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
        logger.debug("Balanced pick breakdown: %s", breakdown)

    return selected, remaining


def _log_source_breakdown(entries: list[dict], label: str) -> None:
    """Log an INFO-level per-source count summary."""
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e.get("source", "__unknown__")] += 1
    breakdown = ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
    logger.info("%s source breakdown: %s", label, breakdown)


# ── Subcommand: add ───────────────────────────────────────────────────


def cmd_add(args: argparse.Namespace) -> None:
    """Move *count* riddles from the pool into the benchmark."""
    pool = load_jsonl_if_exists(args.pool)
    if not pool:
        logger.error("Pool is empty or missing (%s). Nothing to promote.", args.pool)
        raise SystemExit(1)

    if args.count > len(pool):
        logger.warning(
            "Requested %d but pool only has %d entries. Promoting all.",
            args.count,
            len(pool),
        )
    count = min(args.count, len(pool))
    to_promote, remaining = _pick_balanced(pool, min(args.count, len(pool)))

    max_id = get_max_benchmark_id(args.benchmark)
    version = get_benchmark_version()

    promoted: list[dict] = []
    for i, entry in enumerate(to_promote, start=max_id + 1):
        entry["id"] = _make_id(i)
        entry["set"] = args.set
        entry["version_added"] = version
        promoted.append(entry)

    # Append to benchmark
    for entry in promoted:
        append_jsonl(args.benchmark, entry)

    # Rewrite pool without promoted entries
    write_jsonl(args.pool, remaining)

    logger.info(
        "Promoted %d riddles → %s (set=%s, ids %s–%s). Pool: %d remaining.",
        count,
        args.benchmark,
        args.set,
        promoted[0]["id"],
        promoted[-1]["id"],
        len(remaining),
    )
    _log_source_breakdown(promoted, "Promoted")


# ── Subcommand: status ───────────────────────────────────────────────


def cmd_status(args: argparse.Namespace) -> None:
    """Print a summary table of the benchmark and pool."""
    benchmark = load_jsonl_if_exists(args.benchmark)
    pool = load_jsonl_if_exists(args.pool)

    total = len(benchmark)
    fixed = sum(1 for e in benchmark if e.get("set") == "fixed")
    auxiliary = sum(1 for e in benchmark if e.get("set") == "auxiliary")
    untagged = total - fixed - auxiliary

    version = get_benchmark_version()

    # Per-source counts in the pool
    pool_sources: dict[str, int] = defaultdict(int)
    for e in pool:
        pool_sources[e.get("source", "__unknown__")] += 1

    print()
    print("╔══════════════════════════════════════╗")
    print("║    Altered Riddles — Benchmark Status ║")
    print("╠══════════════════════════════════════╣")
    print(f"║  Version          : {version:<17s}║")
    print(f"║  Benchmark total  : {total:<17d}║")
    print(f"║    ├─ fixed       : {fixed:<17d}║")
    print(f"║    ├─ auxiliary   : {auxiliary:<17d}║")
    print(f"║    └─ untagged    : {untagged:<17d}║")
    print(f"║  Pool (pending)   : {len(pool):<17d}║")
    if pool_sources:
        print("╠══════════════════════════════════════╣")
        print("║  Pool by source                      ║")
        for src, n in sorted(pool_sources.items()):
            label = f"    {src}"
            print(f"║  {label:<20s}: {n:<15d}║")
    print("╚══════════════════════════════════════╝")
    print()


# ── Subcommand: refresh-auxiliary ─────────────────────────────────────


def cmd_refresh_auxiliary(args: argparse.Namespace) -> None:
    """Replace all auxiliary entries with fresh ones from the pool."""
    # ------------------------------------------------------------------
    # Back up the current benchmark before any modification
    # ------------------------------------------------------------------
    benchmark_path_obj = Path(args.benchmark)
    if benchmark_path_obj.exists():
        backup_dir = Path(args.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"benchmark_{backup_ts}.jsonl"
        shutil.copy2(args.benchmark, backup_path)
        logger.info("Benchmark backed up → %s", backup_path)

    benchmark = load_jsonl_if_exists(args.benchmark)
    pool = load_jsonl_if_exists(args.pool)

    if not pool:
        logger.error("Pool is empty or missing (%s). Nothing to refresh.", args.pool)
        raise SystemExit(1)

    # Separate fixed from auxiliary (and keep untagged with fixed)
    fixed_entries = [e for e in benchmark if e.get("set") != "auxiliary"]
    old_aux_count = len(benchmark) - len(fixed_entries)

    if args.count > len(pool):
        logger.warning(
            "Requested %d but pool only has %d entries. Using all.",
            args.count,
            len(pool),
        )
    count = min(args.count, len(pool))
    to_promote, remaining = _pick_balanced(pool, min(args.count, len(pool)))

    # Find max ID among fixed entries to continue numbering after them
    max_fixed_id = 0
    for entry in fixed_entries:
        eid = entry.get("id", "")
        m = re.match(r"alt_(\d+)", eid)
        if m:
            max_fixed_id = max(max_fixed_id, int(m.group(1)))

    version = _bump_version()

    new_auxiliary: list[dict] = []
    for i, entry in enumerate(to_promote, start=max_fixed_id + 1):
        entry["id"] = _make_id(i)
        entry["set"] = "auxiliary"
        entry["version_added"] = version
        new_auxiliary.append(entry)

    # Write benchmark: fixed + new auxiliary
    write_jsonl(args.benchmark, fixed_entries + new_auxiliary)

    # Update pool
    write_jsonl(args.pool, remaining)

    logger.info(
        "Refreshed auxiliary set: removed %d old, added %d new (version %s). "
        "Benchmark: %d fixed + %d auxiliary = %d total. Pool: %d remaining.",
        old_aux_count,
        count,
        version,
        len(fixed_entries),
        count,
        len(fixed_entries) + count,
        len(remaining),
    )
    _log_source_breakdown(new_auxiliary, "New auxiliary")


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="promote.py",
        description="Manage the riddle pool and promote riddles to the benchmark.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── add ────────────────────────────────────────────────────────────
    p_add = sub.add_parser("add", help="Move riddles from pool → benchmark")
    p_add.add_argument(
        "--count", type=int, required=True, help="Number of riddles to promote"
    )
    p_add.add_argument(
        "--set",
        choices=["fixed", "auxiliary"],
        default="auxiliary",
        help="Which set to assign (default: auxiliary)",
    )
    p_add.add_argument("--pool", default=DEFAULT_POOL, help="Pool file path")
    p_add.add_argument(
        "--benchmark", default=DEFAULT_BENCHMARK, help="Benchmark file path"
    )
    p_add.set_defaults(func=cmd_add)

    # ── status ─────────────────────────────────────────────────────────
    p_status = sub.add_parser("status", help="Show benchmark / pool composition")
    p_status.add_argument("--pool", default=DEFAULT_POOL, help="Pool file path")
    p_status.add_argument(
        "--benchmark", default=DEFAULT_BENCHMARK, help="Benchmark file path"
    )
    p_status.set_defaults(func=cmd_status)

    # ── refresh-auxiliary ──────────────────────────────────────────────
    p_refresh = sub.add_parser(
        "refresh-auxiliary",
        help="Replace all auxiliary entries with fresh pool riddles",
    )
    p_refresh.add_argument(
        "--count", type=int, required=True, help="How many new auxiliary riddles"
    )
    p_refresh.add_argument("--pool", default=DEFAULT_POOL, help="Pool file path")
    p_refresh.add_argument(
        "--benchmark", default=DEFAULT_BENCHMARK, help="Benchmark file path"
    )
    p_refresh.add_argument(
        "--backup-dir",
        default="data/backups",
        help="Directory for benchmark backups (default: data/backups)",
    )
    p_refresh.set_defaults(func=cmd_refresh_auxiliary)

    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
