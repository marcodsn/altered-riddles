#!/usr/bin/env python3
"""human_review.py — Interactive review of validated riddles.

Walk through validated riddles one by one and approve/reject/edit them.
Entries that don't need human review are auto-promoted directly to pool.
Entries flagged with needs_review=True are shown interactively.
Review outcomes are tracked via pool.jsonl and human_rejected.jsonl,
and pool entries already used in a benchmark set are also treated as processed
so entries are not shown again on future runs.

Usage:
    python -m scripts.human_review
    python -m scripts.human_review --input data/generated/validated.jsonl
"""

from __future__ import annotations

import argparse
import logging

from scripts.core.config import DEFAULT_HUMAN_REJECTED, DEFAULT_POOL, DEFAULT_VALIDATED
from scripts.core.io_utils import append_jsonl, load_jsonl, load_jsonl_if_exists

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("human_review")

SEP = "=" * 72
THIN = "-" * 72


def _pool_keys(pool: list[dict]) -> set[tuple[str, str]]:
    keys = set()
    for e in pool:
        orig = e.get("original_riddle", "").strip().lower()
        alt = e.get("altered_riddle", "").strip().lower()
        if orig and alt:
            keys.add((orig, alt))
    return keys


def _used_pool_keys(pool: list[dict]) -> set[tuple[str, str]]:
    keys = set()
    for e in pool:
        if not e.get("used_in_set"):
            continue
        orig = e.get("original_riddle", "").strip().lower()
        alt = e.get("altered_riddle", "").strip().lower()
        if orig and alt:
            keys.add((orig, alt))
    return keys


def _entry_key(entry: dict) -> tuple[str, str]:
    return (
        entry.get("original_riddle", "").strip().lower(),
        entry.get("altered_riddle", "").strip().lower(),
    )


def _display_entry(entry: dict, idx: int, total: int):
    print(f"\n{SEP}")
    print(
        f"  Entry {idx}/{total}  —  ID: {entry.get('id', '?')}  —  Type: {entry.get('type', '?')}"
    )
    print(f"  Source model: {entry.get('source', '?')}")
    review_reason = entry.get("review_reason", "")
    if review_reason:
        print(f"  ⚑  Review reason: {review_reason}")

    print(THIN)
    print(f"  Original riddle:  {entry.get('original_riddle', '')}")
    print(f"  Original answer:  {entry.get('original_answer', '')}")
    print(THIN)
    print(f"  Altered riddle:   {entry.get('altered_riddle', '')}")
    print(f"  Altered answer:   {entry.get('altered_answer', '')}")
    print(f"  Accepted answers: {entry.get('altered_accepted_answers', [])}")
    print(f"  Competing answers:{entry.get('altered_competing_answers', [])}")
    print(THIN)
    print(f"  Reasoning: {entry.get('altered_reasoning', '')}")
    print(SEP)


def _prompt_action() -> str:
    print("\n  [a]pprove  [r]eject  [e]dit answers  [s]kip  [q]uit")
    while True:
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "q"
        if choice and choice[0] in ("a", "r", "e", "s", "q"):
            return choice[0]
        print("  Invalid choice. Use a/r/e/s/q.")


def _edit_answers(entry: dict) -> dict:
    """Let the user edit accepted and competing answers."""
    entry = dict(entry)  # shallow copy

    print(f"\n  Current altered answer: {entry.get('altered_answer', '')}")
    new_answer = input("  New altered answer (Enter to keep): ").strip()
    if new_answer:
        entry["altered_answer"] = new_answer

    print(f"  Current accepted: {entry.get('altered_accepted_answers', [])}")
    new_accepted = input("  New accepted (comma-separated, Enter to keep): ").strip()
    if new_accepted:
        entry["altered_accepted_answers"] = [
            a.strip() for a in new_accepted.split(",") if a.strip()
        ]

    print(f"  Current competing: {entry.get('altered_competing_answers', [])}")
    new_competing = input("  New competing (comma-separated, Enter to keep): ").strip()
    if new_competing:
        entry["altered_competing_answers"] = [
            a.strip() for a in new_competing.split(",") if a.strip()
        ]

    return entry


