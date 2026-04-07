#!/usr/bin/env python3
"""
evaluate.py — Evaluate model outputs against the Altered Riddles benchmark.

This script is RE-RUNNABLE: it reads model outputs and benchmark data, scores
them WITHOUT calling any API. If you update `altered_accepted_answers` in
`benchmark.jsonl`, you can re-run evaluation to get updated scores.

Usage examples:
    # Evaluate all models in data/model_outputs/
    python -m scripts.evaluate

    # Evaluate a single model output file
    python -m scripts.evaluate --model-outputs data/model_outputs/gemini-3.1-pro.jsonl

    # Verbose per-riddle breakdown
    python -m scripts.evaluate --verbose
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter
from itertools import groupby
from pathlib import Path

from scripts.core.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_MODEL_OUTPUTS,
    DEFAULT_RESULTS,
    get_benchmark_version,
)
from scripts.core.io_utils import load_jsonl, write_json

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
# Answer-matching logic
# ---------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Lowercase, strip punctuation and articles for lenient matching."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\\b(a|an|the|it's|its|it is)\\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def is_match(model_answer: str, accepted_answers: list[str]) -> bool:
    """Check if model answer matches any accepted answer (lenient)."""
    m = normalize(model_answer)
    if not m:
        return False
    for accepted in accepted_answers:
        a = normalize(accepted)
        if not a:
            continue
        if a in m or m in a:
            return True
    return False


# ---------------------------------------------------------------------------
# Evaluation logic
# ---------------------------------------------------------------------------


def build_benchmark_lookup(entries: list[dict]) -> dict[str, dict]:
    """Build a lookup dict keyed by riddle `id`."""
    lookup: dict[str, dict] = {}
    for entry in entries:
        rid = entry.get("id", "")
        if rid:
            lookup[rid] = entry
    return lookup


def extract_accepted_answers(benchmark_entry: dict, riddle_type: str) -> list[str]:
    """
    Return the list of accepted answers for a given riddle type.
    """
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
    """Return the list of accepted answers for the *original* riddle."""
    answers = benchmark_entry.get("original_accepted_answers")
    if not answers:
        ans = benchmark_entry.get("original_answer", "")
        answers = [ans] if ans else []
    return answers


def extract_competing_answers(benchmark_entry: dict) -> list[str]:
    """Return the list of competing answers for the *altered* riddle."""
    return benchmark_entry.get("altered_competing_answers", [])


def _score_single_output(
    output: dict,
    benchmark_lookup: dict[str, dict],
) -> dict | None:
    """Score a single model output record against the benchmark."""
    riddle_id = output.get("riddle_id", "")
    riddle_type = output.get("riddle_type", "")
    model_answer = output.get("model_answer", "")

    benchmark_entry = benchmark_lookup.get(riddle_id)
    if benchmark_entry is None:
        logger.warning("Riddle ID '%s' not found in benchmark — skipping.", riddle_id)
        return None

    accepted = extract_accepted_answers(benchmark_entry, riddle_type)
    correct = is_match(model_answer, accepted)

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
        # Check if the model gave the *original* answer instead
        original_answers = extract_original_answers(benchmark_entry)
        gave_original = is_match(model_answer, original_answers)
        detail["gave_original_answer"] = gave_original
        detail["original_answer"] = original_answers[0] if original_answers else ""

        if correct:
            detail["score"] = 1.0
        else:
            competing = extract_competing_answers(benchmark_entry)
            competing_match = is_match(model_answer, competing) if competing else False
            detail["competing_match"] = competing_match
            if competing_match and not gave_original:
                detail["score"] = COMPETING_ANSWER_WEIGHT
            else:
                detail["score"] = 0.0

    return detail


def _collect_token_stats(model_outputs: list[dict], num_samples: int = 1) -> dict:
    """Aggregate token usage statistics, separating original and altered."""

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
    benchmark_lookup: dict[str, dict],
    verbose: bool = False,
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

        detail = _score_single_output(output, benchmark_lookup)
        if detail is None:
            continue
        details.append(detail)

        if verbose:
            status = "✓" if detail["correct"] else "✗"
            extra = ""
            if detail["riddle_type"] == "altered" and detail.get(
                "gave_original_answer"
            ):
                extra = "  ⚠ gave original answer"
            sample_tag = ""
            if detail.get("sample_index", 1) > 1:
                sample_tag = f"  [sample {detail['sample_index']}]"
            logger.info(
                "  %s  %s (%s): model=%r  accepted=%r%s%s",
                status,
                detail["riddle_id"],
                detail["riddle_type"],
                detail["model_answer"],
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

    original_total = 0
    original_correct = 0
    altered_total = 0
    altered_correct_s1 = 0
    altered_competing = 0
    altered_score_s1 = 0.0
    altered_gave_original = 0

    for key, group in grouped.items():
        riddle_type = key[1]
        rec = next(
            (d for d in group if d.get("sample_index", 1) == 1),
            group[0],
        )

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
                altered_score_s1 += COMPETING_ANSWER_WEIGHT

    # --- Conditioned Override Rate Logic ---
    conditioned_override_total = 0
    conditioned_override_count = 0

    unique_riddles = {k[0] for k in grouped.keys()}
    for rid in unique_riddles:
        orig_group = grouped.get((rid, "original"), [])
        alt_group = grouped.get((rid, "altered"), [])

        if orig_group and alt_group:
            # We use sample 1 to maintain consistency with the baseline metrics
            orig_s1 = next(
                (d for d in orig_group if d.get("sample_index", 1) == 1), orig_group[0]
            )
            alt_s1 = next(
                (d for d in alt_group if d.get("sample_index", 1) == 1), alt_group[0]
            )

            if orig_s1["correct"]:
                conditioned_override_total += 1
                if alt_s1.get("gave_original_answer"):
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

    alt_binary_sum = 0.0
    avg_acc_sum = 0.0

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
        best_of_n_correct = 0
        majority_vote_correct = 0
        altered_count_multi = 0

        for key, group in grouped.items():
            if key[1] != "altered":
                continue
            altered_count_multi += 1

            any_primary = any(d["correct"] for d in group)
            any_competing = any(
                d.get("competing_match") and not d.get("gave_original_answer")
                for d in group
            )
            if any_primary:
                best_of_n_correct += 1
            elif any_competing:
                best_of_n_correct += 1

            answer_counts: Counter[str] = Counter()
            for d in group:
                norm_ans = normalize(d["model_answer"])
                answer_counts[norm_ans] += 1
            majority_answer_norm, _ = answer_counts.most_common(1)[0]
            rep = next(
                d for d in group if normalize(d["model_answer"]) == majority_answer_norm
            )
            if rep["correct"]:
                majority_vote_correct += 1
            elif rep.get("competing_match") and not rep.get("gave_original_answer"):
                majority_vote_correct += COMPETING_ANSWER_WEIGHT

        if altered_count_multi:
            best_of_n_accuracy = round(best_of_n_correct / altered_count_multi, 3)
            majority_vote_accuracy = round(
                majority_vote_correct / altered_count_multi, 3
            )
        else:
            best_of_n_accuracy = 0.0
            majority_vote_accuracy = 0.0

        summary["num_samples"] = num_samples
        summary["best_of_n_accuracy"] = best_of_n_accuracy
        summary["majority_vote_accuracy"] = majority_vote_accuracy

    token_stats = _collect_token_stats(model_outputs, num_samples=num_samples)
    summary.update(token_stats)

    summary["num_riddles"] = len({d["riddle_id"] for d in details})
    summary["original_num_riddles"] = len(
        {d["riddle_id"] for d in details if d["riddle_type"] == "original"}
    )
    summary["altered_num_riddles"] = len(
        {d["riddle_id"] for d in details if d["riddle_type"] == "altered"}
    )

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
            "num_riddles": s.get("num_riddles", s.get("altered_total", 0)),
            "original_num_riddles": s.get("original_num_riddles", 0),
            "altered_num_riddles": s.get("altered_num_riddles", 0),
        }
        if s.get("num_samples", 1) > 1:
            row["num_samples"] = s["num_samples"]
            row["best_of_n_accuracy"] = s["best_of_n_accuracy"]
            row["majority_vote_accuracy"] = s["majority_vote_accuracy"]
        rows.append(row)

    rows.sort(key=lambda r: (-r["total_score"], r["pattern_override_rate"]))

    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank

    ordered: list[dict] = []
    for row in rows:
        entry: dict = {"rank": row["rank"], "model": row["model"]}
        entry["provider"] = row.get("provider", "")
        entry["quantization"] = row.get("quantization", "")
        entry["original_accuracy"] = row["original_accuracy"]
        entry["altered_accuracy"] = row["altered_accuracy"]
        entry["altered_weighted_accuracy"] = row["altered_weighted_accuracy"]
        entry["pattern_override_rate"] = row["pattern_override_rate"]
        entry["conditioned_override_rate"] = row["conditioned_override_rate"]
        entry["average_accuracy"] = row["average_accuracy"]
        entry["total_score"] = row["total_score"]
        entry["total_input_tokens"] = row["total_input_tokens"]
        entry["total_output_tokens"] = row["total_output_tokens"]
        entry["original_input_tokens"] = row["original_input_tokens"]
        entry["original_output_tokens"] = row["original_output_tokens"]
        entry["altered_input_tokens"] = row["altered_input_tokens"]
        entry["altered_output_tokens"] = row["altered_output_tokens"]
        entry["num_riddles"] = row.get("num_riddles", 0)
        entry["original_num_riddles"] = row.get("original_num_riddles", 0)
        entry["altered_num_riddles"] = row.get("altered_num_riddles", 0)
        if "num_samples" in row:
            entry["num_samples"] = row["num_samples"]
            entry["best_of_n_accuracy"] = row["best_of_n_accuracy"]
            entry["majority_vote_accuracy"] = row["majority_vote_accuracy"]
        ordered.append(entry)
    return ordered


def _fmt_tokens(n: int) -> str:
    if n <= 0:
        return "-"
    if n < 1000:
        return str(n)
    if n < 100_000:
        return f"{n / 1000:.1f}k"
    if n < 1_000_000:
        return f"{n / 1000:.0f}k"
    return f"{n / 1_000_000:.1f}M"


def print_leaderboard(leaderboard: list[dict]) -> None:
    col_model = 22
    col_metric = 10
    col_tokens = 8

    def fmt_pct(val: float) -> str:
        return f"{val * 100:5.1f}%"

    header_model = " Model".ljust(col_model)
    header_orig = " Orig Acc".ljust(col_metric)
    header_alt = " Alt Acc".ljust(col_metric)
    header_ovr = " Override".ljust(col_metric)
    header_covr = " Cond Ovr".ljust(col_metric)
    header_score = " Score".ljust(col_metric)
    header_tok = " Tokens".ljust(col_tokens)

    top = (
        f"╔{'═' * col_model}╦{'═' * col_metric}╦{'═' * col_metric}"
        f"╦{'═' * col_metric}╦{'═' * col_metric}╦{'═' * col_metric}╦{'═' * col_tokens}╗"
    )
    mid = (
        f"╠{'═' * col_model}╬{'═' * col_metric}╬{'═' * col_metric}"
        f"╬{'═' * col_metric}╬{'═' * col_metric}╬{'═' * col_metric}╬{'═' * col_tokens}╣"
    )
    bot = (
        f"╚{'═' * col_model}╩{'═' * col_metric}╩{'═' * col_metric}"
        f"╩{'═' * col_metric}╩{'═' * col_metric}╩{'═' * col_metric}╩{'═' * col_tokens}╝"
    )

    print(top)
    print(
        f"║{header_model}║{header_orig}║{header_alt}"
        f"║{header_ovr}║{header_covr}║{header_score}║{header_tok}║"
    )
    print(mid)

    for row in leaderboard:
        model_label = row["model"]
        if row.get("num_samples", 1) > 1:
            model_label = f"{model_label}@{row['num_samples']}"
        model_str = f" {model_label[: col_model - 1]}".ljust(col_model)
        orig_str = f" {fmt_pct(row['original_accuracy'])}".ljust(col_metric)
        alt_str = f" {fmt_pct(row['altered_accuracy'])}".ljust(col_metric)
        ovr_str = f" {fmt_pct(row['pattern_override_rate'])}".ljust(col_metric)
        covr_str = f" {fmt_pct(row['conditioned_override_rate'])}".ljust(col_metric)
        score_str = f" {fmt_pct(row['total_score'])}".ljust(col_metric)
        tok_str = f" {_fmt_tokens(row.get('total_output_tokens', 0))}".ljust(col_tokens)
        print(
            f"║{model_str}║{orig_str}║{alt_str}║{ovr_str}║{covr_str}║{score_str}║{tok_str}║"
        )

    print(bot)


# ---------------------------------------------------------------------------
# Main evaluation driver
# ---------------------------------------------------------------------------


def run_evaluation(args: argparse.Namespace) -> None:
    benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        logger.error("Benchmark file not found: %s", benchmark_path)
        sys.exit(1)

    benchmark_entries = load_jsonl(benchmark_path)
    benchmark_lookup = build_benchmark_lookup(benchmark_entries)
    logger.info(
        "Loaded %d benchmark entries from %s",
        len(benchmark_lookup),
        benchmark_path,
    )

    model_outputs_path = Path(args.model_outputs)
    output_files: list[Path] = []

    if model_outputs_path.is_dir():
        output_files = sorted(model_outputs_path.glob("*.jsonl"))
        if not output_files:
            logger.error("No .jsonl files found in %s", model_outputs_path)
            sys.exit(1)
        logger.info(
            "Found %d model output file(s) in %s",
            len(output_files),
            model_outputs_path,
        )
    elif model_outputs_path.is_file():
        output_files = [model_outputs_path]
    else:
        logger.error("Model outputs path not found: %s", model_outputs_path)
        sys.exit(1)

    version = get_benchmark_version()
    results_root = Path(args.results_dir)
    results_dir = results_root / version
    results_dir.mkdir(parents=True, exist_ok=True)

    all_results: list[dict] = []

    for output_file in output_files:
        logger.info("Evaluating %s …", output_file.name)
        model_outputs = load_jsonl(output_file)

        if not model_outputs:
            logger.warning("  No entries in %s — skipping.", output_file.name)
            continue

        result = evaluate_model(
            model_outputs,
            benchmark_lookup,
            verbose=args.verbose,
        )
        all_results.append(result)

        model_name_safe = output_file.stem
        eval_path = results_dir / f"{model_name_safe}_eval.json"
        write_json(eval_path, result)

        s = result["summary"]
        token_info = ""
        if s.get("total_output_tokens", 0) > 0:
            token_info = f"  tokens_in={s['total_input_tokens']} tokens_out={s['total_output_tokens']}"
        multi_info = ""
        if s.get("num_samples", 1) > 1:
            multi_info = (
                f"  samples={s['num_samples']}"
                f"  best_of_n={s['best_of_n_accuracy'] * 100:.1f}%"
                f"  majority={s['majority_vote_accuracy'] * 100:.1f}%"
            )
        logger.info(
            "  %s — orig=%.1f%%  alt=%.1f%%  avg_acc=%.1f%%  ovr=%.1f%%  cond_ovr=%.1f%%  score=%.1f%%%s%s",
            result["model"],
            s["original_accuracy"] * 100,
            s["altered_accuracy"] * 100,
            s["average_accuracy"] * 100,
            s["pattern_override_rate"] * 100,
            s["conditioned_override_rate"] * 100,
            s["total_score"] * 100,
            multi_info,
            token_info,
        )

    if not all_results:
        logger.error("No models were evaluated.")
        sys.exit(1)

    leaderboard = build_leaderboard(all_results)

    leaderboard_path = results_dir / "leaderboard.json"
    write_json(leaderboard_path, leaderboard)
    logger.info("Leaderboard written to %s", leaderboard_path)

    root_leaderboard_path = results_root / "leaderboard.json"
    results_root.mkdir(parents=True, exist_ok=True)
    write_json(root_leaderboard_path, leaderboard)
    logger.info("Leaderboard also written to %s", root_leaderboard_path)

    print()
    print_leaderboard(leaderboard)
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate model outputs against the Altered Riddles benchmark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default=DEFAULT_BENCHMARK,
        help="Path to the benchmark JSONL file.",
    )
    parser.add_argument(
        "--model-outputs",
        type=str,
        default=DEFAULT_MODEL_OUTPUTS,
        help=(
            "Path to a single model output JSONL file, or a directory "
            "containing multiple output files to evaluate all at once."
        ),
    )
    parser.add_argument(
        "--results-dir",
        type=str,
        default=DEFAULT_RESULTS,
        help="Directory where evaluation results and leaderboard are written.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Show detailed per-riddle results during evaluation.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()
    run_evaluation(args)
