"""revert_promotion.py — Revert promoted benchmark entries back to the pool.

Moves entries from `data/benchmark.jsonl` back to `data/pool.jsonl`,
stripping the promotion metadata (`id`, `set`, `version_added`) and
reassigning fresh `pool_NNNN` IDs.

This is useful when you forgot to run the deduplication script before
promoting riddles from the pool and want to restore the pre-promotion
state so you can deduplicate and re-promote.

Subcommands
───────────
    run                 Move entries from benchmark → pool
    status              Preview which entries would be reverted

Examples
────────
    # Revert ALL benchmark entries back to the pool
    python -m scripts.revert_promotion run

    # Revert only entries promoted in a specific version
    python -m scripts.revert_promotion run --version 2506

    # Revert only auxiliary entries
    python -m scripts.revert_promotion run --set auxiliary

    # Dry-run (preview without writing any files)
    python -m scripts.revert_promotion run --dry-run

    # Revert specific IDs
    python -m scripts.revert_promotion run --ids alt_001,alt_002,alt_003

    # Preview what would be reverted given a filter
    python -m scripts.revert_promotion status --version 2506
    python -m scripts.revert_promotion status --set auxiliary
"""

from __future__ import annotations

import argparse
import logging
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from scripts.core.config import DEFAULT_BENCHMARK, DEFAULT_POOL
from scripts.core.io_utils import (
    get_max_pool_id,
    load_jsonl_if_exists,
    write_jsonl,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────


def _make_pool_id(n: int) -> str:
    """Format a numeric ID as `pool_NNNN` (zero-padded to 4+ digits)."""
    return f"pool_{n:04d}"


def _backup(path: str | Path, backup_dir: str | Path) -> Path | None:
    """Copy *path* to *backup_dir* with a timestamp suffix.

    Returns the backup path, or ``None`` if the source file does not exist.
    """
    src = Path(path)
    if not src.exists():
        logger.warning("Skipping backup — file not found: %s", src)
        return None
    bdir = Path(backup_dir)
    bdir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = bdir / f"{src.stem}_{ts}{src.suffix}"
    shutil.copy2(src, dest)
    logger.info("Backed up %s → %s", src, dest)
    return dest


def _select_entries(
    benchmark: list[dict],
    version: str | None,
    set_filter: str | None,
    ids: set[str] | None,
) -> tuple[list[dict], list[dict]]:
    """Split *benchmark* into ``(to_revert, to_keep)``.

    Filtering priority (mutually exclusive at the CLI level):
      1. ``ids``        — revert entries whose ``id`` is in *ids*.
      2. ``version``    — revert entries whose ``version_added`` matches.
      3. ``set_filter`` — revert entries whose ``set`` matches.
      4. No filter      — revert *all* entries.
    """
    to_revert: list[dict] = []
    to_keep: list[dict] = []

    for entry in benchmark:
        if ids is not None:
            match = entry.get("id") in ids
        elif version is not None:
            match = entry.get("version_added") == version
        elif set_filter is not None:
            match = entry.get("set") == set_filter
        else:
            match = True  # no filter → revert everything

        (to_revert if match else to_keep).append(entry)

    return to_revert, to_keep


def _strip_promotion_fields(entry: dict) -> dict:
    """Return a shallow copy of *entry* with benchmark-only fields removed."""
    stripped = dict(entry)
    stripped.pop("id", None)
    stripped.pop("set", None)
    stripped.pop("version_added", None)
    return stripped


def _log_source_breakdown(entries: list[dict], label: str) -> None:
    """Log an INFO-level per-source count summary for *entries*."""
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e.get("source", "__unknown__")] += 1
    breakdown = ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
    logger.info("%s source breakdown: %s", label, breakdown)


def _print_preview(entries: list[dict]) -> None:
    """Print a compact breakdown of *entries* grouped by set, version, and source."""
    sets: dict[str, int] = defaultdict(int)
    versions: dict[str, int] = defaultdict(int)
    sources: dict[str, int] = defaultdict(int)

    for e in entries:
        sets[e.get("set", "?")] += 1
        versions[e.get("version_added", "?")] += 1
        sources[e.get("source", "?")] += 1

    print("  By set:")
    for k, v in sorted(sets.items()):
        print(f"    {k:<20s}: {v}")
    print("  By version_added:")
    for k, v in sorted(versions.items()):
        print(f"    {k:<20s}: {v}")
    print("  By source:")
    for k, v in sorted(sources.items()):
        print(f"    {k:<20s}: {v}")
    print()


# ── Subcommand: run ───────────────────────────────────────────────────


