#!/usr/bin/env python3
"""Per-type breakdown chart — grouped bar chart of accuracy by alteration type.

Shows per-alteration-type accuracy for the top models as a grouped bar chart.
X-axis: alteration types (constraint_addition, meaning_shift, context_swap, bias_probe)
One bar per model (top 5–8 models), colour-coded by model family.

Requires the ``per_type`` key in leaderboard.json entries (added by a parallel
change to evaluate.py).  Models without that key are silently skipped.

If no models have ``per_type`` data yet, the script falls back to computing
per-type accuracy directly from the eval result files + benchmark.jsonl.

Usage:
    python -m scripts.charts.06_perTypeBreakdown
    python scripts/charts/06_perTypeBreakdown.py --top 6 --blog
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

# Ensure the repo root is importable when running as a standalone script
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go

from scripts.charts.theme import (
    BG_COLOR,
    FONT_FAMILY,
    GRID_COLOR,
    MUTED_TEXT,
    SUBTLE_TEXT,
    TEXT_COLOR,
    add_common_args,
    blog_layout_overrides,
    get_color,
    save_chart,
)

# ── Constants ─────────────────────────────────────────────────────────

ALTERATION_TYPES = [
    "constraint_addition",
    "meaning_shift",
    "context_swap",
    "bias_probe",
]

TYPE_LABELS = {
    "constraint_addition": "Constraint\nAddition",
    "meaning_shift": "Meaning\nShift",
    "context_swap": "Context\nSwap",
    "bias_probe": "Bias\nProbe",
}

MAX_MODELS = 8


# ── Helpers ───────────────────────────────────────────────────────────


def _load_per_type_from_leaderboard(path: str, top_n: int) -> list[dict] | None:
    """Try to load per-type data from leaderboard.json.

    Returns a list of dicts with keys ``model``, ``per_type``, and
    ``rank`` — or ``None`` when no entries carry ``per_type``.
    """
    with open(path, "r") as f:
        data = json.load(f)
    data = sorted(data, key=lambda x: x["rank"])

    entries = []
    for entry in data:
        if "per_type" not in entry:
            continue
        model = entry["model"]
        if "/" in model:
            model = model.split("/")[-1]
        entries.append(
            {
                "model": model,
                "per_type": entry["per_type"],
                "rank": entry["rank"],
            }
        )

    if not entries:
        return None
    return entries[:top_n]


def _load_per_type_from_eval_files(top_n: int, leaderboard_path: str) -> list[dict] | None:
    """Fallback: compute per-type accuracy from eval files + benchmark.

    Cross-references eval details with benchmark.jsonl to recover the
    alteration type for each riddle.
    """
    repo_root = Path(__file__).resolve().parents[2]

    benchmark_path = repo_root / "data" / "benchmark.jsonl"
    if not benchmark_path.exists():
        return None

    # Build riddle_id → type mapping from benchmark
    riddle_types: dict[str, str] = {}
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
            rtype = rec.get("type", "")
            if rid and rtype:
                riddle_types[rid] = rtype

    if not riddle_types:
        return None

    # Read leaderboard for ranking & version detection
    with open(leaderboard_path, "r") as f:
        leaderboard = json.load(f)
    leaderboard = sorted(leaderboard, key=lambda x: x["rank"])

    # Determine version from VERSION file
    version_file = repo_root / "data" / "VERSION"
    version = version_file.read_text().strip() if version_file.exists() else "2604"

    eval_dir = repo_root / "results" / version
    if not eval_dir.exists():
        return None

    entries: list[dict] = []
    for lb_entry in leaderboard[: top_n * 2]:  # scan more to account for misses
        model_name = lb_entry["model"]

        # Find matching eval file
        eval_file = _find_eval_file(eval_dir, model_name)
        if eval_file is None:
            continue

        with open(eval_file, "r") as f:
            eval_data = json.load(f)

        details = eval_data.get("details", [])
        if not details:
            continue

        # Tally per-type accuracy (altered riddles only, sample_index == 1)
        type_correct: dict[str, int] = defaultdict(int)
        type_total: dict[str, int] = defaultdict(int)

        for d in details:
            if d.get("riddle_type") != "altered":
                continue
            if d.get("sample_index", 1) != 1:
                continue

            rid = d.get("riddle_id", "")
            rtype = riddle_types.get(rid, "")
            if rtype not in ALTERATION_TYPES:
                continue

            type_total[rtype] += 1
            if d.get("correct", False):
                type_correct[rtype] += 1

        if not type_total:
            continue

        per_type = {}
        for t in ALTERATION_TYPES:
            total = type_total.get(t, 0)
            correct = type_correct.get(t, 0)
            per_type[t] = round(correct / total, 4) if total > 0 else 0.0

        display_name = model_name
        if "/" in display_name:
            display_name = display_name.split("/")[-1]

        entries.append(
            {
                "model": display_name,
                "per_type": per_type,
                "rank": lb_entry["rank"],
            }
        )

    if not entries:
        return None
    return entries[:top_n]


def _find_eval_file(eval_dir: Path, model_name: str) -> Path | None:
    """Locate the eval JSON for *model_name* inside *eval_dir*."""
    # Normalise model name to match filename conventions
    safe = model_name.replace("/", "_").replace(":", "_")
    candidates = sorted(eval_dir.glob("*_eval.json"))
    for c in candidates:
        stem = c.stem  # e.g. "gemma-4-31b-it_reasoning_temp1.0_eval"
        if safe.lower() in stem.lower():
            return c
    # Looser match: try the first portion before any colon/slash
    base = model_name.split(":")[0].split("/")[-1]
    for c in candidates:
        if base.lower() in c.stem.lower():
            return c
    return None


# ── Chart ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-type breakdown grouped bar chart")
    add_common_args(parser)
    parser.add_argument(
        "--max-models",
        type=int,
        default=MAX_MODELS,
        help="Maximum number of models to display (default: 8)",
    )
    args = parser.parse_args()

    top_n = min(args.top, args.max_models)

    # 1) Try leaderboard per_type data
    entries = _load_per_type_from_leaderboard(args.leaderboard, top_n)

    # 2) Fallback to eval files
    if entries is None:
        print(
            "No per_type data in leaderboard.json — falling back to eval files + benchmark.jsonl"
        )
        entries = _load_per_type_from_eval_files(top_n, args.leaderboard)

    if entries is None or len(entries) == 0:
        print("No per-type data available. Skipping chart generation.")
        return

    # Trim to max models
    entries = entries[:top_n]

    fig = go.Figure()

    for entry in entries:
        model = entry["model"]
        per_type = entry["per_type"]
        accuracies = [per_type.get(t, 0) * 100 for t in ALTERATION_TYPES]
        labels = [TYPE_LABELS.get(t, t) for t in ALTERATION_TYPES]

        fig.add_trace(
            go.Bar(
                name=model,
                x=labels,
                y=accuracies,
                marker=dict(
                    color=get_color(model),
                    line=dict(width=0.5, color="#ffffff"),
                ),
                text=[f"{v:.0f}" for v in accuracies],
                textposition="outside",
                textfont=dict(size=10, family=FONT_FAMILY, color=MUTED_TEXT),
            )
        )

    fig.update_layout(
        barmode="group",
        font=dict(color=TEXT_COLOR, family=FONT_FAMILY),
        title=dict(
            text="PER-TYPE ACCURACY BREAKDOWN<br>"
            f"<span style='font-size:12px;font-weight:normal;color:{SUBTLE_TEXT}'>"
            "Accuracy on altered riddles grouped by alteration type "
            f"(top {len(entries)} models)"
            "</span>",
            font=dict(family=FONT_FAMILY, size=16, color=TEXT_COLOR),
        ),
        xaxis=dict(
            title=None,
            tickfont=dict(size=11, family=FONT_FAMILY, color=TEXT_COLOR),
            showgrid=False,
        ),
        yaxis=dict(
            title=dict(
                text="Accuracy (%)",
                font=dict(size=12, family=FONT_FAMILY, color=MUTED_TEXT),
            ),
            range=[0, 105],
            showgrid=True,
            gridcolor=GRID_COLOR,
            gridwidth=1,
            tickfont=dict(size=11, family=FONT_FAMILY, color=MUTED_TEXT),
            dtick=20,
        ),
        plot_bgcolor=BG_COLOR,
        paper_bgcolor=BG_COLOR,
        margin=dict(l=60, r=20, t=100, b=60),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.35,
            xanchor="center",
            x=0.5,
            font=dict(size=10, family=FONT_FAMILY, color=TEXT_COLOR),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=600,
        bargap=0.20,
        bargroupgap=0.05,
    )

    if args.blog:
        fig.update_layout(**blog_layout_overrides())

    output_name = "per_type_breakdown.png"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(args.output, scale=args.scale)
        print(f"Chart saved: {args.output}")
    else:
        save_chart(fig, output_name, blog=args.blog, scale=args.scale)


if __name__ == "__main__":
    main()
