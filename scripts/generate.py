#!/usr/bin/env python3
"""generate.py — Generate altered riddles from common source riddles.

Uses riddles with mean_accuracy >= 0.6 from sanity check results.
Prioritizes underrepresented original riddles.

Usage:
    python -m scripts.generate --provider gemini --num-calls 20
    python -m scripts.generate --provider local --model qwen3.5-27b --num-calls 10
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_RAW,
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
    strip_markdown_fences,
)
from scripts.core.llm_client import call_llm_batched

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("generate")

REQUIRED_FIELDS = {
    "original_riddle",
    "original_answer",
    "original_reasoning",
    "altered_riddle",
    "altered_answer",
    "altered_reasoning",
    "type",
}


def parse_riddle_array(raw_text: str) -> list[dict]:
    text = strip_markdown_fences(raw_text)
    parsed = json.loads(text)
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value
    raise ValueError(f"Unexpected JSON structure: {type(parsed)}")


def load_common_riddles(
    source_path: str, sanity_path: str, min_accuracy: float = 0.6
) -> list[dict[str, str]]:
    """Load source riddles filtered by mean_accuracy >= min_accuracy from sanity results."""
    all_riddles = load_source_riddles(source_path)
    sanity_file = Path(sanity_path)
    if not sanity_file.exists():
        logger.warning("Sanity results not found at %s — using all source riddles.", sanity_path)
        return all_riddles

    with open(sanity_file, encoding="utf-8") as f:
        sanity = json.load(f)

    # Build set of riddle indices that pass the threshold
    passing_indices = set()
    for entry in sanity.get("per_riddle", []):
        if entry.get("mean_accuracy", 0) >= min_accuracy:
            passing_indices.add(entry["riddle_idx"])

    filtered = [r for i, r in enumerate(all_riddles) if i in passing_indices]
    logger.info(
        "Filtered to %d common riddles (mean_accuracy >= %.0f%%) from %d total.",
        len(filtered),
        min_accuracy * 100,
        len(all_riddles),
    )
    return filtered


def pick_underrepresented(
    common_riddles: list[dict], existing_raw: list[dict], count: int
) -> list[dict]:
    """Pick riddles prioritizing those least represented in existing raw data."""
    # Count occurrences of each original riddle in existing raw
    orig_counts = Counter()
    for entry in existing_raw:
        orig = entry.get("original_riddle", "").strip().lower()
        if orig:
            orig_counts[orig] += 1

    # Sort common riddles by representation (ascending), with random tiebreak
    scored = []
    for r in common_riddles:
        key = r["riddle"].strip().lower()
        scored.append((orig_counts.get(key, 0), random.random(), r))
    scored.sort()

    # Return the least-represented ones, cycling if needed
    selected = []
    while len(selected) < count:
        for _, _, r in scored:
            if len(selected) >= count:
                break
            selected.append(r)
    return selected


def generate(args):
    load_dotenv()
    provider = args.provider
    model, api_key = resolve_provider(provider, args.model)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    common_riddles = load_common_riddles(args.source, args.sanity_results, args.min_accuracy)
    if not common_riddles:
        logger.error("No common riddles found. Run sanity_check first.")
        raise SystemExit(1)

    existing_raw = load_jsonl_if_exists(args.output)
    template = load_template(args.prompt_template)

    logger.info("Provider     : %s", provider)
    logger.info("Model        : %s", model)
    logger.info("Common riddles: %d", len(common_riddles))
    logger.info("Existing raw : %d entries", len(existing_raw))
    logger.info("Calls        : %d (4 riddles per call)", args.num_calls)
    logger.info("Output       : %s", output_path)

    # Pick source riddles for each call, prioritizing underrepresented
    source_picks = pick_underrepresented(common_riddles, existing_raw, args.num_calls)

    # Build prompts
    prompts = []
    for riddle_entry in source_picks:
        prompt_text = template.render(
            source_riddle=riddle_entry["riddle"],
            source_answer=riddle_entry["answer"],
            num_variations=4,
            few_shot_examples=None,
            target_type=None,
        )
        prompts.append(prompt_text)

    total_generated = 0
    total_skipped = 0
    global_index = len(existing_raw)

    for chunk_start in range(0, len(prompts), args.batch_size):
        chunk = prompts[chunk_start : chunk_start + args.batch_size]
        logger.info(
            "Dispatching batch %d-%d / %d...",
            chunk_start + 1,
            chunk_start + len(chunk),
            len(prompts),
        )

        raw_results = call_llm_batched(
            chunk,
            provider=provider,
            model=model,
            temperature=args.temperature,
            api_key=api_key,
            max_output_tokens=args.max_output_tokens,
            max_concurrency=args.batch_size,
        )

        for rel_idx, result in enumerate(raw_results, start=chunk_start + 1):
            if isinstance(result, BaseException):
                logger.error("Call %d failed: %s", rel_idx, result)
                continue
            try:
                entries = parse_riddle_array(result.text)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.error("Call %d unparseable: %s", rel_idx, exc)
                continue

            for entry in entries:
                if not all(entry.get(f) for f in REQUIRED_FIELDS):
                    total_skipped += 1
                    continue
                global_index += 1
                entry["id"] = f"raw_{global_index:04d}"
                entry["source"] = model
                append_jsonl(output_path, entry)
                total_generated += 1

            logger.info(
                "  Call %d -> %d entries (%d valid total)", rel_idx, len(entries), total_generated
            )

    logger.info("=" * 60)
    logger.info(
        "Done. Generated %d, skipped %d. Output: %s", total_generated, total_skipped, output_path
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate altered riddles from common source riddles."
    )
    parser.add_argument("--provider", choices=provider_names(), default="gemini")
    parser.add_argument("--model", default=None)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--sanity-results", default=DEFAULT_SANITY_RESULTS)
    parser.add_argument("--output", default=DEFAULT_RAW)
    parser.add_argument("--prompt-template", default="prompts/generation.j2")
    parser.add_argument("--num-calls", type=int, default=10)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=0.6,
        help="Min mean accuracy for common riddles (default: 0.6)",
    )
    return parser


if __name__ == "__main__":
    generate(build_parser().parse_args())
