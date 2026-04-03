#!/usr/bin/env python3
"""generate.py — Generate altered-riddle pairs from source riddles via LLM.

Usage examples:
    python scripts/generate.py --provider gemini --num-calls 20 --batch-size 8
    python scripts/generate.py --provider openai --model gpt-4o-mini --source data/riddles_source.txt
    python scripts/generate.py --provider local --num-calls 40 --batch-size 16
    python -m scripts.generate --num-variations 3 --num-calls 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
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
    # level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generate")

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------
DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
MAX_RETRIES = 3
INITIAL_BACKOFF_S = 2.0
LOCAL_BASE_URL = "http://10.8.0.5:8083/v1"
DEFAULT_LOCAL_MODEL = "Mistral-Small-4-119B-2603"
DEFAULT_BATCH_SIZE = 10  # max concurrent async requests per batch


# ---------------------------------------------------------------------------
# LLM call helpers  (sync — used when batch_size == 1)
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
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
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
    kwargs: dict[str, Any] = dict(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
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
        create_kwargs: dict[str, Any] = dict(
            model=model,
            messages=[{"role": "user", "content": prompt_text}],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
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


def load_source_riddles(path: str) -> list[str]:
    """Load riddles from a text file (one riddle per line, blank lines ignored)."""
    filepath = Path(path)
    if not filepath.exists():
        logger.warning(
            "Source file %s not found — will use free generation only.", path
        )
        return []
    with open(filepath, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


def load_template(template_path: str) -> jinja2.Template:
    """Load and compile a Jinja2 template from *template_path*."""
    tpl_path = Path(template_path)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tpl_path.parent)),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    return env.get_template(tpl_path.name)


def parse_riddle_array(raw_text: str) -> list[dict[str, Any]]:
    """Parse the LLM response text into a list of riddle-pair dicts.

    The response may be a JSON array directly or a JSON object wrapping one
    (e.g. ``{"riddles": [...]}``)  — we handle both.
    """
    text = raw_text.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    parsed = json.loads(text)

    if isinstance(parsed, list):
        return parsed

    # If the model wrapped the array in an object, grab the first list value.
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value

    raise ValueError(f"Unexpected JSON structure: {type(parsed)}")


REQUIRED_FIELDS = {
    "original_riddle",
    "original_answer",
    "original_reasoning",
    "altered_riddle",
    "altered_answer",
    "altered_reasoning",
    "type",
}


def validate_entry(entry: dict[str, Any]) -> bool:
    """Return True if the entry has all required fields with non-empty values."""
    return all(entry.get(f) for f in REQUIRED_FIELDS)


def write_jsonl_entry(fh, entry: dict[str, Any]) -> None:
    """Append a single JSON object as one line to an open file handle."""
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------


def generate(args: argparse.Namespace) -> None:
    """Run the generation pipeline according to parsed CLI *args*."""
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

    # Load source riddles + template
    source_riddles = load_source_riddles(args.source)
    template = load_template(args.prompt_template)

    batch_size = args.batch_size
    use_batching = batch_size > 1

    logger.info("Provider    : %s", provider)
    logger.info("Model       : %s", model)
    logger.info(
        "Source      : %s (%d riddles loaded)", args.source, len(source_riddles)
    )
    logger.info("Output      : %s", output_path)
    logger.info("Calls       : %d × %d variations", args.num_calls, args.num_variations)
    logger.info("Temp        : %.2f", args.temperature)
    if args.max_output_tokens is not None:
        logger.info("Max tokens  : %d", args.max_output_tokens)
    logger.info(
        "Batching    : %s (batch_size=%d)",
        "enabled" if use_batching else "disabled (sequential)",
        batch_size,
    )

    total_generated = 0
    total_skipped = 0
    global_index = 0

    # Build all prompts upfront so we can slice them into async batches.
    # Each prompt is paired with a human-readable label for logging.
    call_prompts: list[tuple[str, str]] = []  # (prompt_text, label)
    for _ in range(args.num_calls):
        source_riddle = None
        if source_riddles and random.random() < 0.7:
            source_riddle = random.choice(source_riddles)
        prompt_text = template.render(
            source_riddle=source_riddle,
            num_variations=args.num_variations,
            few_shot_examples=None,
        )
        label = (source_riddle[:60] + "…") if source_riddle else "<free generation>"
        call_prompts.append((prompt_text, label))

    with open(output_path, "a", encoding="utf-8") as out_fh:
        if use_batching:
            # ----------------------------------------------------------
            # BATCHED PATH  (all providers, async concurrency)
            # Slice call_prompts into chunks of batch_size, dispatch each
            # chunk as concurrent async requests, then process results.
            # ----------------------------------------------------------
            for chunk_start in range(0, len(call_prompts), batch_size):
                chunk = call_prompts[chunk_start : chunk_start + batch_size]
                prompts_only = [p for p, _ in chunk]

                logger.info(
                    "Dispatching batch %d–%d / %d …",
                    chunk_start + 1,
                    chunk_start + len(chunk),
                    args.num_calls,
                )

                raw_results: list[str | BaseException] = call_llm_batched(
                    prompts_only,
                    provider=provider,
                    model=model,
                    temperature=args.temperature,
                    api_key=api_key,
                    max_output_tokens=args.max_output_tokens,
                    max_concurrency=batch_size,
                )

                for rel_idx, ((_, label), raw) in enumerate(
                    zip(chunk, raw_results), start=chunk_start + 1
                ):
                    logger.info("  [%d/%d] source: %s", rel_idx, args.num_calls, label)

                    if isinstance(raw, BaseException):
                        logger.error(
                            "  Call %d failed after retries: %s — skipping.",
                            rel_idx,
                            raw,
                        )
                        continue

                    try:
                        entries = parse_riddle_array(raw)
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.error(
                            "  Call %d unparseable JSON: %s — skipping.", rel_idx, exc
                        )
                        logger.debug("  Raw response:\n%s", raw[:500])
                        continue

                    for entry in entries:
                        if not validate_entry(entry):
                            logger.warning(
                                "Skipping entry with missing fields: %s", entry
                            )
                            total_skipped += 1
                            continue
                        global_index += 1
                        entry["id"] = f"gen_{ts}_{global_index:03d}"
                        entry["source"] = model
                        write_jsonl_entry(out_fh, entry)
                        total_generated += 1

                    logger.info(
                        "  → parsed %d entries (%d valid so far)",
                        len(entries),
                        total_generated,
                    )
                    out_fh.flush()

        else:
            # ----------------------------------------------------------
            # SEQUENTIAL PATH  (batch_size == 1)
            # ----------------------------------------------------------
            for call_idx, (prompt_text, label) in enumerate(call_prompts, start=1):
                logger.info("Call %d/%d — source: %s", call_idx, args.num_calls, label)

                try:
                    raw = call_llm(
                        prompt_text,
                        provider=provider,
                        model=model,
                        temperature=args.temperature,
                        api_key=api_key,
                        max_output_tokens=args.max_output_tokens,
                    )
                except Exception as exc:
                    logger.error(
                        "Call %d failed after retries: %s — skipping.", call_idx, exc
                    )
                    continue

                try:
                    entries = parse_riddle_array(raw)
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.error(
                        "Call %d returned unparseable JSON: %s — skipping.",
                        call_idx,
                        exc,
                    )
                    logger.debug("Raw response:\n%s", raw[:500])
                    continue

                for entry in entries:
                    if not validate_entry(entry):
                        logger.warning("Skipping entry with missing fields: %s", entry)
                        total_skipped += 1
                        continue
                    global_index += 1
                    entry["id"] = f"gen_{ts}_{global_index:03d}"
                    entry["source"] = model
                    write_jsonl_entry(out_fh, entry)
                    total_generated += 1

                out_fh.flush()
                logger.info(
                    "  → parsed %d entries (%d valid so far)",
                    len(entries),
                    total_generated,
                )

    logger.info("=" * 60)
    logger.info(
        "Done. Generated %d entries, skipped %d.", total_generated, total_skipped
    )
    logger.info("Output written to %s", output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate altered-riddle pairs from source riddles via an LLM.",
    )
    parser.add_argument(
        "--provider",
        choices=["gemini", "openai", "local"],
        default="gemini",
        help="LLM provider to use: gemini, openai, or local (default: gemini)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: gemma-4-31b-it / gpt-4o-mini / Mistral-Small-4-119B-2603)",
    )
    parser.add_argument(
        "--source",
        default="data/riddles_source.txt",
        help="Path to source riddles file, one per line (default: data/riddles_source.txt)",
    )
    parser.add_argument(
        "--output",
        default="data/generated/raw_{timestamp}.jsonl",
        help=(
            "Output JSONL path. {timestamp} is replaced at runtime "
            "(default: data/generated/raw_{timestamp}.jsonl)"
        ),
    )
    parser.add_argument(
        "--num-variations",
        type=int,
        default=5,
        help="Number of variations to request per API call (default: 5)",
    )
    parser.add_argument(
        "--num-calls",
        type=int,
        default=10,
        help="Number of API calls to make (default: 10)",
    )
    parser.add_argument(
        "--prompt-template",
        default="prompts/generation.j2",
        help="Path to Jinja2 prompt template (default: prompts/generation.j2)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature (default: 1.0)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "Max concurrent async requests dispatched per batch (all providers). "
            "Set to 1 to disable batching and use the sequential path. "
            f"(default: {DEFAULT_BATCH_SIZE})"
        ),
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Maximum output tokens for the LLM (None = provider default).",
    )
    return parser


if __name__ == "__main__":
    generate(build_parser().parse_args())
