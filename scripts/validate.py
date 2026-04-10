#!/usr/bin/env python3
"""validate.py — Validate generated altered riddles using an LLM.

Reads JSONL files of generated riddle pairs, sends each one through an LLM
validation prompt, and writes the results (with validation fields attached)
to an output JSONL file. Optionally appends passing entries to the benchmark
or the riddle pool.

Usage examples:
    python -m scripts.validate
    python -m scripts.validate --provider openai --append-to-pool
    python -m scripts.validate --input data/generated/raw_20250101_120000.jsonl
    python -m scripts.validate --input data/generated/raw.jsonl --append-to-pool
    python -m scripts.validate --input data/generated/raw.jsonl --delay 1.0
    python -m scripts.validate --promote-from-validated --append-to-pool
    python -m scripts.validate --re-validate --input data/benchmark.jsonl
    python -m scripts.validate --re-validate --filter-empty-competing --input data/pool.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jinja2
from dotenv import load_dotenv

from scripts.core.config import DEFAULT_POOL, provider_names, resolve_provider
from scripts.core.io_utils import (
    append_jsonl,
    get_max_benchmark_id,
    get_max_pool_id,
    load_jsonl,
    load_jsonl_if_exists,
    load_template,
    write_jsonl,
    write_jsonl_entry,
)
from scripts.core.llm_client import call_llm, call_llm_batched
from scripts.core.parsing import (
    parse_validation_response,
    to_benchmark_format,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("validate")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALIDATION_FIELDS = {
    "answer_valid",
    "is_distinct",
    "has_competing_answers",
    "is_subtle",
    "is_logical",
    "is_clear",
    "competing_answers",
    "altered_accepted_answers",
    "overall_valid",
    "reasoning",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry_key(entry: dict[str, Any]) -> tuple[str, str] | None:
    """Return a normalised (original_riddle, altered_riddle) key, or None if incomplete."""
    orig = entry.get("original_riddle", "").strip().lower()
    alt = entry.get("altered_riddle", "").strip().lower()
    return (orig, alt) if orig and alt else None


def _load_entry_keys(entries: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Extract normalised entry keys from a list of JSONL records."""
    keys: set[tuple[str, str]] = set()
    for entry in entries:
        key = _entry_key(entry)
        if key:
            keys.add(key)
    return keys


def init_promotion_state(args: argparse.Namespace) -> dict[str, Any]:
    """Initialise append targets, ID counters, and dedupe state."""
    state: dict[str, Any] = {
        "append_to_benchmark": args.append_to_benchmark,
        "append_to_pool": args.append_to_pool,
        "benchmark_path": "data/benchmark.jsonl",
        "pool_path": DEFAULT_POOL,
        "benchmark_existing_keys": set(),
        "pool_existing_keys": set(),
        "next_benchmark_id": 0,
        "next_pool_id": 0,
        "benchmark_appended": 0,
        "benchmark_skipped": 0,
        "pool_appended": 0,
        "pool_skipped": 0,
    }

    if args.append_to_benchmark:
        benchmark_path = Path(state["benchmark_path"])
        benchmark_path.parent.mkdir(parents=True, exist_ok=True)
        existing_benchmark = load_jsonl_if_exists(str(benchmark_path))
        state["benchmark_existing_keys"] = _load_entry_keys(existing_benchmark)
        state["next_benchmark_id"] = get_max_benchmark_id(str(benchmark_path))

    if args.append_to_pool:
        pool_path = Path(state["pool_path"])
        pool_path.parent.mkdir(parents=True, exist_ok=True)
        existing_pool = load_jsonl_if_exists(str(pool_path))
        state["pool_existing_keys"] = _load_entry_keys(existing_pool)
        state["next_pool_id"] = get_max_pool_id(str(pool_path))

    return state


def promote_entry(entry: dict[str, Any], state: dict[str, Any]) -> None:
    """Promote one passing validated entry into benchmark/pool immediately."""
    if not entry.get("overall_valid"):
        return

    key = _entry_key(entry)

    if state["append_to_benchmark"]:
        if key and key in state["benchmark_existing_keys"]:
            state["benchmark_skipped"] += 1
        else:
            state["next_benchmark_id"] += 1
            new_id = f"alt_{state['next_benchmark_id']:03d}"
            append_jsonl(
                state["benchmark_path"],
                to_benchmark_format(entry, new_id),
            )
            if key:
                state["benchmark_existing_keys"].add(key)
            state["benchmark_appended"] += 1

    if state["append_to_pool"]:
        if key and key in state["pool_existing_keys"]:
            state["pool_skipped"] += 1
        else:
            state["next_pool_id"] += 1
            new_id = f"pool_{state['next_pool_id']:04d}"
            append_jsonl(
                state["pool_path"],
                to_benchmark_format(entry, new_id),
            )
            if key:
                state["pool_existing_keys"].add(key)
            state["pool_appended"] += 1


