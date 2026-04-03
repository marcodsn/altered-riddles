#!/usr/bin/env python3
"""
benchmark.py — Run the Altered Riddles benchmark against a language model.

Tests a model on all riddles (both original and altered versions) and writes
structured JSONL output for later evaluation.

Usage examples:
    # Run with Gemini (default)
    python scripts/benchmark.py

    # Run with OpenAI
    python scripts/benchmark.py --provider openai --model gpt-4o-mini --max-output-tokens 8192

    # Only test altered riddles
    python scripts/benchmark.py --only altered

    # Multiple samples at temperature > 0
    python scripts/benchmark.py --temperature 0.7 --num-samples 5

    # Batched async calls
    python scripts/benchmark.py --provider openai --batch-size 20

    # Custom benchmark file and output directory
    python scripts/benchmark.py --benchmark data/benchmark.jsonl --output-dir data/model_outputs
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

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
# Constants
# ---------------------------------------------------------------------------
DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
MAX_RETRIES = 3
INITIAL_BACKOFF = 2.0  # seconds
LOCAL_BASE_URL = "http://10.8.0.5:8083/v1"
DEFAULT_LOCAL_MODEL = "Mistral-Small-4-119B-2603"


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Carries the raw text and optional token-usage counters from an LLM call."""

    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


# ---------------------------------------------------------------------------
# Sync API helpers  (used when batch_size == 1)
# ---------------------------------------------------------------------------


