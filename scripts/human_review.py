#!/usr/bin/env python3
"""human_review.py — Interactive review of validated riddles.

Walk through validated riddles one by one and approve/reject/edit them.
Approved entries are added to pool.jsonl.

Usage:
    python -m scripts.human_review
    python -m scripts.human_review --input data/generated/validated.jsonl
"""

from __future__ import annotations

import argparse
import logging

from scripts.core.config import DEFAULT_POOL, DEFAULT_VALIDATED
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


def _display_entry(entry: dict, idx: int, total: int):
    print(f"\n{SEP}")
    print(
        f"  Entry {idx}/{total}  —  ID: {entry.get('id', '?')}  —  Type: {entry.get('type', '?')}"
    )
    print(f"  Source model: {entry.get('source', '?')}")
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
    next_pool_id = len(pool)

    # Filter out entries marked as duplicates by deduplicate.py.
    # Entries without the field (dedup not yet run) are kept for review.
    dedup_excluded = [e for e in entries if e.get("dedup_retained") is False]
    candidates = [e for e in entries if e.get("dedup_retained") is not False]

    # Filter out entries already in pool
    to_review = []
    for entry in candidates:
        orig = entry.get("original_riddle", "").strip().lower()
        alt = entry.get("altered_riddle", "").strip().lower()
        if (orig, alt) not in pool_keys:
            to_review.append(entry)

    if not to_review:
        print("All entries already in pool. Nothing to review.")
        if dedup_excluded:
            print(
                f"({len(dedup_excluded)} entries hidden — marked as duplicates by deduplicate.py)"
            )
        return

    already_in_pool = len(candidates) - len(to_review)
    print(
        f"\n{len(to_review)} entries to review ({already_in_pool} already in pool",
        end="",
    )
    if dedup_excluded:
        print(f", {len(dedup_excluded)} hidden as duplicates", end="")
    print(").\n")

    approved = rejected = skipped = 0

    for idx, entry in enumerate(to_review, 1):
        _display_entry(entry, idx, len(to_review))
        action = _prompt_action()

        if action == "q":
            print("\nProgress saved. You can resume later.")
            break
        elif action == "s":
            skipped += 1
            continue
        elif action == "r":
            rejected += 1
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
                print("  ✗ Rejected.")
                continue
        # action == "a" or approved after edit

        next_pool_id += 1
        entry["id"] = f"pool_{next_pool_id:04d}"
        append_jsonl(args.pool, entry)
        pool_keys.add(
            (
                entry.get("original_riddle", "").strip().lower(),
                entry.get("altered_riddle", "").strip().lower(),
            )
        )
        approved += 1
        print("  ✓ Added to pool.")

    print(f"\n{SEP}")
    print(
        f"  Review summary: {approved} approved, {rejected} rejected, {skipped} skipped"
    )
    print(SEP)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Interactive review of validated riddles."
    )
    parser.add_argument("--input", default=DEFAULT_VALIDATED)
    parser.add_argument("--pool", default=DEFAULT_POOL)
    return parser


if __name__ == "__main__":
    review(build_parser().parse_args())