def cmd_run(args: argparse.Namespace) -> None:
    """Revert selected benchmark entries back to the pool."""
    benchmark = load_jsonl_if_exists(args.benchmark)
    pool = load_jsonl_if_exists(args.pool)

    if not benchmark:
        logger.error(
            "Benchmark is empty or missing (%s). Nothing to revert.", args.benchmark
        )
        raise SystemExit(1)

    # Parse --ids if given
    ids: set[str] | None = None
    if args.ids:
        ids = {s.strip() for s in args.ids.split(",") if s.strip()}

    to_revert, to_keep = _select_entries(
        benchmark,
        version=args.version,
        set_filter=getattr(args, "set", None),
        ids=ids,
    )

    if not to_revert:
        logger.info("No entries matched the given filter. Nothing to do.")
        return

    logger.info(
        "Selected %d/%d benchmark entries to revert back to pool.",
        len(to_revert),
        len(benchmark),
    )

    if args.dry_run:
        print()
        print("── Dry-run preview ──────────────────────────────────────")
        _print_preview(to_revert)
        print(f"  Benchmark entries to revert : {len(to_revert)}")
        print(f"  Benchmark entries to keep   : {len(to_keep)}")
        print(f"  Pool entries after revert   : {len(pool) + len(to_revert)}")
        print()
        logger.info("Dry run — no files were modified.")
        return

    # Safety confirmation when reverting everything without an explicit filter
    reverting_all = not args.version and not getattr(args, "set", None) and not args.ids
    if reverting_all and not args.yes:
        print()
        resp = (
            input(
                f"⚠️  About to revert ALL {len(to_revert)} benchmark entries to the pool.\n"
                "Type 'yes' to confirm: "
            )
            .strip()
            .lower()
        )
        if resp != "yes":
            logger.info("Aborted.")
            return
        print()

    # Back up both files before any modification
    _backup(args.benchmark, args.backup_dir)
    _backup(args.pool, args.backup_dir)

    # Build restored pool entries: strip promotion fields, assign fresh pool IDs
    max_pool_id = get_max_pool_id(args.pool)
    restored: list[dict] = []
    for i, entry in enumerate(to_revert, start=max_pool_id + 1):
        clean = _strip_promotion_fields(entry)
        clean["id"] = _make_pool_id(i)
        restored.append(clean)

    # Rewrite benchmark (kept entries only)
    write_jsonl(args.benchmark, to_keep)

    # Append restored entries to pool
    write_jsonl(args.pool, pool + restored)

    logger.info(
        "Reverted %d entries → pool. Benchmark: %d entries remaining. Pool: %d total.",
        len(restored),
        len(to_keep),
        len(pool) + len(restored),
    )
    _log_source_breakdown(restored, "Reverted")


# ── Subcommand: status ────────────────────────────────────────────────


def cmd_status(args: argparse.Namespace) -> None:
    """Print a summary of entries that would be reverted given the current filter."""
    benchmark = load_jsonl_if_exists(args.benchmark)
    pool = load_jsonl_if_exists(args.pool)

    ids: set[str] | None = None
    if args.ids:
        ids = {s.strip() for s in args.ids.split(",") if s.strip()}

    to_revert, to_keep = _select_entries(
        benchmark,
        version=args.version,
        set_filter=getattr(args, "set", None),
        ids=ids,
    )

    # Determine active filter description
    if ids:
        filter_desc = f"ids = {args.ids}"
    elif args.version:
        filter_desc = f"version_added = {args.version}"
    elif getattr(args, "set", None):
        filter_desc = f"set = {args.set}"
    else:
        filter_desc = "ALL entries"

    print()
    print("╔══════════════════════════════════════════╗")
    print("║   Revert Promotion — Status Preview       ║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Filter               : {filter_desc:<17s}║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Benchmark (current)  : {len(benchmark):<17d}║")
    print(f"║  Pool (current)       : {len(pool):<17d}║")
    print("╠══════════════════════════════════════════╣")
    print(f"║  Entries to revert    : {len(to_revert):<17d}║")
    print(f"║  Entries to keep      : {len(to_keep):<17d}║")
    print(f"║  Pool after revert    : {len(pool) + len(to_revert):<17d}║")
    print("╚══════════════════════════════════════════╝")
    print()

    if to_revert:
        print("── Breakdown of entries that would be reverted ──────────")
        _print_preview(to_revert)
    else:
        print("No entries match the given filter.")


# ── Shared filter arguments ───────────────────────────────────────────


def _add_filter_args(parser: argparse.ArgumentParser) -> None:
    """Attach the shared, mutually-exclusive filtering flags to *parser*."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--version",
        metavar="YYMM",
        default=None,
        help=(
            "Revert only entries whose version_added equals this value "
            "(e.g. --version 2506)"
        ),
    )
    group.add_argument(
        "--set",
        dest="set",
        choices=["fixed", "auxiliary"],
        default=None,
        help="Revert only entries belonging to this set",
    )
    group.add_argument(
        "--ids",
        metavar="ID1,ID2,...",
        default=None,
        help=(
            "Comma-separated list of benchmark IDs to revert "
            "(e.g. --ids alt_001,alt_002,alt_003)"
        ),
    )
    parser.add_argument(
        "--pool",
        default=DEFAULT_POOL,
        help=f"Pool file path (default: {DEFAULT_POOL})",
    )
    parser.add_argument(
        "--benchmark",
        default=DEFAULT_BENCHMARK,
        help=f"Benchmark file path (default: {DEFAULT_BENCHMARK})",
    )


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="revert_promotion.py",
        description=(
            "Revert promoted benchmark entries back to the pool, "
            "stripping promotion metadata and reassigning pool IDs."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── run ────────────────────────────────────────────────────────────
    p_run = sub.add_parser(
        "run",
        help="Move selected entries from benchmark → pool",
    )
    _add_filter_args(p_run)
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview what would happen without writing any files",
    )
    p_run.add_argument(
        "--yes",
        "-y",
        action="store_true",
        default=False,
        help="Skip the confirmation prompt when reverting all entries",
    )
    p_run.add_argument(
        "--backup-dir",
        default="data/backups",
        help="Directory for pre-revert backups (default: data/backups)",
    )
    p_run.set_defaults(func=cmd_run)

    # ── status ─────────────────────────────────────────────────────────
    p_status = sub.add_parser(
        "status",
        help="Preview which entries would be reverted (no files modified)",
    )
    _add_filter_args(p_status)
    p_status.set_defaults(func=cmd_status)

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