def review(args):
    entries = load_jsonl(args.input)
    if not entries:
        print("No entries to review.")
        return

    pool = load_jsonl_if_exists(args.pool)
    pool_keys = _pool_keys(pool)
    used_pool_keys = _used_pool_keys(pool)
    next_pool_id = len(pool)

    human_rejected = load_jsonl_if_exists(args.human_rejected)
    human_rejected_keys = _pool_keys(human_rejected)

    # Filter out entries marked as duplicates by deduplicate.py.
    # Entries without the field (dedup not yet run) are kept for review.
    dedup_excluded = [e for e in entries if e.get("dedup_retained") is False]
    candidates = [e for e in entries if e.get("dedup_retained") is not False]

    # Filter out entries already in pool, already used in a benchmark set,
    # or already human-rejected.
    to_process = []
    for entry in candidates:
        key = _entry_key(entry)
        if (
            key not in pool_keys
            and key not in used_pool_keys
            and key not in human_rejected_keys
        ):
            to_process.append(entry)

    already_skipped = len(candidates) - len(to_process)

    if not to_process:
        print("All entries already processed. Nothing to review.")
        if dedup_excluded:
            print(
                f"({len(dedup_excluded)} entries hidden — marked as duplicates by deduplicate.py)"
            )
        return

    # Split into auto-promote candidates and flagged-for-review entries
    auto_promote_entries = [e for e in to_process if e.get("needs_review") is not True]
    flagged_entries = [e for e in to_process if e.get("needs_review") is True]

    total_pending = len(to_process)
    print(
        f"\n{total_pending} entries to process ({already_skipped} already in pool/used/rejected",
        end="",
    )

    if dedup_excluded:
        print(f", {len(dedup_excluded)} hidden as duplicates", end="")
    print(").")
    print(
        f"  {len(auto_promote_entries)} to auto-promote, "
        f"{len(flagged_entries)} flagged for interactive review.\n"
    )

    auto_promoted = approved = rejected = skipped = 0

    # --- Auto-promote pass ---
    for entry in auto_promote_entries:
        next_pool_id += 1
        pool_entry = dict(entry)
        pool_entry["id"] = f"pool_{next_pool_id:04d}"
        append_jsonl(args.pool, pool_entry)
        pool_keys.add(_entry_key(pool_entry))

        auto_promoted += 1
        altered_preview = entry.get("altered_riddle", "")[:60]
        print(f"  ✓ Auto-promoted (no review needed): {altered_preview}...")

    # --- Interactive review pass ---
    if not flagged_entries:
        print("\nAll pending entries auto-promoted. No flagged entries to review.")
    else:
        print(f"\n{THIN}")
        print(
            f"  Starting interactive review of {len(flagged_entries)} flagged entries."
        )
        print(THIN)

        for idx, entry in enumerate(flagged_entries, 1):
            _display_entry(entry, idx, len(flagged_entries))
            action = _prompt_action()

            if action == "q":
                print("\nProgress saved. You can resume later.")
                break
            elif action == "s":
                skipped += 1
                continue
            elif action == "r":
                rejected += 1
                append_jsonl(args.human_rejected, entry)
                human_rejected_keys.add(_entry_key(entry))
                print("  ✗ Rejected.")
                continue
            elif action == "e":
                entry = _edit_answers(entry)
                # After editing, ask for approval
                print("\n  Updated entry:")
                print(f"    Answer: {entry.get('altered_answer', '')}")
                print(f"    Accepted: {entry.get('altered_accepted_answers', [])}")
                print(f"    Competing: {entry.get('altered_competing_answers', [])}")
                confirm = input("  Approve this entry? [y/n]: ").strip().lower()
                if confirm != "y":
                    rejected += 1
                    append_jsonl(args.human_rejected, entry)
                    human_rejected_keys.add(_entry_key(entry))
                    print("  ✗ Rejected.")
                    continue
            # action == "a" or approved after edit

            next_pool_id += 1
            pool_entry = dict(entry)
            pool_entry["id"] = f"pool_{next_pool_id:04d}"
            append_jsonl(args.pool, pool_entry)
            pool_keys.add(_entry_key(pool_entry))
            approved += 1
            print("  ✓ Added to pool.")

    print(f"\n{SEP}")
    print(
        f"  Review summary: {auto_promoted} auto-promoted, "
        f"{approved} approved, {rejected} rejected, {skipped} skipped"
    )
    print(SEP)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Interactive review of validated riddles."
    )
    parser.add_argument("--input", default=DEFAULT_VALIDATED)
    parser.add_argument("--pool", default=DEFAULT_POOL)
    parser.add_argument(
        "--human-rejected", default=DEFAULT_HUMAN_REJECTED, dest="human_rejected"
    )
    return parser


if __name__ == "__main__":
    review(build_parser().parse_args())
