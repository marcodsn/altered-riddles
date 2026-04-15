#!/usr/bin/env python3
"""sanity_check.py — Two-phase accuracy checker on source riddles.

Phase 1 — Solve: python -m scripts.sanity_check solve --solvers local gemini openai:gpt-4o
Phase 2 — Judge: python -m scripts.sanity_check judge
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_SANITY_RESULTS,
    DEFAULT_SOURCE,
    provider_names,
    resolve_provider,
)
from scripts.core.io_utils import (
    append_jsonl,
    load_jsonl_if_exists,
    load_source_riddles,
    load_template,
    sanitize_model_name,
    strip_markdown_fences,
    write_json,
)
from scripts.core.llm_client import call_llm_batched

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

ANSWERS_DIR = "data/sanity/answers"
JUDGMENTS_DIR = "data/sanity/judgments"
RESULTS_PATH = DEFAULT_SANITY_RESULTS


def parse_solver_spec(spec: str) -> tuple[str, str | None]:
    if ":" in spec:
        provider, model = spec.split(":", 1)
        return provider.strip(), model.strip() or None
    return spec.strip(), None


def parse_model_answer(raw_text: str) -> str:
    text = strip_markdown_fences(raw_text)
    try:
        data = json.loads(text)
        return str(data.get("answer", "")).strip()
    except (json.JSONDecodeError, TypeError):
        return raw_text.strip()[:200]


def parse_judge_response(raw_text: str) -> dict[str, bool]:
    text = strip_markdown_fences(raw_text)
    try:
        data = json.loads(text)
        return {"correct": bool(data.get("correct", False))}
    except (json.JSONDecodeError, TypeError):
        return {"correct": False}


def run_solve(args):
    load_dotenv()
    riddles = load_source_riddles(args.source)
    if not riddles:
        logger.error("No riddles loaded from %s", args.source)
        sys.exit(1)
    logger.info("Loaded %d source riddles", len(riddles))

    answers_dir = Path(ANSWERS_DIR)
    answers_dir.mkdir(parents=True, exist_ok=True)
    solve_template = load_template("prompts/solve.j2")

    for solver_spec in args.solvers:
        provider, model_override = parse_solver_spec(solver_spec)
        model, api_key = resolve_provider(provider, model_override)
        safe_name = sanitize_model_name(model)
        output_path = answers_dir / f"{safe_name}.jsonl"

        logger.info("Solver: %s/%s → %s", provider, model, output_path)

        existing = load_jsonl_if_exists(output_path)
        answered_indices = {r["riddle_idx"] for r in existing}
        pending = [(idx, r) for idx, r in enumerate(riddles) if idx not in answered_indices]

        if not pending:
            logger.info("All riddles already answered — skipping.")
            continue

        logger.info("Answering %d riddles (%d cached).", len(pending), len(answered_indices))

        prompts = [
            solve_template.render(riddle=r["riddle"], chain_of_thought=False) for _, r in pending
        ]

        responses = []
        for chunk_start in range(0, len(prompts), args.batch_size):
            chunk = prompts[chunk_start : chunk_start + args.batch_size]
            logger.info(
                "  Batch [%d-%d / %d]", chunk_start + 1, chunk_start + len(chunk), len(prompts)
            )
            results = call_llm_batched(
                chunk,
                provider=provider,
                model=model,
                temperature=0.0,
                api_key=api_key,
                max_concurrency=args.batch_size,
            )
            responses.extend(results)

        for (idx, r), resp in zip(pending, responses):
            model_answer = ""
            if isinstance(resp, BaseException):
                logger.error("Solver failed for riddle %d: %s", idx, resp)
            else:
                model_answer = parse_model_answer(resp.text)
            append_jsonl(
                output_path,
                {
                    "riddle_idx": idx,
                    "riddle": r["riddle"],
                    "expected_answer": r["answer"],
                    "model_answer": model_answer,
                    "solver": f"{provider}/{model}",
                },
            )

    logger.info("Solve phase complete.")


def run_judge(args):
    load_dotenv()
    answers_dir = Path(ANSWERS_DIR)
    if not answers_dir.exists():
        logger.error("No answers directory. Run 'solve' first.")
        sys.exit(1)

    answer_files = sorted(answers_dir.glob("*.jsonl"))
    if not answer_files:
        logger.error("No answer files found.")
        sys.exit(1)

    judgments_dir = Path(JUDGMENTS_DIR)
    judgments_dir.mkdir(parents=True, exist_ok=True)

    judge_model, judge_api_key = resolve_provider(args.judge_provider, args.judge_model)
    logger.info("Judge: %s/%s", args.judge_provider, judge_model)

    judge_template = load_template("prompts/judge.j2")

    all_model_results: dict[str, dict[int, bool]] = {}
    riddle_meta: dict[int, dict[str, str]] = {}

    for answer_file in answer_files:
        answers = load_jsonl_if_exists(answer_file)
        if not answers:
            continue

        solver_label = answers[0].get("solver", answer_file.stem)
        safe_name = answer_file.stem
        judgment_cache_path = judgments_dir / f"{safe_name}_judgments.jsonl"

        logger.info("Processing solver: %s", solver_label)

        cached_judgments: dict[int, dict] = {}
        for j in load_jsonl_if_exists(judgment_cache_path):
            cached_judgments[j["riddle_idx"]] = j["judgment"]

        for a in answers:
            riddle_meta.setdefault(
                a["riddle_idx"], {"riddle": a["riddle"], "expected_answer": a["expected_answer"]}
            )

        pending = [a for a in answers if a["riddle_idx"] not in cached_judgments]

        if pending:
            logger.info("Judging %d pending answers...", len(pending))
            judge_prompts = []
            valid_pending = []
            for a in pending:
                if not a.get("model_answer"):
                    cached_judgments[a["riddle_idx"]] = {"correct": False}
                    append_jsonl(
                        judgment_cache_path,
                        {"riddle_idx": a["riddle_idx"], "judgment": {"correct": False}},
                    )
                    continue
                judge_prompts.append(
                    judge_template.render(
                        riddle=a["riddle"],
                        model_answer=a["model_answer"],
                        accepted=[a["expected_answer"]],
                        original=[a["expected_answer"]],
                        competing=[],
                    )
                )
                valid_pending.append(a)

            judge_raw = []
            for chunk_start in range(0, len(judge_prompts), args.batch_size):
                chunk = judge_prompts[chunk_start : chunk_start + args.batch_size]
                logger.info(
                    "  Judge batch [%d-%d / %d]",
                    chunk_start + 1,
                    chunk_start + len(chunk),
                    len(judge_prompts),
                )
                results = call_llm_batched(
                    chunk,
                    provider=args.judge_provider,
                    model=judge_model,
                    temperature=0.0,
                    api_key=judge_api_key,
                    max_concurrency=args.batch_size,
                )
                judge_raw.extend(results)

            for a, res in zip(valid_pending, judge_raw):
                if isinstance(res, BaseException):
                    judgment = {"correct": False}
                else:
                    judgment = parse_judge_response(res.text)
                cached_judgments[a["riddle_idx"]] = judgment
                append_jsonl(
                    judgment_cache_path, {"riddle_idx": a["riddle_idx"], "judgment": judgment}
                )

        model_correct = {}
        for a in answers:
            j = cached_judgments.get(a["riddle_idx"], {"correct": False})
            model_correct[a["riddle_idx"]] = j["correct"]

        all_model_results[solver_label] = model_correct

    if not all_model_results:
        logger.error("No results to aggregate.")
        sys.exit(1)

    # Per-model summary
    model_summaries = []
    for solver_label, mc in all_model_results.items():
        correct = sum(mc.values())
        total = len(mc)
        acc = correct / total if total else 0.0
        model_summaries.append(
            {"solver": solver_label, "correct": correct, "total": total, "accuracy": round(acc, 4)}
        )

    mean_accuracy = sum(s["accuracy"] for s in model_summaries) / len(model_summaries)

    # Per-riddle mean accuracy
    all_riddle_indices = sorted(riddle_meta.keys())
    per_riddle = []
    for idx in all_riddle_indices:
        meta = riddle_meta[idx]
        models_with_result = [s for s, mc in all_model_results.items() if idx in mc]
        correct_models = [s for s in models_with_result if all_model_results[s][idx]]
        riddle_mean = len(correct_models) / len(models_with_result) if models_with_result else 0.0
        per_riddle.append(
            {
                "riddle_idx": idx,
                "riddle": meta["riddle"],
                "expected_answer": meta["expected_answer"],
                "mean_accuracy": round(riddle_mean, 4),
                "models_evaluated": len(models_with_result),
                "models_correct": correct_models,
            }
        )

    # Print summary
    print("\n" + "=" * 62)
    print("SANITY CHECK SUMMARY")
    print("=" * 62)
    print(f"{'Model':<40} {'Accuracy':>10} {'Correct':>10}")
    print("-" * 62)
    for s in model_summaries:
        print(f"{s['solver']:<40} {s['accuracy'] * 100:>9.2f}% {s['correct']:>6}/{s['total']}")
    print("-" * 62)
    print(f"{'MEAN ACCURACY':<40} {mean_accuracy * 100:>9.2f}%")
    print("=" * 62)

    # Hardest riddles
    per_riddle_sorted = sorted(per_riddle, key=lambda r: r["mean_accuracy"])
    print(f"\nHardest riddles (lowest mean accuracy):")
    print("-" * 62)
    for entry in per_riddle_sorted[:10]:
        print(
            f"  [{entry['mean_accuracy'] * 100:5.1f}%] {entry['riddle'][:55]}{'...' if len(entry['riddle']) > 55 else ''}"
        )
        print(f"           Expected: {entry['expected_answer']}")

    # Riddle difficulty breakdown
    common = sum(1 for r in per_riddle if r["mean_accuracy"] >= 0.6)
    print(f"\n  {common} riddles with mean accuracy >= 60% (common riddles for generation)")

    # Save results
    results = {
        "judge": f"{args.judge_provider}/{judge_model}",
        "models": model_summaries,
        "mean_accuracy": round(mean_accuracy, 4),
        "per_riddle": per_riddle,
    }
    write_json(args.output, results)
    logger.info("Results saved to %s", args.output)


def parse_args():
    parser = argparse.ArgumentParser(description="Two-phase sanity checker on source riddles.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_solve = sub.add_parser(
        "solve",
        help="Run solver LLMs on source riddles.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_solve.add_argument("--solvers", nargs="+", required=True, metavar="PROVIDER[:MODEL]")
    p_solve.add_argument("--source", default=DEFAULT_SOURCE)
    p_solve.add_argument("--batch-size", type=int, default=10)
    p_solve.set_defaults(func=run_solve)

    p_judge = sub.add_parser(
        "judge",
        help="Judge saved answers and compute accuracy.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_judge.add_argument("--judge-provider", choices=provider_names(), default="local")
    p_judge.add_argument("--judge-model", default=None)
    p_judge.add_argument("--output", default=RESULTS_PATH)
    p_judge.add_argument("--batch-size", type=int, default=10)
    p_judge.set_defaults(func=run_judge)

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    args.func(args)
