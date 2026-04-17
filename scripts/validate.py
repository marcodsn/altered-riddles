#!/usr/bin/env python3
"""validate.py — Validate raw altered riddles using an LLM.

Reads raw.jsonl, validates each entry, appends passing entries to validated.jsonl.

Usage:
    python -m scripts.validate --provider local
    python -m scripts.validate --provider gemini --batch-size 20
"""

from __future__ import annotations

import argparse
import json
import logging

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_RAW,
    DEFAULT_REJECTED,
    DEFAULT_VALIDATED,
    provider_names,
    resolve_provider,
)
from scripts.core.io_utils import (
    append_jsonl,
    load_jsonl,
    load_jsonl_if_exists,
    load_template,
    strip_markdown_fences,
)
from scripts.core.llm_client import call_llm_batched

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("validate")


def _entry_key(entry: dict) -> tuple[str, str] | None:
    orig = entry.get("original_riddle", "").strip().lower()
    alt = entry.get("altered_riddle", "").strip().lower()
    return (orig, alt) if orig and alt else None


def parse_validation_response(raw_text: str) -> dict:
    text = strip_markdown_fences(raw_text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object, got {type(parsed)}")
    return parsed


def to_validated_format(entry: dict, new_id: str, validation: dict) -> dict:
    """Convert a raw entry + validation result to the validated format."""
    original_answer = entry.get("original_answer", "")

    # Build accepted answers from validation response
    llm_accepted = validation.get("altered_accepted_answers", [])
    altered_answer = entry.get("altered_answer", "")
    if llm_accepted and isinstance(llm_accepted, list):
        seen = set()
        accepted = []
        for ans in [altered_answer] + llm_accepted:
            key = ans.strip().lower()
            if key and key not in seen:
                seen.add(key)
                accepted.append(ans)
    else:
        accepted = [altered_answer] if altered_answer else []

    # Build competing answers (exclude original answer)
    orig_lower = original_answer.strip().lower()
    competing = [
        a
        for a in validation.get("competing_answers", [])
        if a.strip().lower() != orig_lower
    ]

    return {
        "id": new_id,
        "original_riddle": entry.get("original_riddle", ""),
        "original_answer": original_answer,
        "original_accepted_answers": [original_answer] if original_answer else [],
        "original_reasoning": entry.get("original_reasoning", ""),
        "altered_riddle": entry.get("altered_riddle", ""),
        "altered_answer": altered_answer,
        "altered_accepted_answers": accepted,
        "altered_competing_answers": competing,
        "altered_reasoning": entry.get("altered_reasoning", ""),
        "source": entry.get("source", ""),
        "type": entry.get("type", "constraint_addition"),
        # Validation quality signals
        "answer_valid": bool(validation.get("answer_valid", False)),
        "is_distinct": bool(validation.get("is_distinct", False)),
        "has_competing_answers": bool(validation.get("has_competing_answers", False)),
        "is_subtle": bool(validation.get("is_subtle", False)),
        "is_logical": bool(validation.get("is_logical", False)),
        "is_clear": bool(validation.get("is_clear", False)),
        "needs_review": bool(validation.get("needs_review", False)),
        "review_reason": validation.get("review_reason", ""),
        "validation_reasoning": validation.get("reasoning", ""),
    }


def validate(args):
    load_dotenv()
    provider = args.provider
    model, api_key = resolve_provider(provider, args.model)
    template = load_template(args.prompt_template)

    raw_entries = load_jsonl(args.input)
    logger.info("Loaded %d raw entries from %s", len(raw_entries), args.input)

    # Load already-validated keys to skip duplicates
    existing_validated = load_jsonl_if_exists(args.output)
    already_done = set()
    for e in existing_validated:
        k = _entry_key(e)
        if k:
            already_done.add(k)

    # Also skip previously-rejected entries so we don't waste LLM calls re-evaluating them
    existing_rejected = load_jsonl_if_exists(args.rejected)
    for e in existing_rejected:
        k = _entry_key(e)
        if k:
            already_done.add(k)

    # Filter to entries not yet processed
    to_validate = []
    for entry in raw_entries:
        k = _entry_key(entry)
        if k and k in already_done:
            continue
        to_validate.append(entry)

    logger.info(
        "Skipping %d already-processed (%d validated, %d rejected). %d to validate.",
        len(existing_validated) + len(existing_rejected),
        len(existing_validated),
        len(existing_rejected),
        len(to_validate),
    )

    if not to_validate:
        logger.info("Nothing to validate.")
        return

    # Build prompts
    entry_prompts = []
    for entry in to_validate:
        prompt = template.render(
            original_riddle=entry.get("original_riddle", ""),
            original_answer=entry.get("original_answer", ""),
            altered_riddle=entry.get("altered_riddle", ""),
            altered_answer=entry.get("altered_answer", ""),
            altered_reasoning=entry.get("altered_reasoning", ""),
        )
        entry_prompts.append((entry, prompt))

    next_id = len(existing_validated)
    total_passed = total_failed = 0

    for chunk_start in range(0, len(entry_prompts), args.batch_size):
        chunk = entry_prompts[chunk_start : chunk_start + args.batch_size]
        prompts_only = [p for _, p in chunk]

        logger.info(
            "Validating batch %d-%d / %d...",
            chunk_start + 1,
            chunk_start + len(chunk),
            len(entry_prompts),
        )

        results = call_llm_batched(
            prompts_only,
            provider=provider,
            model=model,
            temperature=0.3,
            api_key=api_key,
            max_output_tokens=args.max_output_tokens,
            max_concurrency=args.batch_size,
        )

        for (entry, _), result in zip(chunk, results):
            if isinstance(result, BaseException):
                logger.error(
                    "Validation failed for %s: %s", entry.get("id", "?"), result
                )
                continue

            try:
                validation = parse_validation_response(result.text)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.error(
                    "Unparseable response for %s: %s", entry.get("id", "?"), exc
                )
                continue

            passed = bool(validation.get("overall_valid", False))
            if passed:
                next_id += 1
                record = to_validated_format(entry, f"val_{next_id:04d}", validation)
                append_jsonl(args.output, record)
                total_passed += 1
            else:
                orig_lower = entry.get("original_answer", "").strip().lower()
                rej_competing = [
                    a
                    for a in validation.get("competing_answers", [])
                    if a.strip().lower() != orig_lower
                ]
                rejection_record = {
                    "original_riddle": entry.get("original_riddle", ""),
                    "original_answer": entry.get("original_answer", ""),
                    "original_reasoning": entry.get("original_reasoning", ""),
                    "altered_riddle": entry.get("altered_riddle", ""),
                    "altered_answer": entry.get("altered_answer", ""),
                    "altered_competing_answers": rej_competing,
                    "altered_reasoning": entry.get("altered_reasoning", ""),
                    "source": entry.get("source", ""),
                    "type": entry.get("type", "constraint_addition"),
                    # Validation quality signals
                    "answer_valid": bool(validation.get("answer_valid", False)),
                    "is_distinct": bool(validation.get("is_distinct", False)),
                    "has_competing_answers": bool(
                        validation.get("has_competing_answers", False)
                    ),
                    "is_subtle": bool(validation.get("is_subtle", False)),
                    "is_logical": bool(validation.get("is_logical", False)),
                    "is_clear": bool(validation.get("is_clear", False)),
                    "needs_review": bool(validation.get("needs_review", False)),
                    "review_reason": validation.get("review_reason", ""),
                    "validation_reasoning": validation.get("reasoning", ""),
                }
                append_jsonl(args.rejected, rejection_record)
                total_failed += 1

            logger.info(
                "  %s -> %s", entry.get("id", "?"), "PASS" if passed else "FAIL"
            )

    logger.info("=" * 60)
    logger.info(
        "Validation complete. %d passed, %d failed. Output: %s",
        total_passed,
        total_failed,
        args.output,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Validate raw altered riddles using an LLM."
    )
    parser.add_argument("--provider", choices=provider_names(), default="local")
    parser.add_argument("--model", default=None)
    parser.add_argument("--input", default=DEFAULT_RAW)
    parser.add_argument("--output", default=DEFAULT_VALIDATED)
    parser.add_argument("--rejected", default=DEFAULT_REJECTED)
    parser.add_argument("--prompt-template", default="prompts/validation.j2")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    return parser


if __name__ == "__main__":
    validate(build_parser().parse_args())