def promote_from_validated(args: argparse.Namespace, generated_dir: Path) -> None:
    """Promote already-validated passing entries without re-calling the LLM."""
    if not (args.append_to_benchmark or args.append_to_pool):
        logger.error(
            "--promote-from-validated requires --append-to-benchmark and/or --append-to-pool."
        )
        return

    if args.input:
        input_paths = [Path(args.input)]
    else:
        input_paths = sorted(generated_dir.glob("validated_*.jsonl"))
        if not input_paths:
            logger.warning(
                "No validated_*.jsonl files found in %s — nothing to promote.",
                generated_dir,
            )
            return

    promotion_state = init_promotion_state(args)

    total_loaded = 0
    total_candidates = 0
    skipped_duplicates = 0
    seen_keys: set[tuple[str, str]] = set()

    for ipath in input_paths:
        batch = load_jsonl(str(ipath))
        total_loaded += len(batch)
        logger.info("Loaded %d entries from %s", len(batch), ipath)

        for entry in batch:
            if not entry.get("overall_valid"):
                continue

            key = _entry_key(entry)
            if key and key in seen_keys:
                skipped_duplicates += 1
                continue

            if key:
                seen_keys.add(key)

            total_candidates += 1
            promote_entry(entry, promotion_state)

    logger.info("=" * 60)
    logger.info(
        "Promotion-only mode scanned %d entries: %d valid candidates, %d "
        "duplicate candidates skipped.",
        total_loaded,
        total_candidates,
        skipped_duplicates,
    )
    if args.append_to_benchmark:
        logger.info(
            "Benchmark: appended %d, skipped %d already present.",
            promotion_state["benchmark_appended"],
            promotion_state["benchmark_skipped"],
        )
    if args.append_to_pool:
        logger.info(
            "Pool: appended %d, skipped %d already present.",
            promotion_state["pool_appended"],
            promotion_state["pool_skipped"],
        )


# ---------------------------------------------------------------------------
# Main validation loop
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Re-validation of existing entries
# ---------------------------------------------------------------------------


