#!/usr/bin/env python3
"""benchmark.py — Run the Altered Riddles benchmark against a model.

Usage:
    python -m scripts.benchmark --provider gemini
    python -m scripts.benchmark --provider openai --model gpt-5.4
    python -m scripts.benchmark --temperature 0.7 --num-samples 5
    python -m scripts.benchmark --only altered --batch-size 20
    python -m scripts.benchmark --provider openai --reasoning --one-entry-test
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_BENCHMARK,
    DEFAULT_BENCHMARK_FIXED,
    DEFAULT_MODEL_OUTPUTS,
    provider_names,
    resolve_provider,
)
from scripts.core.io_utils import (
    append_jsonl,
    load_jsonl,
    load_jsonl_if_exists,
    load_template,
    sanitize_model_name,
    strip_markdown_fences,
)
from scripts.core.llm_client import LLMResponse, call_llm, call_llm_batched_streaming
from scripts.core.reasoning import DEFAULT_EFFORT, EFFORTS, build_plan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

FIXED_PATH = DEFAULT_BENCHMARK_FIXED


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse_model_response(raw_text: str) -> tuple[str, str]:
    """Extract (answer, reasoning) from a model response."""
    text = strip_markdown_fences(raw_text)
    try:
        data = json.loads(text)
        return (
            str(data.get("answer", "")).strip(),
            str(data.get("reasoning", "")).strip(),
        )
    except json.JSONDecodeError:
        return raw_text.strip()[:500], ""


def build_tasks(
    entries: list[dict],
    only: str,
    num_samples: int,
) -> list[tuple[dict, str, int]]:
    """Build (entry, riddle_type, sample_index) task tuples.

    Original riddles are deduplicated by text so that the same original
    appearing across many altered entries is only tested once.
    """
    tasks: list[tuple[dict, str, int]] = []
    seen_originals: set[str] = set()

    for entry in entries:
        types: list[str] = []

        if only in ("both", "original"):
            orig = entry.get("original_riddle", "")
            if orig and orig not in seen_originals:
                seen_originals.add(orig)
                types.append("original")

        if only in ("both", "altered"):
            types.append("altered")

        for rtype in types:
            # Only one sample for originals (no variance expected)
            n = 1 if rtype == "original" else num_samples
            for si in range(1, n + 1):
                tasks.append((entry, rtype, si))

    return tasks


def already_answered(output_path: str | Path) -> set[tuple[str, str, int]]:
    """Return the set of (riddle_id, riddle_type, sample_index) already on disk."""
    keys: set[tuple[str, str, int]] = set()
    if not Path(output_path).exists():
        return keys
    for r in load_jsonl(output_path):
        keys.add(
            (
                r.get("riddle_id", ""),
                r.get("riddle_type", ""),
                r.get("sample_index", 1),
            )
        )
    return keys


def make_record(
    riddle_id: str,
    riddle_type: str,
    sample_index: int,
    riddle_text: str,
    answer: str,
    reasoning: str,
    raw_response: str,
    model_name: str,
    provider: str,
    temperature: float,
    quantization: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    reasoning_enabled: bool,
    reasoning_effort: str | None,
) -> dict:
    return {
        "riddle_id": riddle_id,
        "riddle_type": riddle_type,
        "sample_index": sample_index,
        "riddle_text": riddle_text,
        "model_answer": answer,
        "model_reasoning": reasoning,
        "raw_response": raw_response,
        "model": model_name.lower(),
        "provider": provider,
        "quantization": quantization,
        "temperature": temperature,
        "reasoning_enabled": reasoning_enabled,
        "reasoning_effort": reasoning_effort,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_benchmark(args: argparse.Namespace) -> None:
    load_dotenv()
    model_name, api_key = resolve_provider(args.provider, args.model)

    reasoning_plan = build_plan(
        provider=args.provider,
        model=model_name,
        reasoning=args.reasoning,
        effort=args.reasoning_effort,
    )
    if reasoning_plan.enabled:
        logger.info(
            "Reasoning ENABLED (effort=%s) for %s/%s",
            reasoning_plan.effort,
            args.provider,
            model_name,
        )
    else:
        logger.info("Reasoning DISABLED for %s/%s", args.provider, model_name)

    num_samples = args.num_samples
    batch_size = args.batch_size
    if args.one_entry_test:
        if num_samples != 1:
            logger.info("One-entry test mode: forcing num_samples=1.")
        if batch_size != 1:
            logger.info("One-entry test mode: forcing batch_size=1.")
        num_samples = 1
        batch_size = 1

    if num_samples > 1 and args.temperature == 0.0:
        logger.warning("Multiple samples at temp=0 are redundant. Forcing num_samples=1.")
        num_samples = 1

    # Load benchmark entries (merge fixed + auxiliary)
    entries = load_jsonl(args.benchmark)
    fixed = load_jsonl_if_exists(FIXED_PATH)
    if fixed:
        entries = entries + fixed
        logger.info(
            "Merged %d auxiliary + %d fixed = %d total entries.",
            len(entries) - len(fixed),
            len(fixed),
            len(entries),
        )
    else:
        logger.info("Loaded %d benchmark entries.", len(entries))

    template = load_template(args.prompt_template)

    # Determine output path
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_model_name(model_name).lower()
    temp_suffix = f"_temp{args.temperature}" if args.temperature > 0 else ""
    test_suffix = "_one_entry_test" if args.one_entry_test else ""
    output_path = output_dir / f"{safe_name}{temp_suffix}{reasoning_plan.tag}{test_suffix}.jsonl"

    # Resume support
    done = set() if args.one_entry_test else already_answered(output_path)
    if done:
        logger.info("Resuming: %d records already in %s", len(done), output_path)

    tasks = build_tasks(entries, args.only, num_samples)
    pending = [(e, rt, si) for e, rt, si in tasks if (e.get("id", ""), rt, si) not in done]
    if args.one_entry_test and pending:
        pending = [
            task
            for task in pending
            if task[0].get("original_riddle" if task[1] == "original" else "altered_riddle", "")
        ][:1]

    logger.info(
        "Tasks: %d total, %d pending (model=%s, temp=%.2f, samples=%d)",
        len(tasks),
        len(pending),
        model_name,
        args.temperature,
        num_samples,
    )

    if not pending:
        if args.one_entry_test:
            logger.info("One-entry test mode: no pending riddle with prompt text was found.")
            return
        logger.info("All riddles already answered.")
        return

    total = len(pending)
    if args.one_entry_test:
        entry, rtype, si = pending[0]
        logger.info(
            "One-entry test mode: running %s (%s, s%d) and writing to %s",
            entry.get("id", "unknown"),
            rtype,
            si,
            output_path,
        )

    # Build prompts + meta for the full pending set; results stream to disk as
    # each completes, so a single slow/stuck generation can no longer block the
    # rest of the batch from being persisted.
    prompts: list[str] = []
    meta: list[tuple[str, str, int, str]] = []
    for entry, rtype, si in pending:
        rid = entry.get("id", "unknown")
        text = entry.get("original_riddle" if rtype == "original" else "altered_riddle", "")
        if not text:
            continue
        prompts.append(template.render(riddle=text, chain_of_thought=args.chain_of_thought))
        meta.append((rid, rtype, si, text))

    if not prompts:
        logger.info("No prompts to run.")
        return

    completed = 0
    total_prompts = len(prompts)

    def handle_result(idx: int, result: LLMResponse | BaseException) -> None:
        nonlocal completed
        rid, rtype, si, text = meta[idx]
        if isinstance(result, BaseException):
            answer, reasoning, raw = "ERROR", str(result), ""
            in_tok = out_tok = None
        else:
            raw = result.text
            in_tok, out_tok = result.input_tokens, result.output_tokens
            if raw:
                answer, reasoning = parse_model_response(raw)
            else:
                answer, reasoning = "ERROR", "Empty response"

        record = make_record(
            rid,
            rtype,
            si,
            text,
            answer,
            reasoning,
            raw,
            model_name,
            args.provider,
            args.temperature,
            args.quantization,
            in_tok,
            out_tok,
            reasoning_plan.enabled,
            reasoning_plan.effort,
        )
        append_jsonl(output_path, record)
        completed += 1
        logger.info(
            "  [%d/%d] %s (%s, s%d) -> %s",
            completed,
            total_prompts,
            rid,
            rtype,
            si,
            answer[:60],
        )

    if batch_size <= 1:
        # Sequential path — keep the per-call delay for rate-limit friendliness.
        for idx, prompt in enumerate(prompts):
            try:
                result: LLMResponse | BaseException = call_llm(
                    prompt,
                    provider=args.provider,
                    model=model_name,
                    temperature=args.temperature,
                    api_key=api_key,
                    max_output_tokens=args.max_output_tokens,
                    reasoning_plan=reasoning_plan,
                )
            except Exception as exc:
                result = exc
            handle_result(idx, result)
            if idx + 1 < total_prompts:
                time.sleep(args.delay)
    else:
        call_llm_batched_streaming(
            prompts,
            provider=args.provider,
            model=model_name,
            temperature=args.temperature,
            api_key=api_key,
            max_output_tokens=args.max_output_tokens,
            max_concurrency=batch_size,
            reasoning_plan=reasoning_plan,
            on_result=handle_result,
        )

    logger.info("Benchmark complete. Results: %s", output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Altered Riddles benchmark.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--provider", choices=provider_names(), default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    parser.add_argument("--output-dir", default=DEFAULT_MODEL_OUTPUTS)
    parser.add_argument("--prompt-template", default="prompts/solve.j2")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument(
        "--only",
        choices=["original", "altered", "both"],
        default="both",
    )
    parser.add_argument("--max-output-tokens", type=int, default=16384)
    parser.add_argument(
        "--num-samples",
        type=int,
        default=1,
        help="Samples per riddle (for temp > 0)",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--one-entry-test",
        action="store_true",
        default=False,
        help=(
            "Run exactly one pending benchmark task, forcing batch size 1 and a "
            "single sample, and write to a dedicated *_one_entry_test.jsonl file."
        ),
    )
    parser.add_argument("--chain-of-thought", action="store_true", default=False)
    parser.add_argument("--quantization", type=str, default=None)
    parser.add_argument(
        "--reasoning",
        action="store_true",
        default=False,
        help="Enable reasoning/thinking mode for the target model.",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=list(EFFORTS),
        default=DEFAULT_EFFORT,
        help="Effort level when --reasoning is set (ignored otherwise).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_benchmark(parse_args())