def call_gemini(
    prompt_text: str,
    model_name: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    """Call the Google Gemini API and return an LLMResponse."""
    from google import genai  # type: ignore[import-untyped]
    from google.genai.types import GenerateContentConfig

    client = genai.Client(api_key=api_key)
    config = GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        max_output_tokens=max_output_tokens,
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt_text,
        config=config,
    )
    assert response.text is not None, "Gemini returned an empty response"

    input_tokens: int | None = None
    output_tokens: int | None = None
    if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
        output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)

    return LLMResponse(
        text=response.text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def call_openai(
    prompt_text: str,
    model_name: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    """Call the OpenAI API and return an LLMResponse."""
    from openai import OpenAI  # type: ignore[import-untyped]

    client = OpenAI(api_key=api_key)
    kwargs: dict[str, Any] = dict(
        model=model_name,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        kwargs["max_completion_tokens"] = max_output_tokens

    response = client.chat.completions.create(**kwargs)
    result = response.choices[0].message.content
    assert result is not None, "OpenAI returned an empty response"

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def call_local(
    prompt_text: str,
    model_name: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    """Call a local OpenAI-compatible server (llama.cpp / vLLM) and return an LLMResponse."""
    from openai import OpenAI  # type: ignore[import-untyped]

    client = OpenAI(base_url=LOCAL_BASE_URL, api_key="local")
    kwargs: dict[str, Any] = dict(
        model=model_name,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    if max_output_tokens is not None:
        kwargs["max_completion_tokens"] = max_output_tokens

    response = client.chat.completions.create(**kwargs)
    result = response.choices[0].message.content
    assert result is not None, "Local server returned an empty response"

    input_tokens: int | None = None
    output_tokens: int | None = None
    if response.usage is not None:
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

    return LLMResponse(
        text=result,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def call_llm(
    provider: str,
    prompt_text: str,
    model_name: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    """Dispatch to the correct provider with retry + exponential backoff."""
    if provider == "gemini":
        call_fn = call_gemini
    elif provider == "local":
        call_fn = call_local
    else:
        call_fn = call_openai
    backoff = INITIAL_BACKOFF

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return call_fn(
                prompt_text, model_name, temperature, api_key, max_output_tokens
            )
        except Exception as exc:
            logger.warning(
                "API call failed (attempt %d/%d): %s", attempt, MAX_RETRIES, exc
            )
            if attempt == MAX_RETRIES:
                raise
            logger.info("Retrying in %.1f s …", backoff)
            time.sleep(backoff)
            backoff *= 2

    # Should never reach here, but satisfy type checkers.
    raise RuntimeError("Exhausted retries")


# ---------------------------------------------------------------------------
# Async / batched helpers
# ---------------------------------------------------------------------------


async def _call_provider_async(
    prompt_text: str,
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
) -> LLMResponse:
    """Single async LLM call dispatched by provider, returning LLMResponse."""
    if provider == "gemini":
        from google import genai  # type: ignore[import-untyped]
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

        input_tokens: int | None = None
        output_tokens: int | None = None
        if hasattr(response, "usage_metadata") and response.usage_metadata is not None:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
            output_tokens = getattr(
                response.usage_metadata, "candidates_token_count", None
            )

        return LLMResponse(
            text=result, input_tokens=input_tokens, output_tokens=output_tokens
        )

    else:  # openai or local — both use AsyncOpenAI
        from openai import AsyncOpenAI  # type: ignore[import-untyped]

        kw: dict[str, Any] = {"api_key": api_key}
        if provider == "local":
            kw["base_url"] = LOCAL_BASE_URL
            kw["api_key"] = "local"
        client_oai = AsyncOpenAI(**kw)

        call_kwargs: dict[str, Any] = dict(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        if max_output_tokens is not None:
            call_kwargs["max_completion_tokens"] = max_output_tokens

        response_oai = await client_oai.chat.completions.create(**call_kwargs)
        result_oai = response_oai.choices[0].message.content
        assert result_oai is not None, f"{provider} returned an empty response"

        input_tokens_oai: int | None = None
        output_tokens_oai: int | None = None
        if response_oai.usage is not None:
            input_tokens_oai = response_oai.usage.prompt_tokens
            output_tokens_oai = response_oai.usage.completion_tokens

        return LLMResponse(
            text=result_oai,
            input_tokens=input_tokens_oai,
            output_tokens=output_tokens_oai,
        )


async def _provider_batch_async(
    prompts: list[str],
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    max_concurrency: int = 10,
) -> list[LLMResponse | BaseException]:
    """Send all prompts concurrently, capped at max_concurrency in-flight requests.

    Returns one LLMResponse (or exception) per prompt, preserving order.
    Each slot independently retries with exponential backoff so a single
    flaky request never stalls the rest of the batch.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _guarded(idx: int, prompt: str) -> LLMResponse:
        async with semaphore:
            backoff = INITIAL_BACKOFF
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
    return await asyncio.gather(*tasks, return_exceptions=True)  # type: ignore[return-value]


def call_llm_batched(
    prompts: list[str],
    *,
    provider: str,
    model: str,
    temperature: float,
    api_key: str,
    max_output_tokens: int | None = None,
    max_concurrency: int = 10,
) -> list[LLMResponse | BaseException]:
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
# I/O helpers
# ---------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file and return a list of dicts."""
    entries: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping malformed line %d in %s: %s", lineno, path, exc
                )
    return entries


def append_jsonl(path: Path, record: dict) -> None:
    """Append a single JSON record to a JSONL file."""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def sanitize_model_name(name: str) -> str:
    """Make a model name safe for use as a filename component."""
    return re.sub(r"[/\\]", "_", name)


def parse_model_response(raw_text: str) -> tuple[str, str]:
    """
    Parse the model's JSON response and return (answer, reasoning).

    Handles both clean JSON and JSON embedded in markdown code fences.
    On parse failure, returns (raw_text[:500], "") so we can inspect it later.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        # Remove closing fence
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()

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
    for entry in entries:
        types: list[str] = []
        if only in ("both", "original"):
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
        "model": model_name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "temperature": temperature,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def run_benchmark(args: argparse.Namespace) -> None:  # noqa: C901
    """Main benchmark loop."""
    # --- Resolve API key ---------------------------------------------------
    if args.provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            logger.error("GEMINI_API_KEY not set. Add it to your .env file.")
            sys.exit(1)
    elif args.provider == "local":
        api_key = "local"  # not needed but kept for uniform call signature
    else:  # openai
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            logger.error("OPENAI_API_KEY not set. Add it to your .env file.")
            sys.exit(1)

    # --- Resolve model name ------------------------------------------------
    model_name: str = args.model
    if model_name is None:
        if args.provider == "gemini":
            model_name = DEFAULT_GEMINI_MODEL
        elif args.provider == "local":
            model_name = DEFAULT_LOCAL_MODEL
        else:
            model_name = DEFAULT_OPENAI_MODEL

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
    template_path = Path(args.prompt_template)
    if not template_path.exists():
        logger.error("Prompt template not found: %s", template_path)
        sys.exit(1)

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        keep_trailing_newline=True,
    )
    try:
        template = env.get_template(template_path.name)
    except TemplateNotFound:
        logger.error("Could not load template: %s", template_path)
        sys.exit(1)

    # --- Prepare output path -----------------------------------------------
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_model_name(model_name)
    if args.temperature > 0:
        output_path = output_dir / f"{safe_name}_temp{args.temperature}.jsonl"
    else:
        output_path = output_dir / f"{safe_name}.jsonl"

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
            prompt_text = template.render(riddle=riddle_text)

            # Call the LLM
            raw_response = ""
            input_tokens: int | None = None
            output_tokens: int | None = None
            try:
                llm_resp = call_llm(
                    provider=args.provider,
                    prompt_text=prompt_text,
                    model_name=model_name,
                    temperature=args.temperature,
                    api_key=api_key,
                    max_output_tokens=max_output_tokens,
                )
                raw_response = llm_resp.text
                input_tokens = llm_resp.input_tokens
                output_tokens = llm_resp.output_tokens
            except Exception as exc:
                logger.error(
                    "Failed to get response for %s (%s, sample %d) after %d retries: %s",
                    riddle_id,
                    riddle_type,
                    sample_index,
                    MAX_RETRIES,
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
                model_name=model_name,
                temperature=args.temperature,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
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
                prompt_text = template.render(riddle=riddle_text)
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
                    model_name=model_name,
                    temperature=args.temperature,
                    input_tokens=input_tokens_val,
                    output_tokens=output_tokens_val,
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
        choices=["gemini", "openai", "local"],
        default="gemini",
        help="LLM provider to use ('local' targets the OpenAI-compatible server at LOCAL_BASE_URL).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "Model name to use. Defaults to "
            f"'{DEFAULT_GEMINI_MODEL}' for Gemini or "
            f"'{DEFAULT_OPENAI_MODEL}' for OpenAI."
        ),
    )
    parser.add_argument(
        "--benchmark",
        type=str,
        default="data/benchmark.jsonl",
        help="Path to the benchmark JSONL file.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/model_outputs",
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
