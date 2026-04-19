#!/usr/bin/env python3
"""evaluate.py — LLM-as-a-judge evaluator for benchmark outputs.

Uses a fast LLM to classify model answers as correct, gave_original, or competing.

Usage:
    python -m scripts.evaluate
    python -m scripts.evaluate --provider local --batch-size 20
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from itertools import groupby
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_BENCHMARK_FIXED,
    DEFAULT_MODEL_OUTPUTS,
    DEFAULT_RESULTS,
    provider_names,
    resolve_provider,
)
from scripts.core.io_utils import (
    append_jsonl,
    load_jsonl,
    load_jsonl_if_exists,
    load_template,
    strip_markdown_fences,
    write_json,
)
from scripts.core.llm_client import call_llm_batched

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

FIXED_PATH = DEFAULT_BENCHMARK_FIXED


def parse_judge_response(raw_text: str) -> dict:
    text = strip_markdown_fences(raw_text)
    try:
        data = json.loads(text)
        return {
            "correct": bool(data.get("correct", False)),
            "gave_original": bool(data.get("gave_original", False)),
            "competing": bool(data.get("competing", False)),
        }
    except json.JSONDecodeError:
        return {"correct": False, "gave_original": False, "competing": False}


def extract_run_metadata(model_outputs: list[dict]) -> dict:
    """Validate and return run-level metadata stored on benchmark outputs."""
    reasoning_enabled = False
    reasoning_effort = None
    seen = False

    for output in model_outputs:
        output_reasoning_enabled = bool(output.get("reasoning_enabled", False))
        output_reasoning_effort = output.get("reasoning_effort")
        if not output_reasoning_enabled:
            output_reasoning_effort = None

        if not seen:
            reasoning_enabled = output_reasoning_enabled
            reasoning_effort = output_reasoning_effort
            seen = True
            continue

        if (
            output_reasoning_enabled != reasoning_enabled
            or output_reasoning_effort != reasoning_effort
        ):
            raise ValueError(
                "Inconsistent reasoning settings in benchmark output file: "
                f"expected enabled={reasoning_enabled}, effort={reasoning_effort!r}; "
                f"got enabled={output_reasoning_enabled}, effort={output_reasoning_effort!r}."
            )

    return {
        "reasoning_enabled": reasoning_enabled,
        "reasoning_effort": reasoning_effort,
    }


def evaluate_model(model_outputs, judgments, benchmark_lookup):
    """Score a single model's outputs. Returns results dict."""
    model_name = provider = quantization = ""
    run_metadata = extract_run_metadata(model_outputs)
    details = []

    for output in model_outputs:
        if not model_name:
            model_name = output.get("model", "unknown")
            provider = output.get("provider", "")
            quantization = output.get("quantization", "")

        rid = output.get("riddle_id", "")
        rtype = output.get("riddle_type", "")
        si = output.get("sample_index", 1)
        entry = benchmark_lookup.get(rid)
        if not entry:
            continue

        key = (rid, rtype, si)
        judgment = judgments.get(
            key, {"correct": False, "gave_original": False, "competing": False}
        )

        detail = {
            "riddle_id": rid,
            "riddle_type": rtype,
            "sample_index": si,
            "model_answer": output.get("model_answer", ""),
            "correct": judgment["correct"],
        }

        if rtype == "altered":
            detail["gave_original_answer"] = judgment.get("gave_original", False)
            detail["original_answer"] = entry.get("original_answer", "")

        details.append(detail)

    # Group by (riddle_id, riddle_type) and take sample 1 for main metrics
    def gkey(d):
        return (d["riddle_id"], d["riddle_type"])

    sorted_details = sorted(details, key=gkey)
    grouped = {}
    for k, grp in groupby(sorted_details, key=gkey):
        grouped[k] = list(grp)

    orig_total = orig_correct = 0
    alt_total = alt_correct = alt_gave_orig = 0

    for (rid, rtype), group in grouped.items():
        rec = next((d for d in group if d.get("sample_index", 1) == 1), group[0])
        if rtype == "original":
            orig_total += 1
            if rec["correct"]:
                orig_correct += 1
        elif rtype == "altered":
            alt_total += 1
            if rec["correct"]:
                alt_correct += 1
            if rec.get("gave_original_answer"):
                alt_gave_orig += 1

    # Conditioned override — match by original riddle TEXT, not by riddle_id,
    # because benchmark.py deduplicates original riddles by text.
    orig_text_correct: dict[str, bool] = {}
    for (rid, rtype), group in grouped.items():
        if rtype == "original":
            entry = benchmark_lookup.get(rid, {})
            orig_text = entry.get("original_riddle", "").strip().lower()
            if orig_text:
                orig_text_correct[orig_text] = any(d["correct"] for d in group)

    co_total = co_count = 0
    for (rid, rtype), group in grouped.items():
        if rtype != "altered":
            continue
        entry = benchmark_lookup.get(rid, {})
        orig_text = entry.get("original_riddle", "").strip().lower()
        if not orig_text or orig_text not in orig_text_correct:
            continue
        if orig_text_correct[orig_text]:
            co_total += 1
            if any(d.get("gave_original_answer") for d in group):
                co_count += 1

    # Token stats
    in_toks = [
        o["input_tokens"] for o in model_outputs if o.get("input_tokens") is not None
    ]
    out_toks = [
        o["output_tokens"] for o in model_outputs if o.get("output_tokens") is not None
    ]

    summary = {
        "original_total": orig_total,
        "original_correct": orig_correct,
        "original_accuracy": round(orig_correct / orig_total, 4) if orig_total else 0.0,
        "altered_total": alt_total,
        "altered_correct": alt_correct,
        "altered_accuracy": round(alt_correct / alt_total, 4) if alt_total else 0.0,
        "pattern_override_rate": round(alt_gave_orig / alt_total, 4)
        if alt_total
        else 0.0,
        "conditioned_override_total": co_total,
        "conditioned_override_count": co_count,
        "conditioned_override_rate": round(co_count / co_total, 4) if co_total else 0.0,
        "total_input_tokens": sum(in_toks) if in_toks else 0,
        "total_output_tokens": sum(out_toks) if out_toks else 0,
    }

    return {
        "model": model_name,
        "provider": provider,
        "quantization": quantization,
        "reasoning_enabled": run_metadata["reasoning_enabled"],
        "reasoning_effort": run_metadata["reasoning_effort"],
        "summary": summary,
        "details": details,
    }


