#!/usr/bin/env python3
"""leaderboard.py — Generate the benchmark leaderboard.

Main metric: conditioned override rate (lower is better).
Also reports original accuracy as a knowledge metric.

Usage:
    python -m scripts.leaderboard
    python -m scripts.leaderboard --results-dir results
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
from collections import defaultdict
from pathlib import Path

from scripts.core.config import DEFAULT_BENCHMARK, DEFAULT_BENCHMARK_FIXED, DEFAULT_RESULTS
from scripts.core.io_utils import load_jsonl_if_exists, write_json

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

FIXED_PATH = DEFAULT_BENCHMARK_FIXED


def _bootstrap_ci95(scores: list[float], B: int = 2000, seed: int = 42) -> float:
    """Compute half-width of 95% CI via bootstrap."""
    n = len(scores)
    if n == 0:
        return 0.0
    if n < 5:
        p = sum(scores) / n
        return round(1.96 * math.sqrt(p * (1 - p) / n), 4)

    rng = random.Random(seed)
    means = []
    for _ in range(B):
        sample = rng.choices(scores, k=n)
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(B * 0.025)]
    hi = means[int(B * 0.975)]
    return round((hi - lo) / 2, 4)


def _clustered_bootstrap_ci95(
    cluster_scores: list[tuple[str, float]],
    B: int = 2000,
    seed: int = 42,
) -> float:
    """CI95 via cluster-level bootstrap (clusters = original riddles)."""
    clusters: dict[str, list[float]] = defaultdict(list)
    for cid, score in cluster_scores:
        clusters[cid].append(score)

    cluster_ids = list(clusters.keys())
    n_clusters = len(cluster_ids)
    n_total = len(cluster_scores)

    if n_total == 0:
        return 0.0
    overall = sum(s for _, s in cluster_scores) / n_total
    if n_clusters < 5:
        return round(1.96 * math.sqrt(overall * (1 - overall) / n_total), 4)

    rng = random.Random(seed)
    means = []
    for _ in range(B):
        sampled = rng.choices(cluster_ids, k=n_clusters)
        values = []
        for cid in sampled:
            values.extend(clusters[cid])
        means.append(sum(values) / len(values) if values else 0.0)
    means.sort()
    lo = means[int(B * 0.025)]
    hi = means[int(B * 0.975)]
    return round((hi - lo) / 2, 4)


def build_leaderboard(all_results: list[dict], benchmark_lookup: dict | None = None) -> list[dict]:
    rows = []
    for result in all_results:
        s = result["summary"]
        row = {
            "model": result["model"],
            "provider": result.get("provider", ""),
            "quantization": result.get("quantization", ""),
            "original_accuracy": s["original_accuracy"],
            "altered_accuracy": s["altered_accuracy"],
            "pattern_override_rate": s["pattern_override_rate"],
            "conditioned_override_rate": s["conditioned_override_rate"],
            "conditioned_override_total": s.get("conditioned_override_total", 0),
            "total_input_tokens": s.get("total_input_tokens", 0),
            "total_output_tokens": s.get("total_output_tokens", 0),
        }

        # CI95 for conditioned override
        if benchmark_lookup:
            altered_s1 = [
                d
                for d in result.get("details", [])
                if d.get("riddle_type") == "altered" and d.get("sample_index", 1) == 1
            ]
            co_scores = []
            for d in altered_s1:
                entry = benchmark_lookup.get(d["riddle_id"], {})
                cluster = entry.get("original_riddle", d["riddle_id"])
                co_scores.append((cluster, 1.0 if d.get("gave_original_answer") else 0.0))
            row["conditioned_override_ci95"] = _clustered_bootstrap_ci95(co_scores)

            acc_scores = [
                (c, 1.0 if d["correct"] else 0.0) for d, (c, _) in zip(altered_s1, co_scores)
            ]
            row["altered_accuracy_ci95"] = _clustered_bootstrap_ci95(acc_scores)
        else:
            n = s.get("altered_total", 0)
            if n > 0:
                p = s["conditioned_override_rate"]
                row["conditioned_override_ci95"] = round(1.96 * math.sqrt(p * (1 - p) / n), 4)
                p2 = s["altered_accuracy"]
                row["altered_accuracy_ci95"] = round(1.96 * math.sqrt(p2 * (1 - p2) / n), 4)
            else:
                row["conditioned_override_ci95"] = 0.0
                row["altered_accuracy_ci95"] = 0.0

        rows.append(row)

    # Sort by conditioned_override_rate ascending (lower = better)
    rows.sort(key=lambda r: (r["conditioned_override_rate"], -r["altered_accuracy"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


def print_leaderboard(leaderboard):
    def pct(v):
        return f"{v * 100:5.1f}%"

    def ci(v):
        return f"+/-{v * 100:.1f}%"

    print()
    print("=" * 100)
    print("ALTERED RIDDLES LEADERBOARD")
    print("=" * 100)
    print(
        f"{'Rank':<5} {'Model':<25} {'Orig Acc':>10} {'Alt Acc':>10} "
        f"{'Cond Override':>15} {'Override':>10} {'Tokens':>10}"
    )
    print("-" * 100)
    for r in leaderboard:
        co = pct(r["conditioned_override_rate"])
        co_ci = ci(r.get("conditioned_override_ci95", 0))
        print(
            f"{r['rank']:<5} {r['model']:<25} {pct(r['original_accuracy']):>10} "
            f"{pct(r['altered_accuracy']):>10} {co + ' ' + co_ci:>15} "
            f"{pct(r['pattern_override_rate']):>10} {r.get('total_output_tokens', 0):>10,}"
        )
    print("=" * 100)
    print()


def generate_markdown(leaderboard, output_path):
    lines = [
        "# Altered Riddles Leaderboard",
        "",
        f"> {len(leaderboard)} models evaluated. "
        "Main metric: **Conditioned Override Rate** (lower = better).",
        "",
        "| Rank | Model | Orig Acc | Alt Acc | Cond Override | CI95 | Override Rate |",
        "|------|-------|----------|---------|---------------|------|--------------|",
    ]
    for r in leaderboard:
        lines.append(
            f"| {r['rank']} | {r['model']} "
            f"| {r['original_accuracy'] * 100:.1f}% "
            f"| {r['altered_accuracy'] * 100:.1f}% "
            f"| {r['conditioned_override_rate'] * 100:.1f}% "
            f"| +/-{r.get('conditioned_override_ci95', 0) * 100:.1f}% "
            f"| {r['pattern_override_rate'] * 100:.1f}% |"
        )
    lines.append("")
    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def run_leaderboard(args):
    results_dir = Path(args.results_dir)

    # Load results
    all_results_path = results_dir / "all_results.json"
    if all_results_path.exists():
        with open(all_results_path) as f:
            all_results = json.load(f)
    else:
        # Fall back to individual eval files
        eval_files = sorted(results_dir.glob("*_eval.json"))
        if not eval_files:
            logger.error("No evaluation results found in %s", results_dir)
            raise SystemExit(1)
        all_results = []
        for ef in eval_files:
            with open(ef) as f:
                all_results.append(json.load(f))

    # Load benchmark for clustering
    bench = load_jsonl_if_exists(args.benchmark)
    fixed = load_jsonl_if_exists(FIXED_PATH)
    all_bench = bench + fixed
    benchmark_lookup = {e.get("id", ""): e for e in all_bench} if all_bench else None

    leaderboard = build_leaderboard(all_results, benchmark_lookup)

    # Save
    write_json(results_dir / "leaderboard.json", leaderboard)
    print_leaderboard(leaderboard)
    md_path = results_dir / "LEADERBOARD.md"
    generate_markdown(leaderboard, md_path)
    logger.info("Leaderboard JSON: %s", results_dir / "leaderboard.json")
    logger.info("Leaderboard MD:   %s", md_path)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate the benchmark leaderboard.")
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS)
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    return parser.parse_args()


if __name__ == "__main__":
    run_leaderboard(parse_args())
