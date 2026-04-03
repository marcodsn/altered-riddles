#!/usr/bin/env python3
"""validate.py — Validate generated altered riddles using an LLM.

Reads a JSONL file of generated riddle pairs, sends each one through an LLM
validation prompt, and writes the results (with validation fields attached)
to an output JSONL file. Optionally appends passing entries to the benchmark.

Usage examples:
    python scripts/validate.py --input data/generated/raw_20250101_120000.jsonl
    python scripts/validate.py --provider openai --input data/generated/raw.jsonl --append-to-benchmark
    python -m scripts.validate --input data/generated/raw.jsonl --delay 1.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jinja2
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("validate")

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
MAX_RETRIES = 3
INITIAL_BACKOFF_S = 2.0

LOCAL_BASE_URL = "http://10.8.0.5:8083/v1"
DEFAULT_LOCAL_MODEL = "Mistral-Small-4-119B-2603"

VALIDATION_FIELDS = {
    "answer_valid",
    "is_distinct",
    "has_competing_answers",
    "is_subtle",
    "is_logical",
    "is_clear",
    "competing_answers",
    "overall_valid",
    "reasoning",
}


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------


def _call_gemini(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> str:
    """Call the Gemini API via the google-genai SDK and return raw text."""
    from google import genai
    from google.genai.types import GenerateContentConfig

    client = genai.Client(api_key=api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt_text,
        config=config,
    )
    result = response.text
    assert result is not None, "Gemini returned an empty response"
    return result


def _call_openai(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> str:
    """Call the OpenAI chat completions API and return raw text."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if max_output_tokens is not None:
        kwargs["max_completion_tokens"] = max_output_tokens
    response = client.chat.completions.create(**kwargs)
    result = response.choices[0].message.content
    assert result is not None, "OpenAI returned an empty response"
    return result


def _call_local(
    prompt_text: str,
    model: str,
    temperature: float,
    api_key: str,  # unused but kept for uniform signature
    max_output_tokens: int | None = None,
) -> str:
    """Call a local OpenAI-compatible server (llama.cpp / vLLM) and return raw text."""
    from openai import OpenAI

    client = OpenAI(base_url=LOCAL_BASE_URL, api_key="local")
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt_text}],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if max_output_tokens is not None:
        kwargs["max_completion_tokens"] = max_output_tokens
    response = client.chat.completions.create(**kwargs)
    result = response.choices[0].message.content
    assert result is not None, "Local server returned an empty response"
    return result


def call_llm(
    prompt_text: str,
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> str:
    """Dispatch to the appropriate provider with retries + exponential backoff."""
    if provider == "gemini":
        call_fn = _call_gemini
    elif provider == "local":
        call_fn = _call_local
    else:
        call_fn = _call_openai
    backoff = INITIAL_BACKOFF_S

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return call_fn(prompt_text, model, temperature, api_key, max_output_tokens)
        except Exception as exc:
            logger.warning(
                "API call attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
            )
            if attempt == MAX_RETRIES:
                raise
            logger.info("Retrying in %.1fs …", backoff)
            time.sleep(backoff)
            backoff *= 2

    # Should not be reached, but just in case:
    raise RuntimeError("Exhausted retries")


# ---------------------------------------------------------------------------
# Async / batched helpers  (all providers)
# ---------------------------------------------------------------------------


async def _call_provider_async(
    prompt_text: str,
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> str:
    """Single async LLM call dispatched by provider."""
    if provider == "gemini":
        from google import genai
        from google.genai.types import GenerateContentConfig

        client = genai.Client(api_key=api_key)
        config = GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
            max_output_tokens=max_output_tokens,
        )
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt_text,
            config=config,
        )
        result = response.text
        assert result is not None, "Gemini returned an empty response"
        return result

    else:  # openai or local — both use AsyncOpenAI
        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = {"api_key": api_key}
        if provider == "local":
            kwargs["base_url"] = LOCAL_BASE_URL
            kwargs["api_key"] = "local"
        client = AsyncOpenAI(**kwargs)
        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt_text}],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_output_tokens is not None:
            create_kwargs["max_completion_tokens"] = max_output_tokens
        response = await client.chat.completions.create(**create_kwargs)
        result = response.choices[0].message.content
        assert result is not None, f"{provider} returned an empty response"
        return result


