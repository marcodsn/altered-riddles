#!/usr/bin/env python3
"""leaderboard.py — Generate the benchmark leaderboard.

Main metric: conditioned override rate (lower is better),
computed only over altered riddles whose original variant the model solves.
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
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from scripts.core.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_BENCHMARK_FIXED,
    DEFAULT_RESULTS,
)
from scripts.core.io_utils import load_jsonl_if_exists, write_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

FIXED_PATH = DEFAULT_BENCHMARK_FIXED


def _expected_coverage(benchmark_entries: list[dict]) -> tuple[set[str], set[str]]:
    """Return expected altered IDs and deduplicated original IDs for a full run."""
    expected_altered_ids: set[str] = set()
    expected_original_ids: set[str] = set()
    seen_originals: set[str] = set()

    for entry in benchmark_entries:
        riddle_id = entry.get("id", "")
        if not riddle_id:
            continue

        expected_altered_ids.add(riddle_id)

        original_riddle = entry.get("original_riddle", "")
        if original_riddle and original_riddle not in seen_originals:
            seen_originals.add(original_riddle)
            expected_original_ids.add(riddle_id)

    return expected_altered_ids, expected_original_ids


def _filter_complete_results(
    all_results: list[dict],
    expected_altered_ids: set[str],
    expected_original_ids: set[str],
) -> list[dict]:
    """Keep only models with at least one evaluated result for every benchmark riddle."""
    if not expected_altered_ids and not expected_original_ids:
        return all_results

    filtered_results = []
    for result in all_results:
        details = result.get("details", [])
        altered_ids = {
            d.get("riddle_id", "")
            for d in details
            if d.get("riddle_type") == "altered" and d.get("riddle_id")
        }
        original_ids = {
            d.get("riddle_id", "")
            for d in details
            if d.get("riddle_type") == "original" and d.get("riddle_id")
        }

        missing_altered = expected_altered_ids - altered_ids
        missing_original = expected_original_ids - original_ids
        if missing_altered or missing_original:
            logger.warning(
                "Skipping incomplete leaderboard entry for %s: missing %d/%d altered and %d/%d original riddles.",
                result.get("model", "unknown"),
                len(missing_altered),
                len(expected_altered_ids),
                len(missing_original),
                len(expected_original_ids),
            )
            continue

        filtered_results.append(result)

    return filtered_results


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


def _paired_diff_sig(
    per_riddle_a: list[dict],
    per_riddle_b: list[dict],
    B: int = 2000,
    seed: int = 42,
) -> int:
    """
    Paired clustered bootstrap on the COR difference (A - B) restricted to
    riddles where *both* models solved the original.

    Returns:
        +1 if A is significantly better than B (A's COR significantly lower),
        -1 if B is significantly better than A,
         0 if inconclusive.
    """
    a_by_id = {
        r["riddle_id"]: r for r in per_riddle_a if r.get("original_solved")
    }
    b_by_id = {
        r["riddle_id"]: r for r in per_riddle_b if r.get("original_solved")
    }
    shared_ids = sorted(set(a_by_id.keys()) & set(b_by_id.keys()))

    diffs_by_cluster: dict[str, list[float]] = defaultdict(list)
    for rid in shared_ids:
        ra = a_by_id[rid]
        rb = b_by_id[rid]
        diff = ra["override_mean"] - rb["override_mean"]
        cluster = ra.get("cluster", rid)
        diffs_by_cluster[cluster].append(diff)

    cluster_ids = list(diffs_by_cluster.keys())
    n_clusters = len(cluster_ids)
    n_total = sum(len(v) for v in diffs_by_cluster.values())

    if n_clusters < 5 or n_total == 0:
        return 0

    rng = random.Random(seed)
    means = []
    for _ in range(B):
        sampled = rng.choices(cluster_ids, k=n_clusters)
        values = []
        for cid in sampled:
            values.extend(diffs_by_cluster[cid])
        if values:
            means.append(sum(values) / len(values))
    if not means:
        return 0
    means.sort()
    lo = means[int(B * 0.025)]
    hi = means[int(B * 0.975)]

    if hi < 0:
        return +1  # A significantly lower -> A better
    if lo > 0:
        return -1  # A significantly higher -> B better
    return 0


def _compute_rank_spread(leaderboard: list[dict]) -> list[dict]:
    """
    Compute plausible rank range from paired bootstrap tests on COR.

    Lower conditioned_override_rate is better.

    For each pair (A, B), the paired clustered bootstrap tests whether
    A's COR is significantly lower (or higher) than B's, using only the
    riddles where both models solved the original. This cancels per-riddle
    difficulty and yields tighter rank spreads than independent CIs.

    rank_best:
        1 + number of models that are significantly better than me.

    rank_worst:
        1 + number of models that are NOT significantly worse than me
        (i.e., could still be better).
    """
    n = len(leaderboard)
    # Symmetric cache: sig[(i, j)] = +1 if i better than j, -1 if j better, 0 inconclusive.
    sig: dict[tuple[int, int], int] = {}

    def model_key(row: dict) -> str:
        return f"{row.get('model', '')}|{row.get('reasoning_effort') or ''}"

    for i in range(n):
        for j in range(i + 1, n):
            a = leaderboard[i]
            b = leaderboard[j]
            pair_seed = hash((model_key(a), model_key(b))) & 0xFFFFFFFF
            s = _paired_diff_sig(
                a.get("_conditioned", []),
                b.get("_conditioned", []),
                seed=pair_seed,
            )
            sig[(i, j)] = s
            sig[(j, i)] = -s

    for i, row in enumerate(leaderboard):
        definitely_better = 0
        not_significantly_worse = 0
        for j in range(n):
            if i == j:
                continue
            s_ji = sig[(j, i)]  # +1 if j better than i
            if s_ji > 0:
                definitely_better += 1
            if s_ji >= 0:
                # j is either better than i, or inconclusive -> j could be better
                not_significantly_worse += 1
        row["rank_best"] = 1 + definitely_better
        row["rank_worst"] = 1 + not_significantly_worse

    return leaderboard


def build_leaderboard(
    all_results: list[dict], benchmark_lookup: dict | None = None
) -> list[dict]:
    rows = []
    for result in all_results:
        s = result["summary"]
        details = result.get("details", [])
        altered_details = [d for d in details if d.get("riddle_type") == "altered"]
        original_details = [d for d in details if d.get("riddle_type") == "original"]

        altered_by_riddle: dict[str, list[dict]] = defaultdict(list)
        for d in altered_details:
            riddle_id = d.get("riddle_id")
            if riddle_id:
                altered_by_riddle[riddle_id].append(d)

        original_by_riddle: dict[str, list[dict]] = defaultdict(list)
        for d in original_details:
            riddle_id = d.get("riddle_id")
            if riddle_id:
                original_by_riddle[riddle_id].append(d)

        per_riddle = []

        for riddle_id, samples in altered_by_riddle.items():
            override_mean = mean(
                1.0 if sample.get("gave_original_answer") else 0.0 for sample in samples
            )
            accuracy_mean = mean(
                1.0 if sample.get("correct") else 0.0 for sample in samples
            )

            original_samples = original_by_riddle.get(riddle_id, [])
            original_accuracy_mean = (
                mean(
                    1.0 if sample.get("correct") else 0.0 for sample in original_samples
                )
                if original_samples
                else None
            )
            original_solved = bool(
                original_samples
                and any(sample.get("correct") for sample in original_samples)
            )

            if benchmark_lookup:
                entry = benchmark_lookup.get(riddle_id, {})
                cluster = entry.get("original_riddle", riddle_id)
            else:
                cluster = riddle_id

            per_riddle.append(
                {
                    "riddle_id": riddle_id,
                    "cluster": cluster,
                    "override_mean": override_mean,
                    "accuracy_mean": accuracy_mean,
                    "sample_count": len(samples),
                    "original_accuracy_mean": original_accuracy_mean,
                    "original_solved": original_solved,
                }
            )

        conditioned_per_riddle = [r for r in per_riddle if r["original_solved"]]

        n_riddles = len(per_riddle)
        if n_riddles > 0:
            altered_accuracy = mean(r["accuracy_mean"] for r in per_riddle)
            pattern_override_rate = s["pattern_override_rate"]
            avg_samples_per_riddle = mean(r["sample_count"] for r in per_riddle)
            avg_output_tokens_per_riddle = s.get("total_output_tokens", 0) / (
                avg_samples_per_riddle * n_riddles
            )
            avg_input_tokens_per_riddle = s.get("total_input_tokens", 0) / (
                avg_samples_per_riddle * n_riddles
            )

            if conditioned_per_riddle:
                conditioned_override_rate = mean(
                    r["override_mean"] for r in conditioned_per_riddle
                )
                conditioned_override_total = sum(
                    sum(
                        1
                        for sample in altered_by_riddle[r["riddle_id"]]
                        if sample.get("gave_original_answer")
                    )
                    for r in conditioned_per_riddle
                )
            else:
                conditioned_override_rate = 0.0
                conditioned_override_total = 0
        else:
            altered_accuracy = s["altered_accuracy"]
            conditioned_override_rate = s["conditioned_override_rate"]
            pattern_override_rate = s["pattern_override_rate"]
            avg_output_tokens_per_riddle = 0.0
            avg_input_tokens_per_riddle = 0.0
            avg_samples_per_riddle = 0.0
            conditioned_override_total = s.get("conditioned_override_total", 0)

        row = {
            "model": result["model"],
            "provider": result.get("provider", ""),
            "quantization": result.get("quantization", ""),
            "reasoning_enabled": bool(result.get("reasoning_enabled", False)),
            "reasoning_effort": result.get("reasoning_effort"),
            "original_accuracy": s["original_accuracy"],
            "altered_accuracy": altered_accuracy,
            "pattern_override_rate": pattern_override_rate,
            "conditioned_override_rate": conditioned_override_rate,
            "conditioned_override_total": conditioned_override_total,
            "total_input_tokens": s.get("total_input_tokens", 0),
            "total_output_tokens": s.get("total_output_tokens", 0),
            "avg_input_tokens_per_riddle": avg_input_tokens_per_riddle,
            "avg_output_tokens_per_riddle": avg_output_tokens_per_riddle,
            "avg_samples_per_riddle": avg_samples_per_riddle,
            "unique_altered_riddles": n_riddles,
            "conditioned_unique_altered_riddles": len(conditioned_per_riddle),
            "_conditioned": per_riddle,
        }

        # CI95 for conditioned override and altered accuracy using per-riddle means
        if conditioned_per_riddle:
            co_scores = [
                (r["cluster"], r["override_mean"]) for r in conditioned_per_riddle
            ]
            row["conditioned_override_ci95"] = _clustered_bootstrap_ci95(co_scores)
        else:
            row["conditioned_override_ci95"] = 0.0

        if per_riddle:
            acc_scores = [(r["cluster"], r["accuracy_mean"]) for r in per_riddle]
            row["altered_accuracy_ci95"] = _clustered_bootstrap_ci95(acc_scores)
        else:
            n = s.get("altered_total", 0)
            if n > 0:
                p = conditioned_override_rate
                row["conditioned_override_ci95"] = round(
                    1.96 * math.sqrt(p * (1 - p) / n), 4
                )
                p2 = altered_accuracy
                row["altered_accuracy_ci95"] = round(
                    1.96 * math.sqrt(p2 * (1 - p2) / n), 4
                )
            else:
                row["conditioned_override_ci95"] = 0.0
                row["altered_accuracy_ci95"] = 0.0

        rows.append(row)

    # Sort by conditioned_override_rate ascending (lower = better)
    rows.sort(key=lambda r: (r["conditioned_override_rate"], -r["altered_accuracy"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank

    # Compute rank spread via paired clustered bootstrap on COR differences.
    rows = _compute_rank_spread(rows)

    # Strip internal per-riddle data before returning (not part of the public schema).
    for row in rows:
        row.pop("_conditioned", None)

    return rows


TYPE_ORDER = ["constraint_addition", "meaning_shift", "context_swap", "bias_probe"]


def build_alteration_type_stats(
    all_results: list[dict], benchmark_lookup: dict
) -> dict:
    """Aggregate per-alteration-type COR and altered accuracy across models."""
    # Count unique altered riddles of each type in the benchmark.
    n_riddles_by_type: dict[str, int] = defaultdict(int)
    for riddle_id, entry in benchmark_lookup.items():
        t = entry.get("type")
        if t:
            n_riddles_by_type[t] += 1

    per_type: dict[str, dict] = {
        t: {"per_model": {}} for t in n_riddles_by_type
    }

    for result in all_results:
        model = result["model"]
        details = result.get("details", [])

        altered_by_riddle: dict[str, list[dict]] = defaultdict(list)
        original_by_riddle: dict[str, list[dict]] = defaultdict(list)
        for d in details:
            rid = d.get("riddle_id")
            if not rid:
                continue
            if d.get("riddle_type") == "altered":
                altered_by_riddle[rid].append(d)
            elif d.get("riddle_type") == "original":
                original_by_riddle[rid].append(d)

        # Bucket per-riddle stats by type.
        acc_by_type: dict[str, list[float]] = defaultdict(list)
        cor_by_type: dict[str, list[float]] = defaultdict(list)
        for rid, samples in altered_by_riddle.items():
            entry = benchmark_lookup.get(rid, {})
            t = entry.get("type")
            if not t:
                continue
            acc = mean(1.0 if s.get("correct") else 0.0 for s in samples)
            acc_by_type[t].append(acc)

            originals = original_by_riddle.get(rid, [])
            original_solved = any(s.get("correct") for s in originals)
            if original_solved:
                override = mean(
                    1.0 if s.get("gave_original_answer") else 0.0 for s in samples
                )
                cor_by_type[t].append(override)

        for t in per_type:
            alt_acc = mean(acc_by_type[t]) if acc_by_type[t] else None
            cor = mean(cor_by_type[t]) if cor_by_type[t] else None
            per_type[t]["per_model"][model] = {
                "cor": round(cor, 4) if cor is not None else None,
                "alt_acc": round(alt_acc, 4) if alt_acc is not None else None,
            }

    types_out = []
    for t in TYPE_ORDER:
        if t not in per_type:
            continue
        entries = per_type[t]["per_model"]
        cor_values = [v["cor"] for v in entries.values() if v["cor"] is not None]
        alt_values = [v["alt_acc"] for v in entries.values() if v["alt_acc"] is not None]
        types_out.append(
            {
                "type": t,
                "mean_cor": round(mean(cor_values), 4) if cor_values else None,
                "mean_alt_acc": round(mean(alt_values), 4) if alt_values else None,
                "n_riddles": n_riddles_by_type[t],
                "per_model": entries,
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "types": types_out,
    }


def print_leaderboard(leaderboard):
    def pct(v):
        return f"{v * 100:5.1f}%"

    def ci(v):
        return f"+/-{v * 100:.1f}%"

    def reasoning_status(row):
        return "on" if row.get("reasoning_enabled") else "off"

    def reasoning_effort(row):
        return row.get("reasoning_effort") or "-"

    width = 136
    print()
    print("=" * width)
    print("ALTERED RIDDLES LEADERBOARD")
    print("=" * width)
    print(
        f"{'Rank':<5} {'Rank Spread':<14} {'Model':<28} {'Reasoning':<9} {'Effort':<8} "
        f"{'Orig Acc':>10} {'Alt Acc':>10} {'Cond Override':>15} {'Override':>10} "
        f"{'Tok/riddle':>12} {'Samp/riddle':>12}"
    )
    print("-" * width)
    for r in leaderboard:
        co = pct(r["conditioned_override_rate"])
        co_ci = ci(r.get("conditioned_override_ci95", 0))
        rank_spread = f"[{r['rank_best']}–{r['rank_worst']}]"
        print(
            f"{r['rank']:<5} {rank_spread:<14} {r['model']:<28} "
            f"{reasoning_status(r):<9} {reasoning_effort(r):<8} {pct(r['original_accuracy']):>10} "
            f"{pct(r['altered_accuracy']):>10} {co + ' ' + co_ci:>15} "
            f"{pct(r['pattern_override_rate']):>10} {r.get('avg_output_tokens_per_riddle', 0):>12.1f} "
            f"{r.get('avg_samples_per_riddle', 0):>12.2f}"
        )
    print("=" * width)
    print()


def generate_markdown(leaderboard, output_path):
    lines = [
        "# Altered Riddles Leaderboard",
        "",
        f"> {len(leaderboard)} models evaluated. "
        "Main metric: **Conditioned Override Rate** (lower = better).",
        "",
        "| Rank | Rank Spread | Model | Reasoning | Effort | Orig Acc ↑ | Alt Acc ↑ | Cond Override ↓ | CI95 | Override Rate ↓ | Tok/riddle | Samp/riddle |",
        "|------|-------------|-------|-----------|--------|-----------|----------|-----------------|------|-----------------|------------|-------------|",
    ]
    for r in leaderboard:
        rank_spread = f"[{r['rank_best']}–{r['rank_worst']}]"
        lines.append(
            f"| {r['rank']} | {rank_spread} | {r['model']} "
            f"| {'on' if r.get('reasoning_enabled') else 'off'} "
            f"| {r.get('reasoning_effort') or '-'} "
            f"| {r['original_accuracy'] * 100:.1f}% "
            f"| {r['altered_accuracy'] * 100:.1f}% "
            f"| {r['conditioned_override_rate'] * 100:.1f}% "
            f"| +/-{r.get('conditioned_override_ci95', 0) * 100:.1f}% "
            f"| {r['pattern_override_rate'] * 100:.1f}% "
            f"| {r.get('avg_output_tokens_per_riddle', 0):.1f} "
            f"| {r.get('avg_samples_per_riddle', 0):.2f} |"
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
    expected_altered_ids, expected_original_ids = _expected_coverage(all_bench)
    all_results = _filter_complete_results(
        all_results,
        expected_altered_ids,
        expected_original_ids,
    )
    if not all_results:
        logger.error(
            "No complete evaluation results found in %s; every model is missing at least one benchmark riddle.",
            results_dir,
        )
        raise SystemExit(1)

    leaderboard = build_leaderboard(all_results, benchmark_lookup)

    # Save
    write_json(results_dir / "leaderboard.json", leaderboard)
    print_leaderboard(leaderboard)
    md_path = results_dir / "LEADERBOARD.md"
    generate_markdown(leaderboard, md_path)
    logger.info("Leaderboard JSON: %s", results_dir / "leaderboard.json")
    logger.info("Leaderboard MD:   %s", md_path)

    type_stats = build_alteration_type_stats(all_results, benchmark_lookup or {})
    type_stats_path = results_dir / "alteration_type_stats.json"
    write_json(type_stats_path, type_stats)
    logger.info("Alteration type stats: %s", type_stats_path)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate the benchmark leaderboard.")
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS)
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    return parser.parse_args()


if __name__ == "__main__":
    run_leaderboard(parse_args())