def revalidate_entries(args: argparse.Namespace) -> None:
    """Re-validate existing benchmark or pool entries via LLM.

    Loads entries from *args.input*, optionally filters to those with empty
    ``altered_competing_answers``, runs each through the validation LLM, and
    merges any newly discovered competing answers back into the entries.
    A timestamped backup of the input file is created before any modification.
    """
    load_dotenv()

    if not args.input:
        logger.error("--re-validate requires --input pointing to a JSONL file.")
        raise SystemExit(1)

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input file not found: %s", input_path)
        raise SystemExit(1)

    provider = args.provider
    model, api_key = resolve_provider(provider, args.model)
    template = load_template(args.prompt_template)

    # Load all entries
    all_entries = load_jsonl(str(input_path))
    logger.info("Loaded %d entries from %s", len(all_entries), input_path)

    # Decide which entries to re-validate
    if args.filter_empty_competing:
        indices_to_validate = [
            i for i, entry in enumerate(all_entries) if not entry.get("altered_competing_answers")
        ]
        logger.info(
            "Filtered to %d entries with empty altered_competing_answers.",
            len(indices_to_validate),
        )
    else:
        indices_to_validate = list(range(len(all_entries)))

    if not indices_to_validate:
        logger.info("No entries to re-validate. Exiting.")
        return

    # Create a backup before modifying
    backup_dir = input_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{input_path.stem}_{backup_ts}{input_path.suffix}"
    shutil.copy2(input_path, backup_path)
    logger.info("Backup created → %s", backup_path)

    batch_size = args.batch_size
    use_batching = batch_size > 1
    max_output_tokens: int | None = args.max_output_tokens

    logger.info("Provider : %s", provider)
    logger.info("Model    : %s", model)
    logger.info("Entries to re-validate: %d / %d", len(indices_to_validate), len(all_entries))

    # Build prompts for the entries to re-validate
    idx_prompt_pairs: list[tuple[int, str]] = []
    for idx in indices_to_validate:
        entry = all_entries[idx]
        try:
            prompt_text = template.render(
                original_riddle=entry.get("original_riddle", ""),
                original_answer=entry.get("original_answer", ""),
                altered_riddle=entry.get("altered_riddle", ""),
                altered_answer=entry.get("altered_answer", ""),
                altered_reasoning=entry.get("altered_reasoning", ""),
            )
            idx_prompt_pairs.append((idx, prompt_text))
        except jinja2.TemplateError as exc:
            logger.error(
                "Template render error for entry %s: %s — skipping.",
                entry.get("id"),
                exc,
            )

    total_processed = 0
    total_updated = 0

    if use_batching:
        for chunk_start in range(0, len(idx_prompt_pairs), batch_size):
            chunk = idx_prompt_pairs[chunk_start : chunk_start + batch_size]
            prompts_only = [p for _, p in chunk]

            logger.info(
                "Dispatching re-validation batch %d–%d / %d …",
                chunk_start + 1,
                chunk_start + len(chunk),
                len(idx_prompt_pairs),
            )

            raw_results = call_llm_batched(
                prompts_only,
                provider=provider,
                model=model,
                temperature=args.temperature,
                api_key=api_key,
                max_output_tokens=max_output_tokens,
                max_concurrency=batch_size,
            )

            for (entry_idx, _), raw in zip(chunk, raw_results):
                entry = all_entries[entry_idx]
                total_processed += 1

                if isinstance(raw, BaseException):
                    logger.error(
                        "  Re-validation failed for %s: %s — skipping.",
                        entry.get("id"),
                        raw,
                    )
                    continue

                raw_text = raw.text
                try:
                    validation = parse_validation_response(raw_text)
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.error(
                        "  Unparseable response for %s: %s — skipping.",
                        entry.get("id"),
                        exc,
                    )
                    continue

                updated = _merge_revalidation(entry, validation)
                if updated:
                    total_updated += 1

                logger.info(
                    "  %s → %s",
                    entry.get("id", "?"),
                    "updated" if updated else "no change",
                )
    else:
        for rel_idx, (entry_idx, prompt_text) in enumerate(idx_prompt_pairs, start=1):
            entry = all_entries[entry_idx]
            total_processed += 1

            logger.info(
                "Re-validating %d/%d — id=%s",
                rel_idx,
                len(idx_prompt_pairs),
                entry.get("id", "?"),
            )

            try:
                response = call_llm(
                    prompt_text,
                    provider=provider,
                    model=model,
                    temperature=args.temperature,
                    api_key=api_key,
                    max_output_tokens=max_output_tokens,
                )
            except Exception as exc:
                logger.error(
                    "Re-validation failed for %s: %s — skipping.",
                    entry.get("id"),
                    exc,
                )
                continue

            raw_text = response.text
            try:
                validation = parse_validation_response(raw_text)
            except (json.JSONDecodeError, ValueError) as exc:
                logger.error(
                    "Unparseable response for %s: %s — skipping.",
                    entry.get("id"),
                    exc,
                )
                continue

            updated = _merge_revalidation(entry, validation)
            if updated:
                total_updated += 1

            logger.info(
                "  %s → %s",
                entry.get("id", "?"),
                "updated" if updated else "no change",
            )

            if rel_idx < len(idx_prompt_pairs) and args.delay > 0:
                time.sleep(args.delay)

    # Write all entries back (including unmodified ones)
    write_jsonl(str(input_path), all_entries)

    logger.info("=" * 60)
    logger.info(
        "Re-validation complete. Processed %d entries, %d updated.",
        total_processed,
        total_updated,
    )
    logger.info("Updated file written to %s", input_path)
    logger.info("Backup at %s", backup_path)


def _merge_revalidation(entry: dict[str, Any], validation: dict[str, Any]) -> bool:
    """Merge newly discovered competing answers into *entry* in-place.

    Returns ``True`` if the entry was actually modified.
    """
    new_competing: list[str] = validation.get("competing_answers", [])
    if not new_competing:
        return False

    existing: list[str] = entry.get("altered_competing_answers", [])
    seen: set[str] = {a.strip().lower() for a in existing}
    added = 0
    for ans in new_competing:
        key = ans.strip().lower()
        if key and key not in seen:
            seen.add(key)
            existing.append(ans)
            added += 1

    if added:
        entry["altered_competing_answers"] = existing
        return True
    return False


