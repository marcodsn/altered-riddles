#!/usr/bin/env python3
"""generate.py — Generate altered-riddle pairs from source riddles via LLM.

Usage examples:
    python -m scripts.generate --provider gemini --num-calls 20 --batch-size 8
    python -m scripts.generate --provider openai --model gpt-5.4 --source data/riddles_source.txt
    python -m scripts.generate --provider local --num-calls 40 --batch-size 16
    python -m scripts.generate --num-variations 3 --num-calls 2
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import DEFAULT_BATCH_SIZE, provider_names, resolve_provider
from scripts.core.io_utils import (
    load_template,
    write_jsonl_entry,
)
from scripts.core.llm_client import call_llm, call_llm_batched
from scripts.core.parsing import REQUIRED_FIELDS, parse_riddle_array, validate_entry

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
# Helpers
# ---------------------------------------------------------------------------


def load_source_riddles(path: str) -> list[str]:
    """Load riddles from a text file (one riddle per line, blank lines ignored)."""
    filepath = Path(path)
    if not filepath.exists():
        logger.warning("Source file %s not found — will use free generation only.", path)
        return []
    with open(filepath, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------


def generate(args: argparse.Namespace) -> None:
    """Run the generation pipeline according to parsed CLI *args*."""
    load_dotenv()

    # Resolve provider + API key via shared config
    provider = args.provider
    model, api_key = resolve_provider(provider, args.model)

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
    logger.info("Source      : %s (%d riddles loaded)", args.source, len(source_riddles))
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
        target_type = args.type if args.type != "random" else None
        prompt_text = template.render(
            source_riddle=source_riddle,
            num_variations=args.num_variations,
            few_shot_examples=None,
            target_type=target_type,
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

                raw_results = call_llm_batched(
                    prompts_only,
                    provider=provider,
                    model=model,
                    temperature=args.temperature,
                    api_key=api_key,
                    max_output_tokens=args.max_output_tokens,
                    max_concurrency=batch_size,
                )

                for rel_idx, ((_, label), result) in enumerate(
                    zip(chunk, raw_results), start=chunk_start + 1
                ):
                    logger.info("  [%d/%d] source: %s", rel_idx, args.num_calls, label)

                    if isinstance(result, BaseException):
                        logger.error(
                            "  Call %d failed after retries: %s — skipping.",
                            rel_idx,
                            result,
                        )
                        continue

                    raw = result.text  # LLMResponse

                    try:
                        entries = parse_riddle_array(raw)
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.error("  Call %d unparseable JSON: %s — skipping.", rel_idx, exc)
                        logger.debug("  Raw response:\n%s", raw[:500])
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
                    resp = call_llm(
                        prompt_text,
                        provider=provider,
                        model=model,
                        temperature=args.temperature,
                        api_key=api_key,
                        max_output_tokens=args.max_output_tokens,
                    )
                    raw = resp.text
                except Exception as exc:
                    logger.error("Call %d failed after retries: %s — skipping.", call_idx, exc)
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
    logger.info("Done. Generated %d entries, skipped %d.", total_generated, total_skipped)
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
        choices=provider_names(),
        default="gemini",
        help="LLM provider to use (default: gemini; see config.py for full list)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override (default: per-provider default; see config.py)",
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
    parser.add_argument(
        "--type",
        choices=[
            "constraint_addition",
            "meaning_shift",
            "context_swap",
            "bias_probe",
            "random",
        ],
        default="random",
        help=(
            "Alteration type to generate. When not 'random', instructs the LLM "
            "to produce only that specific type (default: random)."
        ),
    )
    return parser


if __name__ == "__main__":
    generate(build_parser().parse_args())
