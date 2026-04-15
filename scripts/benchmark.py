#!/usr/bin/env python3
"""benchmark.py — Run the Altered Riddles benchmark against a model.

Usage:
    python -m scripts.benchmark --provider gemini
    python -m scripts.benchmark --provider openai --model gpt-5.4
    python -m scripts.benchmark --temperature 0.7 --num-samples 5
    python -m scripts.benchmark --only altered --batch-size 20
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
from scripts.core.llm_client import LLMResponse, call_llm, call_llm_batched

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

    num_samples = args.num_samples
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
    if args.temperature > 0:
        output_path = output_dir / f"{safe_name}_temp{args.temperature}.jsonl"
    else:
        output_path = output_dir / f"{safe_name}.jsonl"

    # Resume support
    done = already_answered(output_path)
    if done:
        logger.info("Resuming: %d records already in %s", len(done), output_path)

    tasks = build_tasks(entries, args.only, num_samples)
    pending = [(e, rt, si) for e, rt, si in tasks if (e.get("id", ""), rt, si) not in done]

    logger.info(
        "Tasks: %d total, %d pending (model=%s, temp=%.2f, samples=%d)",
        len(tasks),
        len(pending),
        model_name,
        args.temperature,
        num_samples,
    )

    if not pending:
        logger.info("All riddles already answered.")
        return

    batch_size = args.batch_size
    total = len(pending)

    for chunk_start in range(0, total, batch_size):
        chunk = pending[chunk_start : chunk_start + batch_size]
        logger.info(
            "Batch [%d-%d] / %d",
            chunk_start + 1,
            chunk_start + len(chunk),
            total,
        )

        prompts: list[str] = []
        meta: list[tuple[str, str, int, str]] = []

        for entry, rtype, si in chunk:
            rid = entry.get("id", "unknown")
            text = entry.get("original_riddle" if rtype == "original" else "altered_riddle", "")
            if not text:
                continue
            prompts.append(template.render(riddle=text, chain_of_thought=args.chain_of_thought))
            meta.append((rid, rtype, si, text))

        if not prompts:
            continue

        # Sequential or batched execution
        if batch_size <= 1:
            results: list[LLMResponse | BaseException] = []
            for prompt in prompts:
                try:
                    results.append(
                        call_llm(
                            prompt,
                            provider=args.provider,
                            model=model_name,
                            temperature=args.temperature,
                            api_key=api_key,
                            max_output_tokens=args.max_output_tokens,
                        )
                    )
                except Exception as exc:
                    results.append(exc)
                time.sleep(args.delay)
        else:
            results = call_llm_batched(
                prompts,
                provider=args.provider,
                model=model_name,
                temperature=args.temperature,
                api_key=api_key,
                max_output_tokens=args.max_output_tokens,
                max_concurrency=batch_size,
            )

        # Process results
        for (rid, rtype, si, text), result in zip(meta, results):
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
            )
            append_jsonl(output_path, record)
            logger.info("  %s (%s, s%d) -> %s", rid, rtype, si, answer[:60])

        # Delay between batches
        if chunk_start + len(chunk) < total:
            time.sleep(args.delay)

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
    parser.add_argument("--chain-of-thought", action="store_true", default=False)
    parser.add_argument("--quantization", type=str, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    run_benchmark(parse_args())
