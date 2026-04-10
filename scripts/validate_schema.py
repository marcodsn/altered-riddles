#!/usr/bin/env python3
"""validate_schema.py — Validate the benchmark.jsonl schema.

Checks that all entries have required fields, no duplicate IDs,
and basic data integrity constraints are met.

Usage:
    python -m scripts.validate_schema
    python -m scripts.validate_schema --benchmark data/benchmark.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: list[str] = [
    "id",
    "original_riddle",
    "original_answer",
    "original_accepted_answers",
    "original_reasoning",
    "altered_riddle",
    "altered_answer",
    "altered_accepted_answers",
    "altered_competing_answers",
    "altered_reasoning",
    "source",
    "type",
    "set",
    "version_added",
]

VALID_TYPES: set[str] = {
    "constraint_addition",
    "context_swap",
    "meaning_shift",
    "bias_probe",
}

VALID_SETS: set[str] = {
    "fixed",
    "auxiliary",
}

DEFAULT_BENCHMARK = Path("data/benchmark.jsonl")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _load_entries(path: Path) -> list[tuple[int, dict]]:
    """Load JSONL entries, returning (line_number, parsed_dict) pairs."""
    entries: list[tuple[int, dict]] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError as exc:
                # We still record the error as a dict so the caller can report it
                entries.append((lineno, {"__parse_error__": str(exc)}))
                continue
            entries.append((lineno, entry))
    return entries


def validate(entries: list[tuple[int, dict]]) -> list[str]:
    """Run all checks and return a list of human-readable issue strings."""
    issues: list[str] = []
    seen_ids: dict[str, int] = {}  # id -> first line number

    for lineno, entry in entries:
        prefix = f"L{lineno}"

        # JSON parse errors ------------------------------------------------
        if "__parse_error__" in entry:
            issues.append(f"{prefix}: malformed JSON — {entry['__parse_error__']}")
            continue

        entry_id = entry.get("id", "<missing>")
        prefix = f"L{lineno} (id={entry_id})"

        # 1. Required fields -----------------------------------------------
        for field in REQUIRED_FIELDS:
            if field not in entry:
                issues.append(f"{prefix}: missing required field '{field}'")

        # 2. Duplicate IDs -------------------------------------------------
        if "id" in entry:
            rid = entry["id"]
            if rid in seen_ids:
                issues.append(f"{prefix}: duplicate id '{rid}' (first seen on L{seen_ids[rid]})")
            else:
                seen_ids[rid] = lineno

        # 3. altered_answer ≠ original_answer ------------------------------
        orig = entry.get("original_answer", "")
        alt = entry.get("altered_answer", "")
        if orig and alt and orig.strip().lower() == alt.strip().lower():
            issues.append(f"{prefix}: altered_answer is the same as original_answer ('{orig}')")

        # 4. Valid type ----------------------------------------------------
        entry_type = entry.get("type")
        if entry_type is not None and entry_type not in VALID_TYPES:
            issues.append(
                f"{prefix}: invalid type '{entry_type}' — expected one of {sorted(VALID_TYPES)}"
            )

        # 5. Valid set -----------------------------------------------------
        entry_set = entry.get("set")
        if entry_set is not None and entry_set not in VALID_SETS:
            issues.append(
                f"{prefix}: invalid set '{entry_set}' — expected one of {sorted(VALID_SETS)}"
            )

        # 6. version_added exists (already covered by required-field check,
        #    but we also verify it is non-empty) ---------------------------
        version = entry.get("version_added")
        if version is not None and not str(version).strip():
            issues.append(f"{prefix}: 'version_added' is present but empty")

    return issues


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the schema and data integrity of benchmark.jsonl.",
    )
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=DEFAULT_BENCHMARK,
        help=f"Path to the benchmark JSONL file (default: {DEFAULT_BENCHMARK})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    benchmark_path: Path = args.benchmark

    if not benchmark_path.exists():
        print(f"ERROR: benchmark file not found: {benchmark_path}", file=sys.stderr)
        return 1

    print(f"Validating {benchmark_path} …")
    entries = _load_entries(benchmark_path)
    print(f"  Loaded {len(entries)} entries.")

    issues = validate(entries)

    # Summary ---------------------------------------------------------------
    print()
    print("Checks performed:")
    print("  1. All required fields present")
    print("  2. No duplicate IDs")
    print("  3. altered_answer ≠ original_answer")
    print(f"  4. type ∈ {sorted(VALID_TYPES)}")
    print(f"  5. set ∈ {sorted(VALID_SETS)}")
    print("  6. version_added is non-empty")
    print()

    if issues:
        print(f"FAILED — {len(issues)} issue(s) found:\n")
        for issue in issues:
            print(f"  • {issue}")
        print()
        return 1

    print("PASSED — no issues found. ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
