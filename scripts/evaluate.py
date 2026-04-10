#!/usr/bin/env python3
"""
evaluate.py — Evaluate model outputs against the Altered Riddles benchmark.

This script reads model outputs, checks a local judgment cache to avoid re-evaluating,
and calls an LLM to evaluate any pending outputs based on semantic meaning.

Usage examples:
    # Evaluate all models using the default Judge
    python -m scripts.evaluate

    # Use a specific model as the judge (e.g., GPT-5.4) with batched requests
    python -m scripts.evaluate --provider openai --model gpt-5.4 --batch-size 20
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from collections import Counter
from itertools import groupby
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_MODEL_OUTPUTS,
    DEFAULT_RESULTS,
    get_benchmark_version,
    provider_names,
    resolve_provider,
)
from scripts.core.io_utils import (
    append_jsonl,
    load_jsonl,
    load_template,
    strip_markdown_fences,
    write_json,
)
from scripts.core.llm_client import call_llm_batched

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Partial credit for answers that match a competing (non-primary) accepted answer
COMPETING_ANSWER_WEIGHT = 0.5


# ---------------------------------------------------------------------------
# LLM Judge Logic
# ---------------------------------------------------------------------------


def parse_judge_response(raw_text: str) -> dict:
    """Parse the Judge LLM's JSON response."""
    text = strip_markdown_fences(raw_text)
    try:
        data = json.loads(text)
        return {
            "correct": bool(data.get("correct", False)),
            "gave_original": bool(data.get("gave_original", False)),
            "competing": bool(data.get("competing", False)),
        }
    except json.JSONDecodeError:
        logger.warning("Failed to parse Judge JSON: %s", text[:200])
        return {"correct": False, "gave_original": False, "competing": False}


# ---------------------------------------------------------------------------
# Benchmark Data Extractors
# ---------------------------------------------------------------------------