# ---------------------------------------------------------------------------
# Main validation loop
# ---------------------------------------------------------------------------


def validate(args: argparse.Namespace) -> None:
    """Run the validation pipeline according to parsed CLI *args*."""
    load_dotenv()

    generated_dir = Path(args.generated_dir)
    generated_dir.mkdir(parents=True, exist_ok=True)

    if args.re_validate:
        revalidate_entries(args)
        return

    if args.promote_from_validated:
        promote_from_validated(args, generated_dir)
        return

    provider = args.provider
    model, api_key = resolve_provider(provider, args.model)

    if args.input:
        input_paths = [Path(args.input)]
    else:
        input_paths = sorted(generated_dir.glob("raw_*.jsonl"))
        if not input_paths:
            logger.warning(
                "No raw_*.jsonl files found in %s — nothing to validate.",
                generated_dir,
            )
            return

    already_validated: set[tuple[str, str]] = set()
    for vpath in sorted(generated_dir.glob("validated_*.jsonl")):
        for entry in load_jsonl(str(vpath)):
            key = _entry_key(entry)
            if key:
                already_validated.add(key)
    logger.info("Already-validated entries loaded: %d", len(already_validated))

    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if args.output is not None:
        output_path = Path(args.output.replace("{timestamp}", ts))
    else:
        today_files = sorted(generated_dir.glob(f"validated_{today_str}*.jsonl"))
        if today_files:
            output_path = today_files[-1]
            logger.info("Appending to existing today's file: %s", output_path)
        else:
            output_path = generated_dir / f"validated_{ts}.jsonl"
            logger.info("Creating new output file: %s", output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_raw_entries: list[dict[str, Any]] = []
    for ipath in input_paths:
        batch = load_jsonl(str(ipath))
        all_raw_entries.extend(batch)
        logger.info("Loaded %d entries from %s", len(batch), ipath)

    template = load_template(args.prompt_template)

    seen_in_batch: set[tuple[str, str]] = set()
    entries_to_validate: list[dict[str, Any]] = []
    skipped_count = 0

    for entry in all_raw_entries:
        key = _entry_key(entry)
        if key is None:
            entries_to_validate.append(entry)
            continue
        if key in already_validated or key in seen_in_batch:
            skipped_count += 1
            logger.debug(
                "Skipping already-validated / duplicate entry id=%s",
                entry.get("id", "?"),
            )
            continue
        seen_in_batch.add(key)
        entries_to_validate.append(entry)

    if skipped_count:
        logger.info(
            "Skipped %d already-validated / duplicate-within-batch entries.",
            skipped_count,
        )

    if not entries_to_validate:
        logger.info(
            "No new entries to validate — all %d entries already processed. Exiting.",
            len(all_raw_entries),
        )
        return

    entries = entries_to_validate

    batch_size = args.batch_size
    use_batching = batch_size > 1
    max_output_tokens: int | None = args.max_output_tokens

    logger.info("Provider : %s", provider)
    logger.info("Model    : %s", model)
    logger.info(
        "Input    : %s (%d file(s), %d new entries)",
        ", ".join(str(p) for p in input_paths),
        len(input_paths),
        len(entries),
    )
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
    promotion_state = init_promotion_state(args)

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
            for chunk_start in range(0, len(entry_prompts), batch_size):
                chunk = entry_prompts[chunk_start : chunk_start + batch_size]
                prompts_only = [p for _, p in chunk]

                logger.info(
                    "Dispatching batch %d–%d / %d …",
                    chunk_start + 1,
                    chunk_start + len(chunk),
                    len(entry_prompts),
                )

                raw_results = call_llm_batched(
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

                    raw_text = raw.text

                    try:
                        validation = parse_validation_response(raw_text)
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.error(
                            "  Unparseable validation response for entry %s: %s — skipping.",
                            entry.get("id"),
                            exc,
                        )
                        logger.debug("  Raw response:\n%s", raw_text[:500])
                        continue

                    for field in VALIDATION_FIELDS:
                        if field in validation:
                            entry[field] = validation[field]

                    passed = bool(validation.get("overall_valid", False))
                    if passed:
                        total_passed += 1
                    else:
                        total_failed += 1
                    total_validated += 1

                    write_jsonl_entry(out_fh, entry)
                    out_fh.flush()
                    promote_entry(entry, promotion_state)

                    logger.info(
                        "    → %s (answer_valid=%s, is_distinct=%s, overall_valid=%s)",
                        "PASS" if passed else "FAIL",
                        validation.get("answer_valid"),
                        validation.get("is_distinct"),
                        validation.get("overall_valid"),
                    )

        else:
            for idx, (entry, prompt_text) in enumerate(entry_prompts, start=1):
                logger.info(
                    "Validating %d/%d — id=%s",
                    idx,
                    len(entry_prompts),
                    entry.get("id", "?"),
                )

                try:
                    response = call_llm(
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

                raw_text = response.text

                try:
                    validation = parse_validation_response(raw_text)
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.error(
                        "Unparseable validation response for entry %s: %s — skipping.",
                        entry.get("id"),
                        exc,
                    )
                    logger.debug("Raw response:\n%s", raw_text[:500])
                    continue

                for field in VALIDATION_FIELDS:
                    if field in validation:
                        entry[field] = validation[field]

                passed = bool(validation.get("overall_valid", False))
                if passed:
                    total_passed += 1
                else:
                    total_failed += 1
                total_validated += 1

                write_jsonl_entry(out_fh, entry)
                out_fh.flush()
                promote_entry(entry, promotion_state)

                logger.info(
                    "  → %s (answer_valid=%s, is_distinct=%s, overall_valid=%s)",
                    "PASS" if passed else "FAIL",
                    validation.get("answer_valid"),
                    validation.get("is_distinct"),
                    validation.get("overall_valid"),
                )

                if idx < len(entry_prompts) and args.delay > 0:
                    time.sleep(args.delay)

    logger.info("=" * 60)
    logger.info(
        "Done. Validated %d entries: %d passed, %d failed.",
        total_validated,
        total_passed,
        total_failed,
    )
    if args.append_to_benchmark:
        logger.info(
            "Benchmark promotion: appended %d, skipped %d already present.",
            promotion_state["benchmark_appended"],
            promotion_state["benchmark_skipped"],
        )
    if args.append_to_pool:
        logger.info(
            "Pool promotion: appended %d, skipped %d already present.",
            promotion_state["pool_appended"],
            promotion_state["pool_skipped"],
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
        choices=provider_names(),
        default="gemini",
        help="LLM provider to use (default: gemini)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: per-provider default from config)",
    )
    parser.add_argument(
        "--generated-dir",
        default="data/generated",
        help=(
            "Directory containing raw_*.jsonl and validated_*.jsonl files "
            "(default: data/generated). Used for auto-discovery of input files "
            "when --input is omitted and for auto-detecting today's output file."
        ),
    )
    parser.add_argument(
        "--input",
        default=None,
        help=(
            "Input JSONL path. In normal mode this overrides auto-discovery of "
            "raw_*.jsonl inside --generated-dir. In --promote-from-validated "
            "mode, this should point to a validated JSONL file."
        ),
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Output JSONL path. {timestamp} is replaced at runtime. "
            "If omitted, today's validated_{YYYYMMDD}*.jsonl file in "
            "--generated-dir is used when one exists; otherwise a new "
            "validated_{YYYYMMDD_HHMMSS}.jsonl is created there."
        ),
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
        help=(
            "Append passing entries to data/benchmark.jsonl immediately as they "
            "are validated; also used by --promote-from-validated."
        ),
    )
    parser.add_argument(
        "--append-to-pool",
        action="store_true",
        default=False,
        help=(
            "Append passing entries to the riddle pool immediately as they are "
            "validated; also used by --promote-from-validated."
        ),
    )
    parser.add_argument(
        "--promote-from-validated",
        action="store_true",
        default=False,
        help=(
            "Skip LLM validation and promote already-validated passing entries "
            "from validated JSONL file(s) into the benchmark and/or pool. Uses "
            "--input if provided; otherwise scans validated_*.jsonl in "
            "--generated-dir."
        ),
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="Sampling temperature (default: 1.0)",
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
    parser.add_argument(
        "--re-validate",
        action="store_true",
        default=False,
        help=(
            "Re-validate existing benchmark or pool entries. Requires --input. "
            "Runs each entry through the validation LLM again and merges any "
            "newly discovered competing answers. Creates a backup before "
            "modifying the file."
        ),
    )
    parser.add_argument(
        "--filter-empty-competing",
        action="store_true",
        default=False,
        help=(
            "When used with --re-validate, only re-validate entries whose "
            "altered_competing_answers field is empty or missing."
        ),
    )
    return parser


if __name__ == "__main__":
    validate(build_parser().parse_args())
