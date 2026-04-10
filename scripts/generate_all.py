#!/usr/bin/env python3
"""generate_all.py — Generate riddles using multiple LLM families.

Orchestrates generation across all models listed in GENERATOR_MODELS
(see config.py), validates results, and stores valid riddles in the
pool for later promotion to the benchmark.

Usage:
    python -m scripts.generate_all
    python -m scripts.generate_all --num-calls 10 --validate
    python -m scripts.generate_all --num-calls 5 --validate --validate-provider openai
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from scripts.core.config import (
    DEFAULT_POOL,
    DEFAULT_SOURCE,
    GENERATOR_MODELS,
    resolve_provider,
)
from scripts.core.io_utils import (
    append_jsonl,
    load_jsonl_if_exists,
    load_template,
    sanitize_model_name,
    write_jsonl_entry,
)
from scripts.core.llm_client import call_llm_batched
from scripts.core.parsing import (
    REQUIRED_FIELDS,
    parse_riddle_array,
    parse_validation_response,
    to_benchmark_format,
    validate_entry,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("generate_all")


# ---------------------------------------------------------------------------
# Source riddles
# ---------------------------------------------------------------------------


def load_source_riddles(path: str) -> list[str]:
    """Load riddles from a text file (one per line, blanks ignored)."""
    filepath = Path(path)
    if not filepath.exists():
        logger.warning("Source file %s not found — free generation only.", path)
        return []
    with open(filepath, encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# Build generation prompts
# ---------------------------------------------------------------------------


def build_generation_prompts(
    template,
    source_riddles: list[str],
    num_calls: int,
    num_variations: int,
    target_type: str | None = None,
) -> list[str]:
    """Return *num_calls* rendered generation prompts."""
    prompts: list[str] = []
    for _ in range(num_calls):
        source_riddle = None
        if source_riddles and random.random() < 0.7:
            source_riddle = random.choice(source_riddles)
        prompt_text = template.render(
            source_riddle=source_riddle,
            num_variations=num_variations,
            few_shot_examples=None,
            target_type=target_type,
        )
        prompts.append(prompt_text)
    return prompts


# ---------------------------------------------------------------------------
# Build validation prompts
# ---------------------------------------------------------------------------


def build_validation_prompts(
    template,
    entries: list[dict[str, Any]],
) -> list[str]:
    """Return one rendered validation prompt per entry."""
    prompts: list[str] = []
    for entry in entries:
        prompt_text = template.render(
            original_riddle=entry.get("original_riddle", ""),
            original_answer=entry.get("original_answer", ""),
            altered_riddle=entry.get("altered_riddle", ""),
            altered_answer=entry.get("altered_answer", ""),
            altered_reasoning=entry.get("altered_reasoning", ""),
        )
        prompts.append(prompt_text)
    return prompts


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def generate_all(args: argparse.Namespace) -> None:  # noqa: C901
    """Run multi-model generation (and optional validation)."""
    load_dotenv()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_riddles = load_source_riddles(args.source)
    gen_template = load_template("prompts/generation.j2")

    # Resolve target_type for generation prompts
    target_type: str | None = None
    if hasattr(args, "type") and args.type and args.type != "random":
        target_type = args.type

    val_template = None
    val_model = val_api_key = val_provider = None
    if args.validate:
        val_template = load_template("prompts/validation.j2")
        val_provider = args.validate_provider
        val_model, val_api_key = resolve_provider(val_provider, args.validate_model)

    # Per-model stats: {label: {generated, valid, validated, passed}}
    stats: dict[str, dict[str, int]] = {}

    # Collect every entry that should go to the pool
    pool_entries: list[dict[str, Any]] = []

    logger.info("=" * 60)
    logger.info("Multi-model generation — %d generator(s)", len(GENERATOR_MODELS))
    logger.info("Calls/model : %d × %d variations", args.num_calls, args.num_variations)
    logger.info("Source      : %s (%d riddles)", args.source, len(source_riddles))
    logger.info("Batch size  : %d", args.batch_size)
    logger.info("Temperature : %.2f", args.temperature)
    logger.info(
        "Validate    : %s",
        f"yes ({val_provider}/{val_model})" if args.validate else "no",
    )
    logger.info("=" * 60)

    for gen_cfg in GENERATOR_MODELS:
        provider = gen_cfg["provider"]
        model, api_key = resolve_provider(provider, gen_cfg.get("model"))
        label = f"{provider}/{model}"
        safe_name = sanitize_model_name(model)

        logger.info("-" * 60)
        logger.info("Generator: %s", label)

        model_stats: dict[str, int] = {
            "generated": 0,
            "valid": 0,
            "validated": 0,
            "passed": 0,
        }
        stats[label] = model_stats

        # ── 1. Build & dispatch generation prompts ────────────────────
        prompts = build_generation_prompts(
            gen_template,
            source_riddles,
            args.num_calls,
            args.num_variations,
            target_type=target_type,
        )

        valid_entries: list[dict[str, Any]] = []
        raw_path = output_dir / f"raw_{safe_name}_{ts}.jsonl"
        global_idx = 0

        for chunk_start in range(0, len(prompts), args.batch_size):
            chunk = prompts[chunk_start : chunk_start + args.batch_size]
            logger.info(
                "  Dispatching generation batch %d–%d / %d …",
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

            with open(raw_path, "a", encoding="utf-8") as raw_fh:
                for rel_idx, result in enumerate(raw_results, start=chunk_start + 1):
                    if isinstance(result, BaseException):
                        logger.error("  Call %d failed: %s — skipping.", rel_idx, result)
                        continue

                    try:
                        entries = parse_riddle_array(result.text)
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.error("  Call %d unparseable: %s — skipping.", rel_idx, exc)
                        continue

                    model_stats["generated"] += len(entries)

                    for entry in entries:
                        if not validate_entry(entry):
                            continue
                        global_idx += 1
                        entry["id"] = f"gen_{safe_name}_{ts}_{global_idx:04d}"
                        entry["source"] = model
                        write_jsonl_entry(raw_fh, entry)
                        valid_entries.append(entry)

                    logger.info(
                        "    Call %d → %d entries (%d structurally valid so far)",
                        rel_idx,
                        len(entries),
                        len(valid_entries),
                    )

        model_stats["valid"] = len(valid_entries)
        logger.info(
            "  %s: %d generated, %d structurally valid",
            label,
            model_stats["generated"],
            model_stats["valid"],
        )
        logger.info("  Raw output → %s", raw_path)

        # ── 2. Optional LLM validation ────────────────────────────────
        if (
            args.validate
            and valid_entries
            and val_template is not None
            and val_provider is not None
            and val_model is not None
            and val_api_key is not None
        ):
            logger.info("  Running validation on %d entries …", len(valid_entries))
            val_prompts = build_validation_prompts(val_template, valid_entries)

            passing: list[dict[str, Any]] = []

            for vchunk_start in range(0, len(val_prompts), args.batch_size):
                vchunk = val_prompts[vchunk_start : vchunk_start + args.batch_size]
                vchunk_entries = valid_entries[vchunk_start : vchunk_start + len(vchunk)]

                logger.info(
                    "  Validation batch %d–%d / %d …",
                    vchunk_start + 1,
                    vchunk_start + len(vchunk),
                    len(val_prompts),
                )

                val_results = call_llm_batched(
                    vchunk,
                    provider=val_provider,
                    model=val_model,
                    temperature=0.3,
                    api_key=val_api_key,
                    max_output_tokens=args.max_output_tokens,
                    max_concurrency=args.batch_size,
                )

                for entry, vres in zip(vchunk_entries, val_results):
                    model_stats["validated"] += 1
                    if isinstance(vres, BaseException):
                        logger.error("  Validation failed for %s: %s", entry.get("id"), vres)
                        continue
                    try:
                        validation = parse_validation_response(vres.text)
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.error("  Unparseable validation for %s: %s", entry.get("id"), exc)
                        continue

                    overall = bool(validation.get("overall_valid", False))
                    if overall:
                        # Merge competing_answers into entry for pool format
                        entry["competing_answers"] = validation.get("competing_answers", [])
                        passing.append(entry)
                        model_stats["passed"] += 1

                    logger.debug(
                        "    %s → %s",
                        entry.get("id"),
                        "PASS" if overall else "FAIL",
                    )

            logger.info(
                "  Validation done: %d / %d passed",
                model_stats["passed"],
                model_stats["validated"],
            )
            pool_entries.extend(passing)
        else:
            # No validation — all structurally valid entries go to pool
            pool_entries.extend(valid_entries)

    # ── 3. Write pool ─────────────────────────────────────────────────
    existing_pool = load_jsonl_if_exists(DEFAULT_POOL)
    pool_max_idx = 0
    for pe in existing_pool:
        pid = pe.get("id", "")
        if pid.startswith("pool_"):
            try:
                pool_max_idx = max(pool_max_idx, int(pid.split("_")[1]))
            except (IndexError, ValueError):
                pass

    new_count = 0
    for entry in pool_entries:
        pool_max_idx += 1
        new_id = f"pool_{pool_max_idx:04d}"
        pool_record = to_benchmark_format(entry, new_id)
        append_jsonl(DEFAULT_POOL, pool_record)
        new_count += 1

    # ── 4. Summary ────────────────────────────────────────────────────
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(
        "%-35s %8s %8s %8s %8s",
        "Model",
        "Raw",
        "Valid",
        "Checked",
        "Passed",
    )
    logger.info("-" * 75)
    for lbl, s in stats.items():
        logger.info(
            "%-35s %8d %8d %8d %8d",
            lbl,
            s["generated"],
            s["valid"],
            s["validated"],
            s["passed"],
        )
    logger.info("-" * 75)
    logger.info("New entries appended to %s: %d", DEFAULT_POOL, new_count)
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate riddles using multiple LLM families and store in pool.",
    )
    parser.add_argument(
        "--num-calls",
        type=int,
        default=5,
        help="API calls per generator model (default: 5)",
    )
    parser.add_argument(
        "--num-variations",
        type=int,
        default=5,
        help="Variations requested per call (default: 5)",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=DEFAULT_SOURCE,
        help=f"Source riddles file (default: {DEFAULT_SOURCE})",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run LLM validation on generated riddles before pooling",
    )
    parser.add_argument(
        "--validate-provider",
        type=str,
        default="gemini",
        help="Provider for the validation model (default: gemini)",
    )
    parser.add_argument(
        "--validate-model",
        type=str,
        default=None,
        help="Model name for validation (default: provider default)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Batch size for concurrent requests (default: 10)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature for generation (default: 1.0)",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Max output tokens (default: provider default)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/generated",
        help="Directory for raw generation outputs (default: data/generated)",
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
            "Alteration type to generate. 'random' lets the LLM choose freely. "
            "Any other value instructs the LLM to produce only that type. "
            "(default: random)"
        ),
    )
    return parser


if __name__ == "__main__":
    generate_all(build_parser().parse_args())