def run_evaluation(args):
    load_dotenv()
    judge_model, judge_api_key = resolve_provider(args.provider, args.model)

    # Load benchmark
    bench = load_jsonl(args.benchmark)
    fixed = load_jsonl_if_exists(FIXED_PATH)
    all_bench = bench + fixed
    benchmark_lookup = {e.get("id", ""): e for e in all_bench}

    # Find model output files
    outputs_path = Path(args.model_outputs)
    output_files = (
        sorted(outputs_path.glob("*.jsonl"))
        if outputs_path.is_dir()
        else [outputs_path]
    )
    # Remove entries that containt "one_entry_test" in the filename, which are used for testing.
    output_files = [f for f in output_files if "one_entry_test" not in f.name]
    if not output_files:
        logger.error("No output files found in %s", outputs_path)
        sys.exit(1)

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    judgments_dir = results_dir / "judgments"
    judgments_dir.mkdir(exist_ok=True)

    judge_template = load_template(args.judge_template)
    all_results = []

    for output_file in output_files:
        model_outputs = load_jsonl(output_file)
        if not model_outputs:
            continue

        model_safe = output_file.stem
        cache_path = judgments_dir / f"{model_safe}_judgments.jsonl"

        # Load cached judgments
        judgments = {}
        for j in load_jsonl_if_exists(cache_path):
            judgments[(j["riddle_id"], j["riddle_type"], j.get("sample_index", 1))] = j[
                "judgment"
            ]

        # Find pending
        pending = []
        for o in model_outputs:
            key = (
                o.get("riddle_id", ""),
                o.get("riddle_type", ""),
                o.get("sample_index", 1),
            )
            if key not in judgments:
                pending.append(o)

        if pending:
            logger.info(
                "Judging %d pending outputs for %s...", len(pending), model_safe
            )

            for chunk_start in range(0, len(pending), args.batch_size):
                chunk = pending[chunk_start : chunk_start + args.batch_size]
                prompts, chunk_meta = [], []

                for o in chunk:
                    entry = benchmark_lookup.get(o.get("riddle_id", ""))
                    if not entry:
                        continue
                    rtype = o.get("riddle_type", "")

                    if rtype == "original":
                        accepted = entry.get(
                            "original_accepted_answers",
                            [entry.get("original_answer", "")],
                        )
                    else:
                        accepted = entry.get(
                            "altered_accepted_answers",
                            [entry.get("altered_answer", "")],
                        )
                    original = entry.get(
                        "original_accepted_answers", [entry.get("original_answer", "")]
                    )
                    competing = entry.get("altered_competing_answers", [])

                    prompts.append(
                        judge_template.render(
                            riddle=o.get("riddle_text", ""),
                            model_answer=o.get("model_answer", ""),
                            accepted=accepted,
                            original=original,
                            competing=competing,
                        )
                    )
                    chunk_meta.append(o)

                if not prompts:
                    continue

                logger.info(
                    "  Judge batch [%d-%d]", chunk_start + 1, chunk_start + len(chunk)
                )
                results = call_llm_batched(
                    prompts,
                    provider=args.provider,
                    model=judge_model,
                    temperature=0.0,
                    api_key=judge_api_key,
                    max_concurrency=args.batch_size,
                )

                for o, res in zip(chunk_meta, results):
                    key = (
                        o.get("riddle_id", ""),
                        o.get("riddle_type", ""),
                        o.get("sample_index", 1),
                    )
                    parsed = (
                        parse_judge_response(res.text)
                        if not isinstance(res, BaseException)
                        else {
                            "correct": False,
                            "gave_original": False,
                            "competing": False,
                        }
                    )
                    judgments[key] = parsed
                    append_jsonl(
                        cache_path,
                        {
                            "riddle_id": key[0],
                            "riddle_type": key[1],
                            "sample_index": key[2],
                            "judgment": parsed,
                        },
                    )

                time.sleep(0.5)

        result = evaluate_model(model_outputs, judgments, benchmark_lookup)
        all_results.append(result)

        eval_path = results_dir / f"{model_safe}_eval.json"
        write_json(eval_path, result)
        s = result["summary"]
        logger.info(
            "  %s — orig=%.1f%% alt=%.1f%% override=%.1f%% cond_override=%.1f%%",
            result["model"],
            s["original_accuracy"] * 100,
            s["altered_accuracy"] * 100,
            s["pattern_override_rate"] * 100,
            s["conditioned_override_rate"] * 100,
        )

    if not all_results:
        logger.error("No results to save.")
        sys.exit(1)

    write_json(results_dir / "all_results.json", all_results)
    logger.info("All evaluation results saved to %s", results_dir)


def parse_args():
    parser = argparse.ArgumentParser(
        description="LLM-as-a-judge evaluator.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    parser.add_argument("--model-outputs", default=DEFAULT_MODEL_OUTPUTS)
    parser.add_argument("--results-dir", default=DEFAULT_RESULTS)
    parser.add_argument("--judge-template", default="prompts/judge.j2")
    parser.add_argument("--provider", choices=provider_names(), default="local")
    parser.add_argument("--model", default=None)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    run_evaluation(parse_args())
