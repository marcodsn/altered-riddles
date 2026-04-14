"""annotate_competing.py — Human annotation of competing answers.

Interactive CLI tool that walks through every competing answer in the
benchmark and lets an annotator classify each one as defensible, not
defensible, or promote it to a full accepted answer.

Annotations are persisted to a JSON file so the session can be resumed
at any time.

Examples
────────
    python -m scripts.annotate_competing
    python -m scripts.annotate_competing --benchmark data/benchmark.jsonl
    python -m scripts.annotate_competing --report-only
    python -m scripts.annotate_competing --apply
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from scripts.core.config import DEFAULT_BENCHMARK, DEFAULT_RESULTS
from scripts.core.io_utils import load_jsonl, write_json, write_jsonl

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = os.path.join(DEFAULT_RESULTS, "competing_annotations.json")

# Valid interactive responses
VALID_CHOICES = {"d", "n", "p", "s", "q"}

# ── Separator helpers ─────────────────────────────────────────────────

THICK_SEP = "═" * 72
THIN_SEP = "─" * 72


# ── Persistence ───────────────────────────────────────────────────────


def _load_annotations(path: str | Path) -> dict[str, Any]:
    """Load existing annotations from *path*, or return an empty structure."""
    filepath = Path(path)
    if not filepath.exists():
        return {"annotations": [], "promotions": []}
    with open(filepath, encoding="utf-8") as fh:
        data = json.load(fh)
    # Ensure expected keys exist
    data.setdefault("annotations", [])
    data.setdefault("promotions", [])
    return data


def _save_annotations(path: str | Path, data: dict[str, Any]) -> None:
    """Persist annotation data to *path*."""
    write_json(path, data)


def _already_annotated(data: dict[str, Any]) -> set[tuple[str, str]]:
    """Return the set of (riddle_id, competing_answer) pairs already done."""
    seen: set[tuple[str, str]] = set()
    for ann in data["annotations"]:
        seen.add((ann["riddle_id"], ann["competing_answer"]))
    return seen


def _already_promoted(data: dict[str, Any]) -> set[tuple[str, str]]:
    """Return the set of (riddle_id, competing_answer) pairs promoted."""
    return {(p["riddle_id"], p["competing_answer"]) for p in data["promotions"]}


# ── Display helpers ───────────────────────────────────────────────────


def _display_entry(entry: dict[str, Any]) -> None:
    """Print the riddle context for an entry."""
    print(f"\n{THICK_SEP}")
    print(f"  Riddle ID:          {entry['id']}")
    print(THIN_SEP)
    print(f"  Altered riddle:     {entry['altered_riddle']}")
    print(f"  Altered answer:     {entry['altered_answer']}")
    print(f"  Accepted answers:   {', '.join(entry.get('altered_accepted_answers', []))}")
    print(THIN_SEP)
    reasoning = entry.get("altered_reasoning", "")
    # Wrap long reasoning for readability
    print(f"  Reasoning:          {reasoning}")
    print(THICK_SEP)


def _display_competing(index: int, total: int, answer: str) -> None:
    """Print a single competing answer for annotation."""
    print(f"\n  Competing answer [{index}/{total}]: {answer}")
    print()
    print("    [d]efensible   — valid alternative answer")
    print("    [n]ot defensible — not a valid answer")
    print("    [p]romote      — promote to accepted answers (full credit)")
    print("    [s]kip         — skip this entry for now")
    print("    [q]uit         — save progress and exit")


def _prompt() -> str:
    """Read a single-character choice from the annotator."""
    while True:
        try:
            choice = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return "q"
        if choice and choice[0] in VALID_CHOICES:
            return choice[0]
        print(f"    Invalid choice '{choice}'. Please enter d, n, p, s, or q.")


# ── Summary / report ─────────────────────────────────────────────────


def _print_summary(data: dict[str, Any]) -> None:
    """Print annotation statistics."""
    annotations = data["annotations"]
    promotions = data["promotions"]

    total = len(annotations)
    if total == 0:
        print("\nNo competing answers have been reviewed yet.")
        return

    defensible = sum(1 for a in annotations if a["label"] == "defensible")
    not_defensible = sum(1 for a in annotations if a["label"] == "not_defensible")
    promoted = len(promotions)
    skipped = sum(1 for a in annotations if a["label"] == "skipped")

    # Total reviewed excludes skipped entries for the weight calculation
    reviewed = defensible + not_defensible + promoted

    print(f"\n{THICK_SEP}")
    print("  Annotation Summary")
    print(THIN_SEP)
    print(f"  Total annotations recorded:  {total}")
    if skipped:
        print(f"    (of which skipped:         {skipped})")
    print(f"  Reviewed (non-skipped):      {reviewed}")
    print()
    if reviewed > 0:
        d_pct = defensible / reviewed * 100
        n_pct = not_defensible / reviewed * 100
        p_pct = promoted / reviewed * 100
        print(f"  Defensible:                  {defensible:4d}  ({d_pct:5.1f}%)")
        print(f"  Not defensible:              {not_defensible:4d}  ({n_pct:5.1f}%)")
        print(f"  Promoted to accepted:        {promoted:4d}  ({p_pct:5.1f}%)")
        weight = (defensible + promoted) / reviewed if reviewed else 0.0
        print(THIN_SEP)
        print(f"  Suggested --competing-weight: {weight:.4f}")
    print(THICK_SEP)


# ── Benchmark mutation ────────────────────────────────────────────────


def _apply_promotions_to_entries(
    entries: list[dict[str, Any]],
    promotions: list[dict[str, Any]],
) -> int:
    """Mutate *entries* in place, promoting competing answers to accepted.

    Returns the number of promotions actually applied (some may already
    have been applied in a previous run).
    """
    # Build a lookup: riddle_id → set of answers to promote
    to_promote: dict[str, set[str]] = {}
    for p in promotions:
        to_promote.setdefault(p["riddle_id"], set()).add(p["competing_answer"])

    applied = 0
    for entry in entries:
        rid = entry.get("id", "")
        if rid not in to_promote:
            continue
        accepted: list[str] = entry.get("altered_accepted_answers", [])
        competing: list[str] = entry.get("altered_competing_answers", [])
        for ans in to_promote[rid]:
            # Only apply if not already accepted
            if ans not in accepted:
                accepted.append(ans)
                applied += 1
            if ans in competing:
                competing.remove(ans)
        entry["altered_accepted_answers"] = accepted
        entry["altered_competing_answers"] = competing

    return applied


# ── Interactive loop ──────────────────────────────────────────────────


def _run_interactive(
    entries: list[dict[str, Any]],
    ann_data: dict[str, Any],
    output_path: str | Path,
    benchmark_path: str | Path,
) -> None:
    """Main interactive annotation loop."""
    done = _already_annotated(ann_data)

    # Collect work items: (entry, competing_answer)
    work: list[tuple[dict[str, Any], str]] = []
    for entry in entries:
        competing = entry.get("altered_competing_answers", [])
        if not competing:
            continue
        for ans in competing:
            rid = entry.get("id", "")
            if (rid, ans) not in done:
                work.append((entry, ans))

    if not work:
        print("\nAll competing answers have been annotated. Nothing to do.")
        _print_summary(ann_data)
        return

    print(f"\n{len(work)} competing answer(s) remaining for annotation.\n")

    current_entry_id: str | None = None
    quit_requested = False

    for wi, (entry, ans) in enumerate(work, start=1):
        rid = entry["id"]

        # Show entry context when we move to a new riddle
        if rid != current_entry_id:
            _display_entry(entry)
            current_entry_id = rid

        # Count how many competing answers this entry has total
        all_competing = entry.get("altered_competing_answers", [])
        # Figure out the 1-based index of this answer among the entry's competing list
        try:
            idx = all_competing.index(ans) + 1
        except ValueError:
            idx = 1
        _display_competing(idx, len(all_competing), ans)

        choice = _prompt()

        if choice == "q":
            quit_requested = True
            break
        elif choice == "s":
            ann_data["annotations"].append(
                {"riddle_id": rid, "competing_answer": ans, "label": "skipped"}
            )
        elif choice == "d":
            ann_data["annotations"].append(
                {"riddle_id": rid, "competing_answer": ans, "label": "defensible"}
            )
            print("    ✓ Marked as defensible.")
        elif choice == "n":
            ann_data["annotations"].append(
                {"riddle_id": rid, "competing_answer": ans, "label": "not_defensible"}
            )
            print("    ✗ Marked as not defensible.")
        elif choice == "p":
            ann_data["annotations"].append(
                {"riddle_id": rid, "competing_answer": ans, "label": "promoted"}
            )
            ann_data["promotions"].append({"riddle_id": rid, "competing_answer": ans})
            # Immediately apply the promotion to the in-memory entry
            accepted = entry.get("altered_accepted_answers", [])
            competing = entry.get("altered_competing_answers", [])
            if ans not in accepted:
                accepted.append(ans)
            if ans in competing:
                competing.remove(ans)
            entry["altered_accepted_answers"] = accepted
            entry["altered_competing_answers"] = competing
            print("    ⬆ Promoted to accepted answers.")

        # Save after every annotation for crash safety
        _save_annotations(output_path, ann_data)

    # Write benchmark with any promotions applied
    write_jsonl(benchmark_path, entries)
    _save_annotations(output_path, ann_data)

    if quit_requested:
        print("\nProgress saved. You can resume later.")

    _print_summary(ann_data)


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="annotate_competing",
        description=(
            "Interactive annotation tool for competing answers in the Altered Riddles benchmark."
        ),
    )
    parser.add_argument(
        "--benchmark",
        default=DEFAULT_BENCHMARK,
        help=f"Path to the benchmark JSONL file (default: {DEFAULT_BENCHMARK})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Path to the annotations JSON file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        default=False,
        help="Print annotation summary and exit (no interactive mode).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help=(
            "Apply all recorded promotions to the benchmark file without "
            "entering interactive mode."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = build_parser()
    args = parser.parse_args(argv)

    ann_data = _load_annotations(args.output)

    # ── report-only mode ──────────────────────────────────────────────
    if args.report_only:
        _print_summary(ann_data)
        return

    # ── Load benchmark ────────────────────────────────────────────────
    entries = load_jsonl(args.benchmark)

    if not entries:
        print("Benchmark is empty — nothing to annotate.")
        return

    # ── apply mode ────────────────────────────────────────────────────
    if args.apply:
        promotions = ann_data.get("promotions", [])
        if not promotions:
            print("No promotions recorded — nothing to apply.")
            return
        applied = _apply_promotions_to_entries(entries, promotions)
        write_jsonl(args.benchmark, entries)
        print(f"Applied {applied} promotion(s) to {args.benchmark}.")
        _print_summary(ann_data)
        return

    # ── Check for work ────────────────────────────────────────────────
    has_competing = any(entry.get("altered_competing_answers") for entry in entries)
    if not has_competing:
        print("No entries with competing answers found in the benchmark.")
        return

    # ── Interactive mode ──────────────────────────────────────────────
    _run_interactive(entries, ann_data, args.output, args.benchmark)


if __name__ == "__main__":
    main()
