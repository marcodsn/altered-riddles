#!/usr/bin/env python3
"""sanity_check.py — Two-phase LLM accuracy checker on source riddles.

Solve and judge are intentionally separated so you can run different solver
models at different times, accumulate answers, then (re-)run the judge at any
point to get updated accuracy figures.

Phase 1 — Solve (can be repeated for any number of models):
    python -m scripts.sanity_check solve --solvers local gemini openai:gpt-4o
    python -m scripts.sanity_check solve --solvers mistral:mistral-small-2603

Phase 2 — Judge (re-run any time after adding more solver outputs):
    python -m scripts.sanity_check judge
    python -m scripts.sanity_check judge --judge-provider openai --output results/sanity.json

Answers are stored in ``data/sanity/answers/<model>.jsonl``.
Judgments are cached in ``data/sanity/judgments/<model>_judgments.jsonl``.
Final results are written to ``data/sanity/results.json`` by default.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_SOURCE,
    provider_names,
    resolve_provider,
)
from scripts.core.io_utils import (
    append_jsonl,
    load_jsonl_if_exists,
    load_source_riddles_csv,
    load_template,
    sanitize_model_name,
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

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

DEFAULT_SANITY_DIR = "data/sanity"
DEFAULT_ANSWERS_DIR = "data/sanity/answers"
DEFAULT_JUDGMENTS_DIR = "data/sanity/judgments"
DEFAULT_RESULTS_PATH = "data/sanity/results.json"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def parse_solver_spec(spec: str) -> tuple[str, str | None]:
    """Parse ``"provider:model"`` or bare ``"provider"`` → ``(provider, model|None)``."""
    if ":" in spec:
        provider, model = spec.split(":", 1)
        return provider.strip(), model.strip() or None
    return spec.strip(), None


def parse_model_answer(raw_text: str) -> str:
    """Extract ``answer`` from a solve-response JSON string.

    Falls back to the raw text (≤ 200 chars) on parse failure.
    """
    text = strip_markdown_fences(raw_text)
    try:
        data = json.loads(text)
        return str(data.get("answer", "")).strip()
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse solver JSON: %s", text[:200])
        return raw_text.strip()[:200]


def parse_judge_response(raw_text: str) -> dict[str, bool]:
    """Extract ``correct`` / ``gave_original`` / ``competing`` from judge JSON.

    All keys default to ``False`` on parse failure.
    """
    text = strip_markdown_fences(raw_text)
    try:
        data = json.loads(text)
        return {
            "correct": bool(data.get("correct", False)),
            "gave_original": bool(data.get("gave_original", False)),
            "competing": bool(data.get("competing", False)),
        }
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse judge JSON: %s", text[:200])
        return {"correct": False, "gave_original": False, "competing": False}


# ---------------------------------------------------------------------------
# Phase 1 — Solve
# ---------------------------------------------------------------------------


def run_solve(args: argparse.Namespace) -> None:
    """Run solver LLMs on source riddles and persist answers to disk."""
    load_dotenv()

    riddles = load_source_riddles_csv(args.source)
    if not riddles:
        logger.error("No riddles loaded from %s", args.source)
        sys.exit(1)
    logger.info("Loaded %d source riddles from %s", len(riddles), args.source)

    answers_dir = Path(args.answers_dir)
    answers_dir.mkdir(parents=True, exist_ok=True)

    solve_template = load_template("prompts/solve.j2")

    for solver_spec in args.solvers:
        provider, model_override = parse_solver_spec(solver_spec)
        model, api_key = resolve_provider(provider, model_override)
        solver_label = f"{provider}/{model}"
        safe_name = sanitize_model_name(model)
        output_path = answers_dir / f"{safe_name}.jsonl"

        logger.info("=" * 60)
        logger.info("Solver: %s", solver_label)
        logger.info("Output: %s", output_path)
        logger.info("=" * 60)

        # Load already-answered riddle indices so we can skip them on resume.
        existing: list[dict] = load_jsonl_if_exists(output_path)
        answered_indices: set[int] = {r["riddle_idx"] for r in existing}
        pending = [(idx, r) for idx, r in enumerate(riddles) if idx not in answered_indices]

        if not pending:
            logger.info("All riddles already answered for %s — skipping.", solver_label)
            continue

        logger.info(
            "Answering %d riddles (%d already cached).",
            len(pending),
            len(answered_indices),
        )

        # Build prompts for pending riddles.
        prompts = [
            solve_template.render(
                riddle=r["riddle"],
                chain_of_thought=args.chain_of_thought,
            )
            for _, r in pending
        ]

        # Dispatch in batches.
        responses: list = []
        for chunk_start in range(0, len(prompts), args.batch_size):
            chunk = prompts[chunk_start : chunk_start + args.batch_size]
            logger.info(
                "  Batch [%d–%d / %d]...",
                chunk_start + 1,
                chunk_start + len(chunk),
                len(prompts),
            )
            results = call_llm_batched(
                chunk,
                provider=provider,
                model=model,
                temperature=args.temperature,
                api_key=api_key,
                max_concurrency=args.batch_size,
                max_output_tokens=args.max_output_tokens,
            )
            responses.extend(results)

        # Persist answers.
        saved = 0
        for (idx, r), resp in zip(pending, responses):
            if isinstance(resp, BaseException):
                logger.error("  Solver failed for riddle %d: %s", idx, resp)
                model_answer = ""
            else:
                model_answer = parse_model_answer(resp.text)

            record = {
                "riddle_idx": idx,
                "riddle": r["riddle"],
                "expected_answer": r["answer"],
                "model_answer": model_answer,
                "solver": solver_label,
            }
            append_jsonl(output_path, record)
            saved += 1

        logger.info("  Saved %d answer(s) to %s", saved, output_path)

    logger.info("=" * 60)
    logger.info("Solve phase complete.")
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Phase 2 — Judge
# ---------------------------------------------------------------------------


def run_judge(args: argparse.Namespace) -> None:
    """Judge all saved solver answers and compute accuracy metrics."""
    load_dotenv()

    answers_dir = Path(args.answers_dir)
    if not answers_dir.exists():
        logger.error("Answers directory not found: %s — run the 'solve' phase first.", answers_dir)
        sys.exit(1)

    answer_files = sorted(answers_dir.glob("*.jsonl"))
    if not answer_files:
        logger.error("No .jsonl files found in %s — run the 'solve' phase first.", answers_dir)
        sys.exit(1)

    judgments_dir = Path(args.judgments_dir)
    judgments_dir.mkdir(parents=True, exist_ok=True)

    judge_model, judge_api_key = resolve_provider(args.judge_provider, args.judge_model)
    judge_label = f"{args.judge_provider}/{judge_model}"
    logger.info("Judge: %s", judge_label)

    judge_template = load_template("prompts/judge.j2")

    # Collect per-model results: {solver_label: {riddle_idx: correct}}
    all_model_results: dict[str, dict[int, bool]] = {}
    # Metadata per riddle (from any answer file — they all share the same CSV).
    riddle_meta: dict[int, dict[str, str]] = {}

    for answer_file in answer_files:
        answers: list[dict] = load_jsonl_if_exists(answer_file)
        if not answers:
            continue

        solver_label = answers[0].get("solver", answer_file.stem)
        safe_name = answer_file.stem
        judgment_cache_path = judgments_dir / f"{safe_name}_judgments.jsonl"

        logger.info("=" * 60)
        logger.info("Processing solver: %s", solver_label)
        logger.info("Answer file     : %s", answer_file)
        logger.info("Judgment cache  : %s", judgment_cache_path)
        logger.info("=" * 60)

        # Load existing judgment cache: {riddle_idx: judgment_dict}
        cached_judgments: dict[int, dict[str, bool]] = {}
        for j in load_jsonl_if_exists(judgment_cache_path):
            cached_judgments[j["riddle_idx"]] = j["judgment"]

        # Collect riddle metadata while we iterate.
        for a in answers:
            idx = a["riddle_idx"]
            riddle_meta.setdefault(
                idx, {"riddle": a["riddle"], "expected_answer": a["expected_answer"]}
            )

        # Identify answers that still need judging.
        pending = [a for a in answers if a["riddle_idx"] not in cached_judgments]

        if pending:
            logger.info("Running judge on %d pending answers...", len(pending))

            # Build judge prompts for pending answers.
            judge_prompts: list[str | None] = []
            for a in pending:
                if not a.get("model_answer"):
                    judge_prompts.append(None)
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

            valid_indices = [i for i, p in enumerate(judge_prompts) if p is not None]
            valid_prompts: list[str] = [p for p in judge_prompts if p is not None]

            judge_raw: list = []
            for chunk_start in range(0, len(valid_prompts), args.batch_size):
                chunk = valid_prompts[chunk_start : chunk_start + args.batch_size]
                logger.info(
                    "  Judge batch [%d–%d / %d]...",
                    chunk_start + 1,
                    chunk_start + len(chunk),
                    len(valid_prompts),
                )
                results = call_llm_batched(
                    chunk,
                    provider=args.judge_provider,
                    model=judge_model,
                    temperature=args.judge_temperature,
                    api_key=judge_api_key,
                    max_concurrency=args.batch_size,
                )
                judge_raw.extend(results)

            # Map judge results back to riddle indices and cache them.
            parsed_by_pending_idx: dict[int, dict[str, bool]] = {}
            for list_idx, pending_idx in enumerate(valid_indices):
                res = judge_raw[list_idx]
                if isinstance(res, BaseException):
                    logger.error(
                        "  Judge failed for riddle %d: %s",
                        pending[pending_idx]["riddle_idx"],
                        res,
                    )
                    judgment = {"correct": False, "gave_original": False, "competing": False}
                else:
                    judgment = parse_judge_response(res.text)
                parsed_by_pending_idx[pending_idx] = judgment

            for i, a in enumerate(pending):
                judgment = parsed_by_pending_idx.get(
                    i, {"correct": False, "gave_original": False, "competing": False}
                )
                cached_judgments[a["riddle_idx"]] = judgment
                append_jsonl(
                    judgment_cache_path,
                    {"riddle_idx": a["riddle_idx"], "judgment": judgment},
                )

        else:
            logger.info("All judgments already cached for %s.", solver_label)

        # Compute per-model correctness map.
        model_correct: dict[int, bool] = {}
        for a in answers:
            idx = a["riddle_idx"]
            j = cached_judgments.get(idx, {"correct": False})
            model_correct[idx] = j["correct"]

        correct_count = sum(model_correct.values())
        total = len(answers)
        accuracy = correct_count / total if total else 0.0

        logger.info(
            "  %s — %d / %d correct (%.2f%%)", solver_label, correct_count, total, accuracy * 100
        )
        all_model_results[solver_label] = model_correct

    if not all_model_results:
        logger.error("No results to aggregate. Exiting.")
        sys.exit(1)

    # ── Per-model summary ─────────────────────────────────────────────
    model_summaries: list[dict] = []
    accuracies: list[float] = []

    for solver_label, model_correct in all_model_results.items():
        correct_count = sum(model_correct.values())
        total = len(model_correct)
        accuracy = correct_count / total if total else 0.0
        model_summaries.append(
            {
                "solver": solver_label,
                "correct": correct_count,
                "total": total,
                "accuracy": round(accuracy, 4),
            }
        )
        accuracies.append(accuracy)

    mean_accuracy = sum(accuracies) / len(accuracies) if accuracies else 0.0

    # ── Per-riddle mean accuracy ──────────────────────────────────────
    # For each riddle, compute the fraction of models that answered it correctly.
    all_riddle_indices = sorted(riddle_meta.keys())
    per_riddle: list[dict] = []

    for idx in all_riddle_indices:
        meta = riddle_meta[idx]
        models_with_result = [solver for solver, mc in all_model_results.items() if idx in mc]
        correct_models = [
            solver for solver in models_with_result if all_model_results[solver][idx]
        ]
        incorrect_models = [
            solver for solver in models_with_result if not all_model_results[solver][idx]
        ]
        riddle_mean = len(correct_models) / len(models_with_result) if models_with_result else 0.0
        per_riddle.append(
            {
                "riddle_idx": idx,
                "riddle": meta["riddle"],
                "expected_answer": meta["expected_answer"],
                "mean_accuracy": round(riddle_mean, 4),
                "models_evaluated": len(models_with_result),
                "models_correct": correct_models,
                "models_incorrect": incorrect_models,
            }
        )

    # Sort by mean_accuracy ascending so the hardest riddles come first.
    per_riddle_sorted = sorted(per_riddle, key=lambda r: r["mean_accuracy"])

    # ── Print summary table ───────────────────────────────────────────
    print()
    print("=" * 62)
    print("SANITY CHECK SUMMARY")
    print("=" * 62)
    print(f"{'Model':<40} {'Accuracy':>10} {'Correct':>10}")
    print("-" * 62)
    for s in model_summaries:
        print(f"{s['solver']:<40} {s['accuracy'] * 100:>9.2f}% {s['correct']:>6}/{s['total']}")
    print("-" * 62)
    print(f"{'MEAN ACCURACY':<40} {mean_accuracy * 100:>9.2f}%")
    print("=" * 62)

    # Print the 10 hardest riddles.
    print()
    print(f"{'Hardest riddles (lowest mean accuracy across models)':}")
    print("-" * 62)
    for entry in per_riddle_sorted[:10]:
        print(
            f"  [{entry['mean_accuracy'] * 100:5.1f}%]  "
            f"{entry['riddle'][:55]}{'…' if len(entry['riddle']) > 55 else ''}"
        )
        print(f"           Expected: {entry['expected_answer']}")
    print()

    # Print number of riddles above certain accuracy thresholds.
    thresholds = [0.8, 0.6, 0.4]
    print("Riddle difficulty breakdown:")
    for t in thresholds:
        count = sum(1 for r in per_riddle if r["mean_accuracy"] >= t)
        print(f"  {count} riddles with mean accuracy ≥ {t * 100:.0f}%")

    # ── Persist results ───────────────────────────────────────────────
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = {
        "judge": judge_label,
        "models": model_summaries,
        "mean_accuracy": round(mean_accuracy, 4),
        "per_riddle": per_riddle,  # full list, ordered by riddle_idx
        "per_riddle_by_difficulty": per_riddle_sorted,  # sorted hardest-first
    }
    write_json(output_path, results)
    logger.info("Results saved to %s", output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_solve_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "solve",
        help="Run solver LLMs on source riddles and save answers to disk.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--solvers",
        nargs="+",
        required=True,
        metavar="PROVIDER[:MODEL]",
        help=(
            "One or more solver specs as 'provider' or 'provider:model' "
            "(e.g. 'gemini' 'openai:gpt-4o' 'local:qwen3-8b')."
        ),
    )
    p.add_argument(
        "--source",
        type=str,
        default=DEFAULT_SOURCE,
        help="Path to the source riddles CSV.",
    )
    p.add_argument(
        "--answers-dir",
        type=str,
        default=DEFAULT_ANSWERS_DIR,
        help="Directory where solver answer JSONL files are stored.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Max concurrent LLM requests per batch.",
    )
    p.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for solver LLMs.",
    )
    p.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Max output tokens passed to the solver LLM.",
    )
    p.add_argument(
        "--chain-of-thought",
        action="store_true",
        default=False,
        help="Enable chain-of-thought reasoning in solve prompts.",
    )
    p.set_defaults(func=run_solve)


def build_judge_parser(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = sub.add_parser(
        "judge",
        help="Judge saved solver answers and report accuracy metrics.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--answers-dir",
        type=str,
        default=DEFAULT_ANSWERS_DIR,
        help="Directory containing solver answer JSONL files.",
    )
    p.add_argument(
        "--judgments-dir",
        type=str,
        default=DEFAULT_JUDGMENTS_DIR,
        help="Directory for judgment cache files.",
    )
    p.add_argument(
        "--output",
        type=str,
        default=DEFAULT_RESULTS_PATH,
        help="Path to write the aggregated results JSON.",
    )
    p.add_argument(
        "--judge-provider",
        type=str,
        choices=provider_names(),
        default="local",
        help="Provider for the judge LLM.",
    )
    p.add_argument(
        "--judge-model",
        type=str,
        default=None,
        help="Model for the judge LLM (None = provider default).",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Max concurrent judge LLM requests per batch.",
    )
    p.add_argument(
        "--judge-temperature",
        type=float,
        default=0.0,
        help="Sampling temperature for the judge LLM.",
    )
    p.set_defaults(func=run_judge)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Two-phase LLM accuracy checker on source riddles. "
            "Use 'solve' to collect answers, 'judge' to evaluate them."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True
    build_solve_parser(sub)
    build_judge_parser(sub)
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = parse_args()
    args.func(args)
