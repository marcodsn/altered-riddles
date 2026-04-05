#!/usr/bin/env python3
"""
benchmark.py — Run the Altered Riddles benchmark against a language model.

Tests a model on all riddles (both original and altered versions) and writes
structured JSONL output for later evaluation.

Usage examples:
    # Run with Gemini (default)
    python -m scripts.benchmark

    # Run with OpenAI
    python -m scripts.benchmark --provider openai --model gpt-5.4 --max-output-tokens 8192

    # Only test altered riddles
    python -m scripts.benchmark --only altered

    # Multiple samples at temperature > 0
    python -m scripts.benchmark --temperature 0.7 --num-samples 5

    # Batched async calls
    python -m scripts.benchmark --provider openai --batch-size 20

    # Custom benchmark file and output directory
    python -m scripts.benchmark --benchmark data/benchmark.jsonl --output-dir data/model_outputs
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_BENCHMARK,
    DEFAULT_MODEL_OUTPUTS,
    DEFAULT_RESULTS,  # noqa: F401 — re-exported for convenience
    get_benchmark_version,
    provider_names,
    resolve_provider,
)
from scripts.core.io_utils import (
    append_jsonl,
    load_jsonl,
    load_template,
    sanitize_model_name,
    strip_markdown_fences,
)
from scripts.core.llm_client import (  # noqa: F401 — LLMResponse re-exported
    LLMResponse,
    call_llm,
    call_llm_batched,
)

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
# Response parsing
# ---------------------------------------------------------------------------


def parse_model_response(raw_text: str) -> tuple[str, str]:
    """
    Parse the model's JSON response and return (answer, reasoning).

    Handles both clean JSON and JSON embedded in markdown code fences.
    On parse failure, returns (raw_text[:500], "") so we can inspect it later.
    """
    text = strip_markdown_fences(raw_text)

    try:
        data = json.loads(text)
        answer = str(data.get("answer", "")).strip()
        reasoning = str(data.get("reasoning", "")).strip()
        return answer, reasoning
    except json.JSONDecodeError:
        logger.warning("Failed to parse model response as JSON: %s", text[:200])
        return text[:500], ""


# ---------------------------------------------------------------------------
# Benchmark logic
# ---------------------------------------------------------------------------


def build_tasks(
    entries: list[dict],
    only: str,
    num_samples: int,
) -> list[tuple[dict, str, int]]:
    """
    Build the list of (entry, riddle_type, sample_index) tasks to run.

    Each benchmark entry can produce up to two riddle types (original and
    altered), each with up to num_samples samples.

    Note: original riddles are deduplicated by their text content before
    building tasks, because the same source riddle often has multiple altered
    variants in the benchmark. Testing the original riddle once per unique
    text is sufficient.

    Parameters
    ----------
    entries : list[dict]
        Benchmark entries loaded from JSONL.
    only : str
        "original", "altered", or "both".
    num_samples : int
        Number of samples per (entry, riddle_type) pair.

    Returns
    -------
    list of (entry, riddle_type, sample_index) tuples.
    """
    tasks: list[tuple[dict, str, int]] = []
    seen_original_riddles: set[str] = set()
    for entry in entries:
        types: list[str] = []
        if only in ("both", "original"):
            orig_text = entry.get("original_riddle", "")
            if orig_text and orig_text not in seen_original_riddles:
                seen_original_riddles.add(orig_text)
                types.append("original")
        if only in ("both", "altered"):
            types.append("altered")
        for rtype in types:
            for si in range(1, num_samples + 1):
                tasks.append((entry, rtype, si))
    return tasks


def already_answered_keys(output_path: Path) -> set[tuple[str, str, int]]:
    """
    Load existing output file and return a set of (riddle_id, riddle_type, sample_index)
    keys that have already been answered (for resume support).
    """
    keys: set[tuple[str, str, int]] = set()
    if not output_path.exists():
        return keys
    for record in load_jsonl(output_path):
        rid = record.get("riddle_id", "")
        rtype = record.get("riddle_type", "")
        si = record.get("sample_index", 1)
        if rid and rtype:
            keys.add((rid, rtype, int(si)))
    return keys


def _make_record(
    riddle_id: str,
    riddle_type: str,
    sample_index: int,
    riddle_text: str,
    answer: str,
    reasoning: str,
    raw_response: str,
    model_name: str,
    temperature: float,
    input_tokens: int | None,
    output_tokens: int | None,
    provider: str,
    quantization: str | None = None,
) -> dict:
    """Build an output record dict."""
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
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "temperature": temperature,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def run_benchmark(args: argparse.Namespace) -> None:  # noqa: C901
    """Main benchmark loop."""
    # --- Resolve provider, model, and API key ------------------------------
    model_name, api_key = resolve_provider(args.provider, args.model)

    # Determine the model name to use when saving results
    save_model_name = model_name
    if args.reasoning:
        save_model_name += ":reasoning"

    # --- Resolve num_samples -----------------------------------------------
    num_samples: int = args.num_samples
    if num_samples > 1 and args.temperature == 0.0:
        logger.warning(
            "Multiple samples at temperature 0 are redundant — forcing num_samples=1."
        )
        num_samples = 1

    max_output_tokens: int | None = args.max_output_tokens
    batch_size: int = args.batch_size

    # --- Load benchmark data -----------------------------------------------
    benchmark_path = Path(args.benchmark)
    if not benchmark_path.exists():
        logger.error("Benchmark file not found: %s", benchmark_path)
        sys.exit(1)

    entries = load_jsonl(benchmark_path)
    logger.info("Loaded %d benchmark entries from %s", len(entries), benchmark_path)

    # --- Load Jinja2 template ----------------------------------------------
    template = load_template(args.prompt_template)

    # --- Prepare output path (version-aware) -------------------------------
    version = get_benchmark_version()
    output_dir = Path(args.output_dir) / version
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_model_name(model_name).lower()
    cot_tag = "_cot" if args.chain_of_thought else ""
    if args.temperature > 0:
        output_path = output_dir / f"{safe_name}{cot_tag}_temp{args.temperature}.jsonl"
    else:
        output_path = output_dir / f"{safe_name}{cot_tag}.jsonl"

    # --- Resume support: skip already-answered riddles ---------------------
    done = already_answered_keys(output_path)
    if done:
        logger.info(
            "Resuming — %d record(s) already answered in %s", len(done), output_path
        )

    # --- Build task list ---------------------------------------------------
    tasks = build_tasks(entries, args.only, num_samples)
    pending = [
        (e, rt, si) for e, rt, si in tasks if (e.get("id", ""), rt, si) not in done
    ]

    logger.info(
        "Tasks: %d total, %d pending (%s riddles, model=%s, temp=%.2f, samples=%d, batch=%d)",
        len(tasks),
        len(pending),
        args.only,
        model_name,
        args.temperature,
        num_samples,
        batch_size,
    )

    if not pending:
        logger.info("Nothing to do — all riddles already answered.")
        return

    # -----------------------------------------------------------------------
    # Helper to extract riddle text from an entry
    # -----------------------------------------------------------------------
    def _riddle_text(entry: dict, riddle_type: str) -> str:
        if riddle_type == "original":
            return entry.get("original_riddle", "")
        return entry.get("altered_riddle", "")

    # -----------------------------------------------------------------------
    # Sequential path  (batch_size == 1)
    # -----------------------------------------------------------------------
    if batch_size <= 1:
        for idx, (entry, riddle_type, sample_index) in enumerate(pending, start=1):
            riddle_id = entry.get("id", "unknown")
            riddle_text = _riddle_text(entry, riddle_type)

            if not riddle_text:
                logger.warning(
                    "Skipping %s (%s) — no riddle text found.", riddle_id, riddle_type
                )
                continue

            logger.info(
                "[%d/%d] Testing riddle %s (%s, sample %d)…",
                idx,
                len(pending),
                riddle_id,
                riddle_type,
                sample_index,
            )

            # Render prompt
            prompt_text = template.render(
                riddle=riddle_text, chain_of_thought=args.chain_of_thought
            )

            # Call the LLM
            raw_response = ""
            input_tokens: int | None = None
            output_tokens: int | None = None
            try:
                llm_resp = call_llm(
                    prompt_text,
                    provider=args.provider,
                    model=model_name,
                    temperature=args.temperature,
                    api_key=api_key,
                    max_output_tokens=max_output_tokens,
                )
                raw_response = llm_resp.text
                input_tokens = llm_resp.input_tokens
                output_tokens = llm_resp.output_tokens
            except Exception as exc:
                logger.error(
                    "Failed to get response for %s (%s, sample %d) after retries: %s",
                    riddle_id,
                    riddle_type,
                    sample_index,
                    exc,
                )

            # Parse response
            if raw_response:
                answer, reasoning = parse_model_response(raw_response)
            else:
                answer, reasoning = "ERROR", "API call failed after retries."

            # Build and write output record
            record = _make_record(
                riddle_id=riddle_id,
                riddle_type=riddle_type,
                sample_index=sample_index,
                riddle_text=riddle_text,
                answer=answer,
                reasoning=reasoning,
                raw_response=raw_response,
                model_name=save_model_name,
                temperature=args.temperature,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                provider=args.provider,
                quantization=args.quantization,
            )
            append_jsonl(output_path, record)

            logger.info(
                "[%d/%d] Testing riddle %s (%s, sample %d)… done  →  %s",
                idx,
                len(pending),
                riddle_id,
                riddle_type,
                sample_index,
                answer[:80],
            )

            # Delay between API calls to respect rate limits
            if idx < len(pending):
                time.sleep(args.delay)

    # -----------------------------------------------------------------------
    # Batched async path  (batch_size > 1)
    # -----------------------------------------------------------------------
    else:
        # Slice pending into chunks of batch_size
        total = len(pending)
        written = 0

        for chunk_start in range(0, total, batch_size):
            chunk = pending[chunk_start : chunk_start + batch_size]
            chunk_idx_start = chunk_start + 1
            chunk_idx_end = chunk_start + len(chunk)

            logger.info(
                "Dispatching batch [%d–%d] of %d …",
                chunk_idx_start,
                chunk_idx_end,
                total,
            )

            # Render all prompts for this chunk
            prompts: list[str] = []
            chunk_meta: list[
                tuple[str, str, int, str]
            ] = []  # (riddle_id, riddle_type, sample_index, riddle_text)
            for entry, riddle_type, sample_index in chunk:
                riddle_id = entry.get("id", "unknown")
                riddle_text = _riddle_text(entry, riddle_type)
                if not riddle_text:
                    logger.warning(
                        "Skipping %s (%s) — no riddle text found.",
                        riddle_id,
                        riddle_type,
                    )
                    continue
                prompt_text = template.render(
                    riddle=riddle_text, chain_of_thought=args.chain_of_thought
                )
                prompts.append(prompt_text)
                chunk_meta.append((riddle_id, riddle_type, sample_index, riddle_text))

            if not prompts:
                continue

            # Dispatch batch
            results = call_llm_batched(
                prompts,
                provider=args.provider,
                model=model_name,
                temperature=args.temperature,
                api_key=api_key,
                max_output_tokens=max_output_tokens,
                max_concurrency=batch_size,
            )

            # Process results
            for (riddle_id, riddle_type, sample_index, riddle_text), result in zip(
                chunk_meta, results
            ):
                written += 1
                raw_response = ""
                input_tokens_val: int | None = None
                output_tokens_val: int | None = None

                if isinstance(result, BaseException):
                    logger.error(
                        "Failed to get response for %s (%s, sample %d): %s",
                        riddle_id,
                        riddle_type,
                        sample_index,
                        result,
                    )
                    answer, reasoning = "ERROR", f"API call failed: {result}"
                else:
                    raw_response = result.text
                    input_tokens_val = result.input_tokens
                    output_tokens_val = result.output_tokens
                    answer, reasoning = parse_model_response(raw_response)

                record = _make_record(
                    riddle_id=riddle_id,
                    riddle_type=riddle_type,
                    sample_index=sample_index,
                    riddle_text=riddle_text,
                    answer=answer,
                    reasoning=reasoning,
                    raw_response=raw_response,
                    model_name=save_model_name,
                    temperature=args.temperature,
                    input_tokens=input_tokens_val,
                    output_tokens=output_tokens_val,
                    provider=args.provider,
                    quantization=args.quantization,
                )
                append_jsonl(output_path, record)

                logger.info(
                    "[%d/%d] %s (%s, sample %d)  →  %s",
                    written,
                    total,
                    riddle_id,
                    riddle_type,
                    sample_index,
                    answer[:80],
                )

            # Delay between batches to respect rate limits
            if chunk_idx_end < total:
                time.sleep(args.delay)

    logger.info("Benchmark complete. Results written to %s", output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Altered Riddles benchmark against a language model.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--provider",
        choices=provider_names(),
        default="gemini",
        help="LLM provider to use.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name to use. Defaults to the provider's default model (see config.py).",
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default=DEFAULT_BENCHMARK,
        help="Path to the benchmark JSONL file.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=DEFAULT_MODEL_OUTPUTS,
        help="Directory for model output JSONL files.",
    )
    parser.add_argument(
        "--prompt-template",
        type=str,
        default="prompts/solve.j2",
        help="Path to the Jinja2 solve prompt template.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (0.0 = deterministic).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between API calls (or between batches).",
    )
    parser.add_argument(
        "--only",
        choices=["original", "altered", "both"],
        default="both",
        help="Which riddle types to test.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Maximum output tokens for the LLM (None = provider default).",
    )
    parser.add_argument(
        "--num-samples",
        type=int,
        default=1,
        help="Number of samples per riddle (useful at temperature > 0).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Max concurrent async requests per batch (1 = sequential).",
    )
    parser.add_argument(
        "--chain-of-thought",
        action="store_true",
        default=False,
        help="Include reasoning in the prompt (adds a 'reasoning' field before 'answer' in the model's response).",
    )
    parser.add_argument(
        "--reasoning",
        action="store_true",
        default=False,
        help="Append ':reasoning' to the model name when saving results.",
    )
    parser.add_argument(
        "--quantization",
        type=str,
        default=None,
        help="Quantization type used by the model.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Load .env from project root (one level up from scripts/)
    dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path)

    args = parse_args()
    run_benchmark(args)
