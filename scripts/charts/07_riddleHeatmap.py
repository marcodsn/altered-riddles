#!/usr/bin/env python3
"""Riddle heatmap data export — per-riddle results across all models.

Instead of a visual heatmap (which would be unreadable at 250 riddles),
this script exports a structured JSON file with per-riddle results across
all evaluated models.  The output is designed to be consumed by downstream
tools, dashboards, or manual inspection.

Output: ``data/images/riddle_heatmap.json``

Each entry contains:
  - riddle_id, type, difficulty
  - results: {model_name: outcome} where outcome is one of
    "correct", "competing", "original_answer", or "incorrect"

Usage:
    python -m scripts.charts.07_riddleHeatmap
    python scripts/charts/07_riddleHeatmap.py --version 2604
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Ensure the repo root is importable when running as a standalone script
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.charts.theme import (
    IMAGE_DIR,
    add_common_args,
)

# ── Constants ─────────────────────────────────────────────────────────

OUTPUT_NAME = "riddle_heatmap.json"


# ── Helpers ───────────────────────────────────────────────────────────


def _read_version() -> str:
    """Read the benchmark version from ``data/VERSION``."""
    repo_root = Path(__file__).resolve().parents[2]
    vf = repo_root / "data" / "VERSION"
    if vf.exists():
        return vf.read_text().strip()
    return "2604"


def _load_benchmark_metadata(repo_root: Path) -> dict[str, dict]:
    """Build a mapping of riddle_id → {type, ...} from benchmark.jsonl."""
    benchmark_path = repo_root / "data" / "benchmark.jsonl"
    if not benchmark_path.exists():
        print(f"Warning: benchmark file not found at {benchmark_path}")
        return {}

    riddles: dict[str, dict] = {}
    with open(benchmark_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = rec.get("id", "")
            if rid:
                riddles[rid] = {
                    "type": rec.get("type", ""),
                    "set": rec.get("set", ""),
                    "source": rec.get("source", ""),
                }
    return riddles


def _load_difficulty_scores(repo_root: Path, version: str) -> dict[str, float]:
    """Load per-riddle difficulty scores if available.

    Looks for ``results/{version}/riddle_difficulty.json``.
    Returns an empty dict when the file does not exist.
    """
    difficulty_path = repo_root / "results" / version / "riddle_difficulty.json"
    if not difficulty_path.exists():
        return {}

    with open(difficulty_path, "r") as f:
        data = json.load(f)

    # Support both list-of-dicts and dict-keyed-by-id formats
    if isinstance(data, list):
        return {
            entry.get("riddle_id", entry.get("id", "")): entry.get("difficulty", 0.0)
            for entry in data
            if entry.get("riddle_id") or entry.get("id")
        }
    if isinstance(data, dict):
        # Could be {riddle_id: difficulty_score} or {riddle_id: {difficulty: ...}}
        result: dict[str, float] = {}
        for k, v in data.items():
            if isinstance(v, (int, float)):
                result[k] = float(v)
            elif isinstance(v, dict):
                result[k] = float(v.get("difficulty", 0.0))
        return result
    return {}


def _classify_outcome(detail: dict) -> str:
    """Map an eval detail record to a human-readable outcome string."""
    if detail.get("correct", False):
        return "correct"
    if detail.get("gave_original_answer", False):
        return "original_answer"
    # Check for competing answer: score > 0 but not fully correct
    score = detail.get("score", 0.0)
    if score is not None and score > 0 and not detail.get("correct", False):
        return "competing"
    return "incorrect"


def _compute_difficulty_from_evals(
    riddle_results: dict[str, dict[str, str]],
) -> dict[str, float]:
    """Compute a simple difficulty score: 1 − (fraction of models that got it right).

    A riddle that no model solved has difficulty 1.0; one that every model
    solved has difficulty 0.0.
    """
    difficulty: dict[str, float] = {}
    for rid, results in riddle_results.items():
        if not results:
            difficulty[rid] = 1.0
            continue
        n_correct = sum(1 for v in results.values() if v == "correct")
        difficulty[rid] = round(1.0 - n_correct / len(results), 4)
    return difficulty


def _clean_model_name(raw: str) -> str:
    """Produce a readable model name from an eval-file model field."""
    name = raw
    if "/" in name:
        name = name.split("/")[-1]
    return name


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Export per-riddle heatmap data as JSON")
    add_common_args(parser)
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Benchmark version (default: read from data/VERSION)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    version = args.version or _read_version()

    eval_dir = repo_root / "results" / version
    if not eval_dir.exists():
        print(f"Error: eval directory not found: {eval_dir}")
        sys.exit(1)

    eval_files = sorted(eval_dir.glob("*_eval.json"))
    if not eval_files:
        print(f"Error: no eval files found in {eval_dir}")
        sys.exit(1)

    # Load benchmark metadata (type, set, source)
    benchmark_meta = _load_benchmark_metadata(repo_root)

    # Load external difficulty scores (may be empty)
    external_difficulty = _load_difficulty_scores(repo_root, version)

    # Collect per-riddle results across all models
    # riddle_id → {model_name: outcome}
    riddle_results: dict[str, dict[str, str]] = defaultdict(dict)
    all_riddle_ids: set[str] = set()

    for eval_file in eval_files:
        try:
            with open(eval_file, "r") as f:
                eval_data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: skipping {eval_file.name}: {exc}")
            continue

        model_name = _clean_model_name(eval_data.get("model", eval_file.stem))
        details = eval_data.get("details", [])

        for detail in details:
            # Only include altered riddle results (sample_index 1 = first sample)
            if detail.get("riddle_type") != "altered":
                continue
            if detail.get("sample_index", 1) != 1:
                continue

            rid = detail.get("riddle_id", "")
            if not rid:
                continue

            all_riddle_ids.add(rid)
            outcome = _classify_outcome(detail)
            riddle_results[rid][model_name] = outcome

    if not riddle_results:
        print("No altered-riddle results found across eval files.")
        sys.exit(1)

    # Compute difficulty from eval data if no external source available
    if external_difficulty:
        difficulty_scores = external_difficulty
    else:
        difficulty_scores = _compute_difficulty_from_evals(riddle_results)

    # Build output list sorted by riddle ID
    sorted_ids = sorted(
        all_riddle_ids,
        key=lambda x: (int(x.split("_")[1]) if "_" in x and x.split("_")[1].isdigit() else 0),
    )

    output: list[dict] = []
    for rid in sorted_ids:
        meta = benchmark_meta.get(rid, {})
        entry = {
            "riddle_id": rid,
            "type": meta.get("type", "unknown"),
            "difficulty": round(difficulty_scores.get(rid, 0.0), 4),
            "results": dict(sorted(riddle_results.get(rid, {}).items())),
        }
        output.append(entry)

    # Write output
    out_dir = Path(IMAGE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / OUTPUT_NAME

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Summary
    n_riddles = len(output)
    n_models = len({m for entry in output for m in entry["results"]})
    print(f"Heatmap data exported: {out_path}")
    print(f"  Riddles: {n_riddles}")
    print(f"  Models:  {n_models}")

    # Type distribution
    type_counts: dict[str, int] = defaultdict(int)
    for entry in output:
        type_counts[entry["type"]] += 1
    print("  By type:")
    for t, c in sorted(type_counts.items()):
        print(f"    {t}: {c}")

    # Outcome distribution
    outcome_counts: dict[str, int] = defaultdict(int)
    for entry in output:
        for outcome in entry["results"].values():
            outcome_counts[outcome] += 1
    total_outcomes = sum(outcome_counts.values())
    print(f"  Total outcomes: {total_outcomes}")
    for o, c in sorted(outcome_counts.items()):
        pct = c / total_outcomes * 100 if total_outcomes else 0
        print(f"    {o}: {c} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
