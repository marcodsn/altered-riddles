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
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

FIXED_PATH = DEFAULT_BENCHMARK_FIXED

MODEL_FAMILY_MAP: dict[str, str] = {
    "gpt": "gpt",
    "claude": "claude",
    "gemini": "gemini",
    "gemma": "gemma",
    "llama": "llama",
    "mistral": "mistral",
    "command": "cohere",
    "qwen": "qwen",
    "deepseek": "deepseek",
    "glm": "glm",
    "mimo": "mimo",
    "lfm": "lfm",
    "minimax": "minimax",
    "kimi": "kimi",
    "grok": "grok",
}


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


def _model_to_family(model_id: str) -> str:
    """Return the family name for a given model id, or the id itself as fallback."""
    raw = model_id.strip().lower()
    if not raw:
        return "__unknown__"
    key = raw.split("/", 1)[1] if "/" in raw else raw
    for prefix, family in MODEL_FAMILY_MAP.items():
        if key.startswith(prefix):
            return family
    return key  # unknown model stays as-is


def _pick_balanced(
    pool: list[dict],
    count: int,
    max_per_original: int | None = None,
    existing_entries: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Pick count entries using round-robin over model families.

    If round-robin stalls because some families run out of eligible entries,
    fall back to any remaining eligible entries across the whole pool.
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
        if entry.get("used_in_set"):
            continue
        family = _model_to_family(entry.get("source", "__unknown__"))
        buckets[family].append(i)

    families = list(buckets.keys())
    selected_indices: list[int] = []
    selected_set: set[int] = set()
    skipped: set[int] = set()

    def is_eligible(idx: int) -> bool:
        entry = pool[idx]
        orig_key = _normalize(entry.get("original_riddle", ""))
        return not (
            max_per_original
            and orig_key
            and original_counts[orig_key] >= max_per_original
        )

    def select_idx(idx: int) -> None:
        entry = pool[idx]
        orig_key = _normalize(entry.get("original_riddle", ""))
        selected_indices.append(idx)
        selected_set.add(idx)
        if orig_key:
            original_counts[orig_key] += 1

    while len(selected_indices) < count:
        made_progress = False
        for family in families:
            if len(selected_indices) >= count:
                break
            while buckets[family]:
                idx = buckets[family].pop(0)
                if idx in selected_set:
                    continue
                if not is_eligible(idx):
                    skipped.add(idx)
                    continue
                select_idx(idx)
                made_progress = True
                break
        if made_progress:
            continue

        for i, entry in enumerate(pool):
            if len(selected_indices) >= count:
                break
            if entry.get("used_in_set") or i in selected_set:
                continue
            if not is_eligible(i):
                skipped.add(i)
                continue
            select_idx(i)
            made_progress = True

        if not made_progress:
            break

    selected = [pool[i] for i in selected_indices]
    remaining = []
    for i, entry in enumerate(pool):
        if i in selected_set:
            updated = dict(entry)
            updated["used_in_set"] = True
            updated["used_set"] = updated.get("set") or "benchmark"
            remaining.append(updated)
        elif i in skipped:
            remaining.append(entry)
        else:
            remaining.append(entry)
    return selected, remaining


def _family_breakdown(entries: list[dict], label: str):
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        family = _model_to_family(e.get("source", "__unknown__"))
        counts[family] += 1
    breakdown = ", ".join(f"{family}={n}" for family, n in sorted(counts.items()))
    logger.info("%s model-family breakdown: %s", label, breakdown)


def _log_promotion_eligibility(
    pool: list[dict],
    existing_entries: list[dict],
    max_per_original: int | None,
) -> None:
    pending_pool = [e for e in pool if not e.get("used_in_set")]
    if not pending_pool:
        logger.info("No pending pool entries remain.")
        return

    original_counts: dict[str, int] = defaultdict(int)
    for e in existing_entries:
        key = _normalize(e.get("original_riddle", ""))
        if key:
            original_counts[key] += 1

    eligible_count = 0
    blocked_count = 0
    blocked_originals: dict[str, int] = defaultdict(int)

    for entry in pending_pool:
        orig_key = _normalize(entry.get("original_riddle", ""))
        if (
            max_per_original
            and orig_key
            and original_counts[orig_key] >= max_per_original
        ):
            blocked_count += 1
            blocked_originals[orig_key] += 1
        else:
            eligible_count += 1

    logger.info(
        "Promotion eligibility: %d pending, %d eligible, %d blocked by max-per-original=%s.",
        len(pending_pool),
        eligible_count,
        blocked_count,
        max_per_original,
    )

    if blocked_originals:
        top_blocked = sorted(
            blocked_originals.items(),
            key=lambda item: (-item[1], item[0]),
        )[:5]
        summary = ", ".join(f"{orig}={n}" for orig, n in top_blocked)
        logger.info("Top blocked originals in pending pool: %s", summary)


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

    to_promote, remaining = _pick_balanced(
        pool, count, args.max_per_original, all_existing
    )
    max_id = max(_get_max_id(existing), _get_max_id(existing_fixed))

    for i, entry in enumerate(to_promote, start=max_id + 1):
        entry["id"] = _make_id(i)
        entry["set"] = args.set

    target = FIXED_PATH if args.set == "fixed" else args.benchmark
    for entry in to_promote:
        append_jsonl(target, entry)
    write_jsonl(args.pool, remaining)

    used_count = sum(1 for e in remaining if e.get("used_in_set"))
    pending_count = len(remaining) - used_count

    logger.info(
        "Promoted %d riddles -> %s (set=%s). Pool: %d pending, %d used.",
        len(to_promote),
        target,
        args.set,
        pending_count,
        used_count,
    )
    if not to_promote:
        _log_promotion_eligibility(pool, all_existing, args.max_per_original)
    _family_breakdown(to_promote, "Promoted")


def cmd_status(args):
    benchmark = load_jsonl_if_exists(args.benchmark)
    fixed = load_jsonl_if_exists(FIXED_PATH)
    pool = load_jsonl_if_exists(args.pool)

    pending_pool = [e for e in pool if not e.get("used_in_set")]
    used_pool = [e for e in pool if e.get("used_in_set")]

    pending_families: dict[str, int] = defaultdict(int)
    used_families: dict[str, int] = defaultdict(int)
    for e in pending_pool:
        pending_families[_model_to_family(e.get("source", "__unknown__"))] += 1
    for e in used_pool:
        used_families[_model_to_family(e.get("source", "__unknown__"))] += 1

    print()
    print("+" + "-" * 40 + "+")
    print("|  Altered Riddles — Status              |")
    print("+" + "-" * 40 + "+")
    print(f"|  Benchmark (auxiliary) : {len(benchmark):<14d}|")
    print(f"|  Benchmark (fixed)     : {len(fixed):<14d}|")
    print(f"|  Total benchmark       : {len(benchmark) + len(fixed):<14d}|")
    print(f"|  Pool (total)          : {len(pool):<14d}|")
    print(f"|  Pool (pending)        : {len(pending_pool):<14d}|")
    print(f"|  Pool (used)           : {len(used_pool):<14d}|")
    if pending_families:
        print("+" + "-" * 40 + "+")
        print("|  Pending pool by family               |")
        for family, n in sorted(pending_families.items()):
            print(f"|    {family:<22s}: {n:<12d}|")
    if used_families:
        print("+" + "-" * 40 + "+")
        print("|  Used pool by family                  |")
        for family, n in sorted(used_families.items()):
            print(f"|    {family:<22s}: {n:<12d}|")
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

    to_promote, remaining = _pick_balanced(
        pool, count, args.max_per_original, fixed_entries
    )

    max_id = _get_max_id(fixed_entries)
    for i, entry in enumerate(to_promote, start=max_id + 1):
        entry["id"] = _make_id(i)
        entry["set"] = "auxiliary"

    write_jsonl(args.benchmark, to_promote)
    write_jsonl(args.pool, remaining)

    used_count = sum(1 for e in remaining if e.get("used_in_set"))
    pending_count = len(remaining) - used_count

    logger.info(
        "Refreshed auxiliary: %d entries. Pool: %d pending, %d used.",
        len(to_promote),
        pending_count,
        used_count,
    )
    if not to_promote:
        _log_promotion_eligibility(pool, fixed_entries, args.max_per_original)
    _family_breakdown(to_promote, "New auxiliary")


def cmd_split(args):
    pool = load_jsonl_if_exists(args.pool)
    if not pool:
        logger.error("Pool is empty.")
        raise SystemExit(1)

    fixed_count = args.fixed_count
    aux_count = args.auxiliary_count
    total_needed = fixed_count + aux_count

    if total_needed > len(pool):
        logger.warning(
            "Requested %d but pool has %d. Adjusting.", total_needed, len(pool)
        )
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

    used_count = sum(1 for e in final_remaining if e.get("used_in_set"))
    pending_count = len(final_remaining) - used_count

    logger.info(
        "Split complete: %d fixed, %d auxiliary. Pool: %d pending, %d used.",
        len(fixed_entries),
        len(aux_entries),
        pending_count,
        used_count,
    )
    _family_breakdown(fixed_entries, "Fixed")
    _family_breakdown(aux_entries, "Auxiliary")


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser():
    parser = argparse.ArgumentParser(
        description="Promote riddles from pool to benchmark."
    )
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