def build_benchmark_lookup(entries: list[dict]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for entry in entries:
        rid = entry.get("id", "")
        if rid:
            lookup[rid] = entry
    return lookup


def extract_accepted_answers(benchmark_entry: dict, riddle_type: str) -> list[str]:
    if riddle_type == "original":
        answers = benchmark_entry.get("original_accepted_answers")
        if not answers:
            ans = benchmark_entry.get("original_answer", "")
            answers = [ans] if ans else []
    else:
        answers = benchmark_entry.get("altered_accepted_answers")
        if not answers:
            ans = benchmark_entry.get("altered_answer", "")
            answers = [ans] if ans else []
    return answers


def extract_original_answers(benchmark_entry: dict) -> list[str]:
    answers = benchmark_entry.get("original_accepted_answers")
    if not answers:
        ans = benchmark_entry.get("original_answer", "")
        answers = [ans] if ans else []
    return answers


def extract_competing_answers(benchmark_entry: dict) -> list[str]:
    return benchmark_entry.get("altered_competing_answers", [])


# ---------------------------------------------------------------------------
# Evaluation Logic
# ---------------------------------------------------------------------------


def _score_single_output(
    output: dict,
    benchmark_entry: dict | None,
    judgment: dict,
    competing_weight: float = COMPETING_ANSWER_WEIGHT,
) -> dict | None:
    """Score a single model output record using the Judge's assessment."""
    if benchmark_entry is None:
        return None

    riddle_id = output.get("riddle_id", "")
    riddle_type = output.get("riddle_type", "")
    model_answer = output.get("model_answer", "")
    accepted = extract_accepted_answers(benchmark_entry, riddle_type)

    correct = judgment.get("correct", False)

    detail: dict = {
        "riddle_id": riddle_id,
        "riddle_type": riddle_type,
        "riddle_text": output.get("riddle_text", ""),
        "model_answer": model_answer,
        "accepted_answers": accepted,
        "correct": correct,
        "sample_index": output.get("sample_index", 1),
    }

    if riddle_type == "altered":
        gave_original = judgment.get("gave_original", False)
        competing_match = judgment.get("competing", False)

        detail["gave_original_answer"] = gave_original
        original_answers = extract_original_answers(benchmark_entry)
        detail["original_answer"] = original_answers[0] if original_answers else ""

        if correct:
            detail["score"] = 1.0
        else:
            detail["competing_match"] = competing_match
            if competing_match and not gave_original:
                detail["score"] = competing_weight
            else:
                detail["score"] = 0.0

    return detail


def _collect_token_stats(model_outputs: list[dict], num_samples: int = 1) -> dict:
    def _sum_tokens(outputs: list[dict], divisor: int) -> tuple[int, int]:
        in_toks = [
            o["input_tokens"] for o in outputs if o.get("input_tokens") is not None
        ]
        out_toks = [
            o["output_tokens"] for o in outputs if o.get("output_tokens") is not None
        ]
        raw_in = sum(in_toks) if in_toks else 0
        raw_out = sum(out_toks) if out_toks else 0
        return round(raw_in / divisor), round(raw_out / divisor)

    orig_outputs = [o for o in model_outputs if o.get("riddle_type") == "original"]
    alt_outputs = [o for o in model_outputs if o.get("riddle_type") == "altered"]

    effective_samples = max(num_samples, 1)
    orig_in, orig_out = _sum_tokens(orig_outputs, effective_samples)
    alt_in, alt_out = _sum_tokens(alt_outputs, effective_samples)

    return {
        "original_input_tokens": orig_in,
        "original_output_tokens": orig_out,
        "altered_input_tokens": alt_in,
        "altered_output_tokens": alt_out,
        "total_input_tokens": orig_in + alt_in,
        "total_output_tokens": orig_out + alt_out,
    }


def evaluate_model(
    model_outputs: list[dict],
    judgments: dict[tuple[str, str, int], dict],
    benchmark_lookup: dict[str, dict],
    verbose: bool = False,
    competing_weight: float = COMPETING_ANSWER_WEIGHT,
) -> dict:
    """Evaluate a single model's outputs and return a results dict."""
    model_name = ""
    details: list[dict] = []
    provider = ""
    quantization = ""

    for output in model_outputs:
        if not model_name:
            model_name = output.get("model", "unknown")
            provider = output.get("provider", "")
            quantization = output.get("quantization", "")

        riddle_id = output.get("riddle_id", "")
        riddle_type = output.get("riddle_type", "")
        sample_index = output.get("sample_index", 1)

        benchmark_entry = benchmark_lookup.get(riddle_id)
        if not benchmark_entry:
            continue

        key = (riddle_id, riddle_type, sample_index)
        judgment = judgments.get(
            key, {"correct": False, "gave_original": False, "competing": False}
        )

        detail = _score_single_output(
            output, benchmark_entry, judgment, competing_weight=competing_weight
        )
        if detail is None:
            continue
        details.append(detail)

        if verbose:
            status = "✓" if detail["correct"] else "✗"
            extra = "  ⚠ gave original" if detail.get("gave_original_answer") else ""
            sample_tag = (
                f"  [sample {detail['sample_index']}]"
                if detail.get("sample_index", 1) > 1
                else ""
            )
            logger.info(
                "  %s  %s (%s): ans=%r  acc=%r%s%s",
                status,
                detail["riddle_id"],
                detail["riddle_type"],
                detail["model_answer"][:40] + "...",
                detail["accepted_answers"],
                extra,
                sample_tag,
            )

    def _group_key(d: dict) -> tuple[str, str]:
        return (d["riddle_id"], d["riddle_type"])

    sorted_details = sorted(details, key=lambda d: _group_key(d))
    grouped: dict[tuple[str, str], list[dict]] = {}
    for key, grp in groupby(sorted_details, key=lambda d: _group_key(d)):
        grouped[key] = list(grp)

    altered_group_sizes = [len(v) for k, v in grouped.items() if k[1] == "altered"]
    num_samples = max(altered_group_sizes) if altered_group_sizes else 1

    original_total = original_correct = 0
    altered_total = altered_correct_s1 = altered_competing = altered_gave_original = 0
    altered_score_s1 = 0.0

    for key, group in grouped.items():
        riddle_type = key[1]
        rec = next((d for d in group if d.get("sample_index", 1) == 1), group[0])

        if riddle_type == "original":
            original_total += 1
            if rec["correct"]:
                original_correct += 1
        elif riddle_type == "altered":
            altered_total += 1
            if rec.get("gave_original_answer"):
                altered_gave_original += 1
            if rec["correct"]:
                altered_correct_s1 += 1
                altered_score_s1 += 1.0
            elif rec.get("competing_match") and not rec.get("gave_original_answer"):
                altered_competing += 1
                altered_score_s1 += competing_weight

    conditioned_override_total = conditioned_override_count = 0
    unique_riddles = {k[0] for k in grouped.keys()}

    for rid in unique_riddles:
        orig_group = grouped.get((rid, "original"), [])
        alt_group = grouped.get((rid, "altered"), [])
        if orig_group and alt_group:
            orig_correct = any(d["correct"] for d in orig_group)
            if orig_correct:
                conditioned_override_total += 1
                alt_gave_original = any(
                    d.get("gave_original_answer") for d in alt_group
                )
                if alt_gave_original:
                    conditioned_override_count += 1

    original_accuracy = (
        round(original_correct / original_total, 3) if original_total else 0.0
    )
    altered_weighted_accuracy = (
        round(altered_score_s1 / altered_total, 3) if altered_total else 0.0
    )
    pattern_override_rate = (
        round(altered_gave_original / altered_total, 3) if altered_total else 0.0
    )
    conditioned_override_rate = (
        round(conditioned_override_count / conditioned_override_total, 3)
        if conditioned_override_total
        else 0.0
    )

    alt_binary_sum = avg_acc_sum = 0.0
    for key, group in grouped.items():
        if key[1] != "altered":
            continue
        binary_scores = [1.0 if d["correct"] else 0.0 for d in group]
        alt_binary_sum += sum(binary_scores) / len(binary_scores)
        sample_scores = [d.get("score", 0.0) for d in group]
        avg_acc_sum += sum(sample_scores) / len(sample_scores)

    altered_accuracy = (
        round(alt_binary_sum / altered_total, 3) if altered_total else 0.0
    )
    average_accuracy = round(avg_acc_sum / altered_total, 3) if altered_total else 0.0
    total_score = average_accuracy

    summary: dict = {
        "original_total": original_total,
        "original_correct": original_correct,
        "original_accuracy": original_accuracy,
        "altered_total": altered_total,
        "altered_correct": altered_correct_s1,
        "altered_competing": altered_competing,
        "altered_accuracy": altered_accuracy,
        "altered_weighted_accuracy": altered_weighted_accuracy,
        "pattern_override_rate": pattern_override_rate,
        "conditioned_override_rate": conditioned_override_rate,
        "average_accuracy": average_accuracy,
        "total_score": total_score,
    }

    if num_samples > 1:
        best_of_n_correct = majority_vote_correct = altered_count_multi = 0
        for key, group in grouped.items():
            if key[1] != "altered":
                continue
            altered_count_multi += 1
            if any(d["correct"] for d in group):
                best_of_n_correct += 1
            elif any(
                d.get("competing_match") and not d.get("gave_original_answer")
                for d in group
            ):
                best_of_n_correct += competing_weight

            # Simple majority norm logic (LLM judge is better, but this suffices for multi-sample consensus)
            answer_counts: Counter[str] = Counter()
            for d in group:
                answer_counts[d["model_answer"]] += 1
            majority_ans, _ = answer_counts.most_common(1)[0]
            rep = next(d for d in group if d["model_answer"] == majority_ans)
            if rep["correct"]:
                majority_vote_correct += 1
            elif rep.get("competing_match") and not rep.get("gave_original_answer"):
                majority_vote_correct += competing_weight

        summary["num_samples"] = num_samples
        summary["best_of_n_accuracy"] = (
            round(best_of_n_correct / altered_count_multi, 3)
            if altered_count_multi
            else 0.0
        )
        summary["majority_vote_accuracy"] = (
            round(majority_vote_correct / altered_count_multi, 3)
            if altered_count_multi
            else 0.0
        )

    summary.update(_collect_token_stats(model_outputs, num_samples=num_samples))
    summary["num_riddles"] = len({d["riddle_id"] for d in details})
    summary["original_num_riddles"] = len(
        {d["riddle_id"] for d in details if d["riddle_type"] == "original"}
    )
    summary["altered_num_riddles"] = len(
        {d["riddle_id"] for d in details if d["riddle_type"] == "altered"}
    )

    # --- Per-type breakdown (altered riddles only, sample_index == 1) ---
    per_type: dict[str, dict] = {}
    altered_details_s1 = [
        d
        for d in details
        if d.get("riddle_type") == "altered" and d.get("sample_index", 1) == 1
    ]
    type_groups: dict[str, list[dict]] = {}
    for d in altered_details_s1:
        entry = benchmark_lookup.get(d["riddle_id"], {})
        t = entry.get("type", "unknown")
        type_groups.setdefault(t, []).append(d)
    for t, grp in sorted(type_groups.items()):
        count = len(grp)
        correct = sum(1 for d in grp if d["correct"])
        score_sum = sum(d.get("score", 0.0) for d in grp)
        gave_orig = sum(1 for d in grp if d.get("gave_original_answer"))
        per_type[t] = {
            "count": count,
            "accuracy": round(correct / count, 3) if count else 0.0,
            "weighted_accuracy": round(score_sum / count, 3) if count else 0.0,
            "pattern_override_rate": round(gave_orig / count, 3) if count else 0.0,
        }
    summary["per_type"] = per_type

    # --- Per-source breakdown (altered riddles only, sample_index == 1) ---
    per_source: dict[str, dict] = {}
    source_groups: dict[str, list[dict]] = {}
    for d in altered_details_s1:
        entry = benchmark_lookup.get(d["riddle_id"], {})
        src = entry.get("source", "unknown")
        source_groups.setdefault(src, []).append(d)
    for src, grp in sorted(source_groups.items()):
        count = len(grp)
        correct = sum(1 for d in grp if d["correct"])
        score_sum = sum(d.get("score", 0.0) for d in grp)
        gave_orig = sum(1 for d in grp if d.get("gave_original_answer"))
        per_source[src] = {
            "count": count,
            "accuracy": round(correct / count, 3) if count else 0.0,
            "weighted_accuracy": round(score_sum / count, 3) if count else 0.0,
            "pattern_override_rate": round(gave_orig / count, 3) if count else 0.0,
        }
    summary["per_source"] = per_source

    return {
        "model": model_name,
        "provider": provider,
        "quantization": quantization,
        "summary": summary,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Leaderboard & display
# ---------------------------------------------------------------------------


def build_leaderboard(all_results: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for result in all_results:
        s = result["summary"]
        row: dict = {
            "model": result["model"],
            "provider": result.get("provider", ""),
            "quantization": result.get("quantization", ""),
            "original_accuracy": s["original_accuracy"],
            "altered_accuracy": s["altered_accuracy"],
            "altered_weighted_accuracy": s["altered_weighted_accuracy"],
            "pattern_override_rate": s["pattern_override_rate"],
            "conditioned_override_rate": s["conditioned_override_rate"],
            "average_accuracy": s["average_accuracy"],
            "total_score": s["total_score"],
            "total_input_tokens": s.get("total_input_tokens", 0),
            "total_output_tokens": s.get("total_output_tokens", 0),
            "original_input_tokens": s.get("original_input_tokens", 0),
            "original_output_tokens": s.get("original_output_tokens", 0),
            "altered_input_tokens": s.get("altered_input_tokens", 0),
            "altered_output_tokens": s.get("altered_output_tokens", 0),
            "original_num_riddles": s.get("original_num_riddles", 0),
            "altered_num_riddles": s.get("altered_num_riddles", 0),
        }
        n = row.get("altered_num_riddles", 0)
        if n > 0:
            p_acc = row["altered_accuracy"]
            row["altered_accuracy_ci95"] = round(
                1.96 * math.sqrt(p_acc * (1 - p_acc) / n), 4
            )
            p_avg = row["average_accuracy"]
            row["average_accuracy_ci95"] = round(
                1.96 * math.sqrt(p_avg * (1 - p_avg) / n), 4
            )
            p_ovr = row["pattern_override_rate"]
            row["pattern_override_rate_ci95"] = round(
                1.96 * math.sqrt(p_ovr * (1 - p_ovr) / n), 4
            )
        else:
            row["altered_accuracy_ci95"] = 0.0
            row["average_accuracy_ci95"] = 0.0
            row["pattern_override_rate_ci95"] = 0.0
        if s.get("num_samples", 1) > 1:
            row["num_samples"] = s["num_samples"]
            row["best_of_n_accuracy"] = s["best_of_n_accuracy"]
            row["majority_vote_accuracy"] = s["majority_vote_accuracy"]
        row["per_type"] = s.get("per_type", {})
        row["per_source"] = s.get("per_source", {})
        row["parameter_count_billions"] = None
        row["estimated_cost_per_mtok_usd"] = None
        rows.append(row)

    # Filter out models with insufficient coverage (< 250 altered riddles)
    rows = [r for r in rows if r.get("altered_num_riddles", 0) >= 250]
    rows.sort(key=lambda r: (-r["total_score"], r["pattern_override_rate"]))
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def print_leaderboard(leaderboard: list[dict]) -> None:
    col_model, col_metric, col_tokens = 22, 10, 8

    def fmt_pct(val: float) -> str:
        return f"{val * 100:5.1f}%"

    top = f"╔{'═' * col_model}╦{'═' * col_metric}╦{'═' * col_metric}╦{'═' * col_metric}╦{'═' * col_metric}╦{'═' * col_metric}╦{'═' * col_tokens}╗"
    mid = f"╠{'═' * col_model}╬{'═' * col_metric}╬{'═' * col_metric}╬{'═' * col_metric}╬{'═' * col_metric}╬{'═' * col_metric}╬{'═' * col_tokens}╣"
    bot = f"╚{'═' * col_model}╩{'═' * col_metric}╩{'═' * col_metric}╩{'═' * col_metric}╩{'═' * col_metric}╩{'═' * col_metric}╩{'═' * col_tokens}╝"

    print(top)
    print(
        f"║{' Model'.ljust(col_model)}║{' Orig Acc'.ljust(col_metric)}║{' Alt Acc'.ljust(col_metric)}║{' Override'.ljust(col_metric)}║{' Cond Ovr'.ljust(col_metric)}║{' Score'.ljust(col_metric)}║{' Tokens'.ljust(col_tokens)}║"
    )
    print(mid)

    for row in leaderboard:
        model_label = (
            f"{row['model']}@{row['num_samples']}"
            if row.get("num_samples", 1) > 1
            else row["model"]
        )
        print(
            f"║ {model_label[: col_model - 1].ljust(col_model - 1)}"
            f"║ {fmt_pct(row['original_accuracy']).ljust(col_metric - 1)}"
            f"║ {fmt_pct(row['altered_accuracy']).ljust(col_metric - 1)}"
            f"║ {fmt_pct(row['pattern_override_rate']).ljust(col_metric - 1)}"
            f"║ {fmt_pct(row['conditioned_override_rate']).ljust(col_metric - 1)}"
            f"║ {fmt_pct(row['total_score']).ljust(col_metric - 1)}"
            f"║ {str(row.get('total_output_tokens', '-')).ljust(col_tokens - 1)}║"
        )
    print(bot)


def generate_markdown_leaderboard(leaderboard: list[dict], output_path: Path) -> None:
    """Generate a Markdown-formatted leaderboard table."""
    lines = [
        "# Altered Riddles Leaderboard",
        "",
        f"> Auto-generated from `leaderboard.json`. {len(leaderboard)} models evaluated.",
        "",
        "| Rank | Model | Orig Acc | Alt Acc | Override | Score | Tokens |",
        "|------|-------|----------|---------|----------|-------|--------|",
    ]
    for row in leaderboard:
        model = row["model"]
        if row.get("num_samples", 1) > 1:
            model += f"@{row['num_samples']}"
        lines.append(
            f"| {row['rank']} "
            f"| {model} "
            f"| {row['original_accuracy'] * 100:.1f}% "
            f"| {row['altered_accuracy'] * 100:.1f}% "
            f"| {row['pattern_override_rate'] * 100:.1f}% "
            f"| {row['total_score'] * 100:.1f}% "
            f"| {row.get('total_output_tokens', '-'):,} |"
        )
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def compute_riddle_difficulty(all_results: list[dict], output_path: Path) -> None:
    """Compute per-riddle difficulty scores across all evaluated models.

    Difficulty = 1.0 - (fraction of models that got it right).
    """
    riddle_scores: dict[str, list[float]] = {}
    for result in all_results:
        for detail in result.get("details", []):
            if detail.get("riddle_type") != "altered":
                continue
            rid = detail["riddle_id"]
            score = detail.get("score", 0.0)
            if rid not in riddle_scores:
                riddle_scores[rid] = []
            riddle_scores[rid].append(score)

    difficulty_data = []
    for rid, scores in sorted(riddle_scores.items()):
        avg_score = sum(scores) / len(scores) if scores else 0.0
        difficulty_data.append(
            {
                "riddle_id": rid,
                "num_models_tested": len(scores),
                "avg_score": round(avg_score, 3),
                "difficulty": round(1.0 - avg_score, 3),
            }
        )

    difficulty_data.sort(key=lambda x: x["difficulty"], reverse=True)

    from scripts.core.io_utils import write_json

    write_json(output_path, difficulty_data)


# ---------------------------------------------------------------------------
# Main Evaluation Driver
# ---------------------------------------------------------------------------


def run_evaluation(args: argparse.Namespace) -> None:
    judge_model, judge_api_key = resolve_provider(args.provider, args.model)

    benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        logger.error("Benchmark not found: %s", benchmark_path)
        sys.exit(1)

    benchmark_entries = load_jsonl(benchmark_path)
    benchmark_lookup = build_benchmark_lookup(benchmark_entries)

    model_outputs_path = Path(args.model_outputs)
    output_files = (
        sorted(model_outputs_path.glob("*.jsonl"))
        if model_outputs_path.is_dir()
        else [model_outputs_path]
    )

    if not output_files:
        logger.error("No .jsonl files found in %s", model_outputs_path)
        sys.exit(1)

    results_dir_root = Path(args.results_dir)
    results_dir = Path(args.results_dir) / get_benchmark_version()
    results_dir.mkdir(parents=True, exist_ok=True)

    judgments_dir = results_dir / "judgments"
    judgments_dir.mkdir(exist_ok=True)

    # --- Load the Jinja2 Template ---
    judge_template = load_template(args.judge_template)

    all_results: list[dict] = []

    for output_file in output_files:
        model_outputs = load_jsonl(output_file)
        if not model_outputs:
            continue

        model_name_safe = output_file.stem
        judgment_cache_path = judgments_dir / f"{model_name_safe}_judgments.jsonl"

        # Load Existing Judgments
        judgments: dict[tuple[str, str, int], dict] = {}
        if judgment_cache_path.exists():
            for j in load_jsonl(judgment_cache_path):
                judgments[
                    (j["riddle_id"], j["riddle_type"], j.get("sample_index", 1))
                ] = j["judgment"]

        # Identify Pending Tasks
        pending_tasks = []
        for output in model_outputs:
            key = (
                output.get("riddle_id", ""),
                output.get("riddle_type", ""),
                output.get("sample_index", 1),
            )
            if key not in judgments:
                pending_tasks.append(output)

        if pending_tasks:
            logger.info(
                "Calling Judge LLM for %d pending outputs in %s...",
                len(pending_tasks),
                model_name_safe,
            )

            total = len(pending_tasks)
            for chunk_start in range(0, total, args.batch_size):
                chunk = pending_tasks[chunk_start : chunk_start + args.batch_size]
                prompts, chunk_meta = [], []

                for output in chunk:
                    rid, rtype = (
                        output.get("riddle_id", ""),
                        output.get("riddle_type", ""),
                    )
                    entry = benchmark_lookup.get(rid)
                    if not entry:
                        continue

                    accepted = extract_accepted_answers(entry, rtype)
                    original = extract_original_answers(entry)
                    competing = extract_competing_answers(entry)

                    # --- Render prompt from Jinja Template ---
                    prompt = judge_template.render(
                        riddle=output.get("riddle_text", ""),
                        model_answer=output.get("model_answer", ""),
                        accepted=accepted,
                        original=original,
                        competing=competing,
                    )

                    prompts.append(prompt)
                    chunk_meta.append(output)

                if not prompts:
                    continue

                logger.info(
                    "  Dispatching Judge batch [%d–%d]...",
                    chunk_start + 1,
                    chunk_start + len(chunk),
                )
                results = call_llm_batched(
                    prompts,
                    provider=args.provider,
                    model=judge_model,
                    temperature=args.temperature,
                    api_key=judge_api_key,
                    max_concurrency=args.batch_size,
                )

                for output, res in zip(chunk_meta, results):
                    key = (
                        output.get("riddle_id", ""),
                        output.get("riddle_type", ""),
                        output.get("sample_index", 1),
                    )
                    if isinstance(res, BaseException):
                        logger.error("Judge failed for %s: %s", key, res)
                        parsed = {
                            "correct": False,
                            "gave_original": False,
                            "competing": False,
                        }
                    else:
                        parsed = parse_judge_response(res.text)

                    judgments[key] = parsed
                    append_jsonl(
                        judgment_cache_path,
                        {
                            "riddle_id": key[0],
                            "riddle_type": key[1],
                            "sample_index": key[2],
                            "judgment": parsed,
                        },
                    )

                time.sleep(0.5)

        # Evaluate and Save
        result = evaluate_model(
            model_outputs,
            judgments,
            benchmark_lookup,
            verbose=args.verbose,
            competing_weight=args.competing_weight,
        )
        all_results.append(result)

        eval_path = results_dir / f"{model_name_safe}_eval.json"
        write_json(eval_path, result)
        s = result["summary"]
        logger.info(
            "  %s — orig=%.1f%%  alt=%.1f%%  score=%.1f%%",
            result["model"],
            s["original_accuracy"] * 100,
            s["altered_accuracy"] * 100,
            s["total_score"] * 100,
        )

        if args.live_leaderboard:
            current_leaderboard = build_leaderboard(all_results)
            write_json(results_dir / "leaderboard.json", current_leaderboard)
            logger.info("  [Live Leaderboard updated]")

    if not all_results:
        sys.exit(1)

    leaderboard = build_leaderboard(all_results)
    write_json(results_dir_root / "leaderboard.json", leaderboard)
    write_json(results_dir / "leaderboard.json", leaderboard)
    print("\n")
    print_leaderboard(leaderboard)
    generate_markdown_leaderboard(
        leaderboard, Path(args.results_dir) / "LEADERBOARD.md"
    )
    logger.info(
        "Markdown leaderboard written to %s", Path(args.results_dir) / "LEADERBOARD.md"
    )
    compute_riddle_difficulty(all_results, results_dir / "riddle_difficulty.json")
    logger.info(
        "Per-riddle difficulty scores written to %s",
        results_dir / "riddle_difficulty.json",
    )
    print("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--benchmark", type=str, default=DEFAULT_BENCHMARK)
    parser.add_argument("--model-outputs", type=str, default=DEFAULT_MODEL_OUTPUTS)
    parser.add_argument("--results-dir", type=str, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--judge-template",
        type=str,
        default="prompts/judge.j2",
        help="Path to the Jinja2 judge prompt template.",
    )
    parser.add_argument(
        "--provider",
        choices=provider_names(),
        default="local",
        help="LLM Provider for the Judge.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemma-4-26b-a4b-it",
        help="LLM Model for the Judge (defaults to provider's default).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Temperature for the Judge LLM.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Batch size for concurrent LLM judge calls.",
    )
    parser.add_argument(
        "--live-leaderboard",
        action="store_true",
        default=False,
        help="Generate and save leaderboard.json incrementally after each model finishes.",
    )
    parser.add_argument(
        "--competing-weight",
        type=float,
        default=COMPETING_ANSWER_WEIGHT,
        help="Weight for competing (non-primary) accepted answers.",
    )
    parser.add_argument(
        "--param-count",
        type=float,
        default=None,
        help="Model parameter count in billions (optional metadata).",
    )
    parser.add_argument(
        "--cost-per-mtok",
        type=float,
        default=None,
        help="Cost per million tokens in USD (optional metadata).",
    )
    parser.add_argument("--verbose", action="store_true", default=False)
    return parser.parse_args()


if __name__ == "__main__":
    dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path)
    run_evaluation(parse_args())