async def _provider_batch_async(
    prompts: list[str],
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    max_concurrency: int,
) -> list[str | BaseException]:
    """Send all prompts concurrently, capped at max_concurrency in-flight requests.

    Returns one result (or exception) per prompt, preserving order.
    Each slot independently retries with exponential backoff so a single
    flaky request never stalls the rest of the batch.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _guarded(idx: int, prompt: str) -> str:
        async with semaphore:
            backoff = INITIAL_BACKOFF_S
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    return await _call_provider_async(
                        prompt,
                        provider=provider,
                        model=model,
                        temperature=temperature,
                        api_key=api_key,
                        max_output_tokens=max_output_tokens,
                    )
                except Exception as exc:
                    logger.warning(
                        "Prompt %d async attempt %d/%d failed: %s",
                        idx,
                        attempt,
                        MAX_RETRIES,
                        exc,
                    )
                    if attempt == MAX_RETRIES:
                        raise
                    await asyncio.sleep(backoff)
                    backoff *= 2
        raise RuntimeError("Exhausted retries")

    tasks = [asyncio.create_task(_guarded(i, p)) for i, p in enumerate(prompts)]
    # return_exceptions=True: one failure never cancels the rest of the batch
    return await asyncio.gather(*tasks, return_exceptions=True)


def call_llm_batched(
    prompts: list[str],
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    max_concurrency: int,
) -> list[str | BaseException]:
    """Synchronous entry-point for batched inference on any provider.

    Runs all prompts through a single asyncio event loop, returning results
    in the same order.  Exceptions are returned as values so the caller can
    handle them per-prompt without aborting the batch.
    """
    return asyncio.run(
        _provider_batch_async(
            prompts,
            provider=provider,
            model=model,
            temperature=temperature,
            api_key=api_key,
            max_output_tokens=max_output_tokens,
            max_concurrency=max_concurrency,
        )
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_jsonl(path: str) -> list[dict[str, Any]]:
    """Load a JSONL file and return a list of dicts."""
    entries: list[dict[str, Any]] = []
    filepath = Path(path)
    if not filepath.exists():
        logger.error("Input file not found: %s", path)
        raise SystemExit(1)
    with open(filepath, encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSON on line %d: %s", line_num, exc)
    return entries


def load_template(template_path: str) -> jinja2.Template:
    """Load and compile a Jinja2 template from *template_path*."""
    tpl_path = Path(template_path)
    if not tpl_path.exists():
        logger.error("Template file not found: %s", template_path)
        raise SystemExit(1)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tpl_path.parent)),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    return env.get_template(tpl_path.name)


def parse_validation_response(raw_text: str) -> dict[str, Any]:
    """Parse the LLM validation response into a dict.

    The response should be a single JSON object. We handle minor quirks like
    wrapping markdown fences.
    """
    text = raw_text.strip()
    # Strip optional markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed)}")
    return parsed


def write_jsonl_entry(fh, entry: dict[str, Any]) -> None:
    """Append a single JSON object as one line to an open file handle."""
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_max_benchmark_id(benchmark_path: str) -> int:
    """Return the maximum numeric ID (from ``alt_NNN``) in the benchmark file.

    Returns 0 if the file does not exist or is empty.
    """
    filepath = Path(benchmark_path)
    if not filepath.exists():
        return 0

    max_id = 0
    with open(filepath, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry_id = entry.get("id", "")
            match = re.match(r"alt_(\d+)", entry_id)
            if match:
                max_id = max(max_id, int(match.group(1)))
    return max_id


def to_benchmark_format(entry: dict[str, Any], new_id: str) -> dict[str, Any]:
    """Convert a validated generation entry to the benchmark JSONL format."""
    # Collect competing answers from validation, filtering out any that match
    # the original answer (those would indicate a flawed alteration).
    original_answer_lower = entry.get("original_answer", "").strip().lower()
    competing = [
        a
        for a in entry.get("competing_answers", [])
        if a.strip().lower() != original_answer_lower
    ]
    return {
        "id": new_id,
        "original_riddle": entry.get("original_riddle", ""),
        "original_answer": entry.get("original_answer", ""),
        "original_accepted_answers": [entry.get("original_answer", "")],
        "original_reasoning": entry.get("original_reasoning", ""),
        "altered_riddle": entry.get("altered_riddle", ""),
        "altered_answer": entry.get("altered_answer", ""),
        "altered_accepted_answers": [entry.get("altered_answer", "")],
        "altered_competing_answers": competing,
        "altered_reasoning": entry.get("altered_reasoning", ""),
        "source": entry.get("source", ""),
        "type": entry.get("type", "constraint_addition"),
    }


# ---------------------------------------------------------------------------
# Main validation loop
# ---------------------------------------------------------------------------


def validate(args: argparse.Namespace) -> None:
    """Run the validation pipeline according to parsed CLI *args*."""
    load_dotenv()

    # Resolve provider + API key
    provider = args.provider
    if provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "")
        model = args.model or DEFAULT_GEMINI_MODEL
        if not api_key:
            logger.error(
                "Missing GEMINI_API_KEY environment variable. Set it in .env or your shell."
            )
            raise SystemExit(1)
    elif provider == "local":
        api_key = "local"  # not used, but kept for uniform signature
        model = args.model or DEFAULT_LOCAL_MODEL
    else:  # openai
        api_key = os.environ.get("OPENAI_API_KEY", "")
        model = args.model or DEFAULT_OPENAI_MODEL
        if not api_key:
            logger.error(
                "Missing OPENAI_API_KEY environment variable. Set it in .env or your shell."
            )
            raise SystemExit(1)

    # Resolve output path with timestamp
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output.replace("{timestamp}", ts))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load entries + template
    entries = load_jsonl(args.input)
    template = load_template(args.prompt_template)

    batch_size = args.batch_size
    use_batching = batch_size > 1
    max_output_tokens: int | None = args.max_output_tokens

    logger.info("Provider : %s", provider)
    logger.info("Model    : %s", model)
    logger.info("Input    : %s (%d entries)", args.input, len(entries))
    logger.info("Output   : %s", output_path)
    logger.info("Temp     : %.2f", args.temperature)
    logger.info("Delay    : %.2fs between calls", args.delay)
    logger.info(
        "Batching : %s (batch_size=%d)",
        "enabled" if use_batching else "disabled (sequential)",
        batch_size,
    )
    if max_output_tokens is not None:
        logger.info("Max tokens: %d", max_output_tokens)

    total_validated = 0
    total_passed = 0
    total_failed = 0

    validated_entries: list[dict[str, Any]] = []

    # Build (entry, prompt_text) pairs upfront so we can slice into batches.
    entry_prompts: list[tuple[dict[str, Any], str]] = []
    for entry in entries:
        try:
            prompt_text = template.render(
                original_riddle=entry.get("original_riddle", ""),
                original_answer=entry.get("original_answer", ""),
                altered_riddle=entry.get("altered_riddle", ""),
                altered_answer=entry.get("altered_answer", ""),
                altered_reasoning=entry.get("altered_reasoning", ""),
            )
            entry_prompts.append((entry, prompt_text))
        except jinja2.TemplateError as exc:
            logger.error(
                "Template render error for entry %s: %s — skipping.",
                entry.get("id"),
                exc,
            )

    with open(output_path, "a", encoding="utf-8") as out_fh:
        if use_batching:
            # ----------------------------------------------------------
            # BATCHED PATH  (all providers, async concurrency)
            # ----------------------------------------------------------
            for chunk_start in range(0, len(entry_prompts), batch_size):
                chunk = entry_prompts[chunk_start : chunk_start + batch_size]
                prompts_only = [p for _, p in chunk]

                logger.info(
                    "Dispatching batch %d–%d / %d …",
                    chunk_start + 1,
                    chunk_start + len(chunk),
                    len(entry_prompts),
                )

                raw_results: list[str | BaseException] = call_llm_batched(
                    prompts_only,
                    provider=provider,
                    model=model,
                    temperature=args.temperature,
                    api_key=api_key,
                    max_output_tokens=max_output_tokens,
                    max_concurrency=batch_size,
                )

                for rel_idx, ((entry, _), raw) in enumerate(
                    zip(chunk, raw_results), start=chunk_start + 1
                ):
                    logger.info(
                        "  [%d/%d] id=%s",
                        rel_idx,
                        len(entry_prompts),
                        entry.get("id", "?"),
                    )

                    if isinstance(raw, BaseException):
                        logger.error(
                            "  Validation call failed for entry %s after retries: %s — skipping.",
                            entry.get("id"),
                            raw,
                        )
                        continue

                    # Parse the validation response
                    try:
                        validation = parse_validation_response(raw)
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.error(
                            "  Unparseable validation response for entry %s: %s — skipping.",
                            entry.get("id"),
                            exc,
                        )
                        logger.debug("  Raw response:\n%s", raw[:500])
                        continue

                    # Merge validation fields into the entry
                    for field in VALIDATION_FIELDS:
                        if field in validation:
                            entry[field] = validation[field]

                    # Determine pass/fail
                    passed = bool(validation.get("overall_valid", False))
                    if passed:
                        total_passed += 1
                    else:
                        total_failed += 1
                    total_validated += 1

                    write_jsonl_entry(out_fh, entry)
                    validated_entries.append(entry)

                    logger.info(
                        "    → %s (answer_valid=%s, is_distinct=%s, overall_valid=%s)",
                        "PASS" if passed else "FAIL",
                        validation.get("answer_valid"),
                        validation.get("is_distinct"),
                        validation.get("overall_valid"),
                    )

                out_fh.flush()

        else:
            # ----------------------------------------------------------
            # SEQUENTIAL PATH  (batch_size == 1)
            # ----------------------------------------------------------
            for idx, (entry, prompt_text) in enumerate(entry_prompts, start=1):
                logger.info(
                    "Validating %d/%d — id=%s",
                    idx,
                    len(entry_prompts),
                    entry.get("id", "?"),
                )

                # Call the LLM
                try:
                    raw = call_llm(
                        prompt_text,
                        provider=provider,
                        model=model,
                        temperature=args.temperature,
                        api_key=api_key,
                        max_output_tokens=max_output_tokens,
                    )
                except Exception as exc:
                    logger.error(
                        "Validation call failed for entry %s after retries: %s — skipping.",
                        entry.get("id"),
                        exc,
                    )
                    continue

                # Parse the validation response
                try:
                    validation = parse_validation_response(raw)
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.error(
                        "Unparseable validation response for entry %s: %s — skipping.",
                        entry.get("id"),
                        exc,
                    )
                    logger.debug("Raw response:\n%s", raw[:500])
                    continue

                # Merge validation fields into the entry
                for field in VALIDATION_FIELDS:
                    if field in validation:
                        entry[field] = validation[field]

                # Determine pass/fail
                passed = bool(validation.get("overall_valid", False))
                if passed:
                    total_passed += 1
                else:
                    total_failed += 1
                total_validated += 1

                write_jsonl_entry(out_fh, entry)
                validated_entries.append(entry)
                out_fh.flush()

                logger.info(
                    "  → %s (answer_valid=%s, is_distinct=%s, overall_valid=%s)",
                    "PASS" if passed else "FAIL",
                    validation.get("answer_valid"),
                    validation.get("is_distinct"),
                    validation.get("overall_valid"),
                )

                # Rate-limit delay between calls (skip after the last one)
                if idx < len(entry_prompts) and args.delay > 0:
                    time.sleep(args.delay)

    # ------------------------------------------------------------------
    # Optionally append valid entries to the benchmark file
    # ------------------------------------------------------------------
    if args.append_to_benchmark:
        benchmark_path = "data/benchmark.jsonl"
        valid_entries = [e for e in validated_entries if e.get("overall_valid")]

        if not valid_entries:
            logger.info("No valid entries to append to benchmark.")
        else:
            current_max_id = get_max_benchmark_id(benchmark_path)
            Path(benchmark_path).parent.mkdir(parents=True, exist_ok=True)

            with open(benchmark_path, "a", encoding="utf-8") as bench_fh:
                for i, entry in enumerate(valid_entries, start=1):
                    new_id = f"alt_{current_max_id + i:03d}"
                    bench_entry = to_benchmark_format(entry, new_id)
                    write_jsonl_entry(bench_fh, bench_entry)

            logger.info(
                "Appended %d valid entries to %s (IDs alt_%03d–alt_%03d)",
                len(valid_entries),
                benchmark_path,
                current_max_id + 1,
                current_max_id + len(valid_entries),
            )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("=" * 60)
    logger.info(
        "Done. Validated %d entries: %d passed, %d failed.",
        total_validated,
        total_passed,
        total_failed,
    )
    logger.info("Output written to %s", output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate generated altered riddles using an LLM.",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "openai", "local"],
        default="gemini",
        help="LLM provider to use (default: gemini)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: gemini-2.0-flash / gpt-4o-mini)",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input JSONL path — the generated riddles file",
    )
    parser.add_argument(
        "--output",
        default="data/generated/validated_{timestamp}.jsonl",
        help="Output JSONL path. {timestamp} is replaced at runtime (default: data/generated/validated_{timestamp}.jsonl)",
    )
    parser.add_argument(
        "--prompt-template",
        default="prompts/validation.j2",
        help="Path to Jinja2 validation template (default: prompts/validation.j2)",
    )
    parser.add_argument(
        "--append-to-benchmark",
        action="store_true",
        default=False,
        help="If set, automatically append valid entries to data/benchmark.jsonl",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0.0)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between API calls for rate limiting (default: 0.5)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help=(
            "Max concurrent async requests dispatched per batch (all providers). "
            "Set to 1 to disable batching and use the sequential path. "
            "(default: 1)"
        ),
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Max output tokens for the LLM. If not specified, no limit is set.",
    )
    return parser


if __name__ == "__main__":
    validate(build_parser().parse_args())
