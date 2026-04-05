#!/usr/bin/env python3
"""clean_outputs.py — Remove duplicate original-riddle entries from model output files.

The benchmark contains many entries that share the same original_riddle text
(one original riddle can inspire multiple altered versions).  The benchmark
runner previously tested *every* benchmark entry's original riddle, leading to
the same original riddle being sent to a model N times (once per altered variant
that shares it).  This script strips those redundant records out of already-
computed output files, keeping only the **first** occurrence of each
(riddle_text, sample_index) pair among original-type records.

Altered-riddle records are untouched.

Usage examples:
    # Preview changes without modifying files
    python -m scripts.clean_outputs --dry-run

    # Clean all files in the default version directory
    python -m scripts.clean_outputs

    # Clean a specific file
    python -m scripts.clean_outputs --file data/model_outputs/2604/some_model.jsonl

    # Clean all files under a custom output dir (non-versioned)
    python -m scripts.clean_outputs --output-dir data/model_outputs/2604

    # Skip writing backups
    python -m scripts.clean_outputs --no-backup
"""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from scripts.core.config import DEFAULT_MODEL_OUTPUTS, get_benchmark_version
from scripts.core.io_utils import load_jsonl, write_jsonl

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
# Core cleaning logic
# ---------------------------------------------------------------------------


def clean_records(records: list[dict]) -> tuple[list[dict], int]:
    """Return a deduplicated copy of *records* and the number of dropped rows.

    Rules
    -----
    * ``riddle_type == "original"``: keep the first record for every
      ``(riddle_text, sample_index)`` pair; drop subsequent duplicates.
    * ``riddle_type == "altered"`` (or anything else): always keep.

    Parameters
    ----------
    records:
        Raw records as loaded from a model-output JSONL file.

    Returns
    -------
    (cleaned_records, num_dropped)
    """
    seen_original_keys: set[tuple[str, int]] = set()
    cleaned: list[dict] = []
    dropped = 0

    for record in records:
        rtype = record.get("riddle_type", "")
        if rtype != "original":
            # Altered (and any unknown) records are always kept.
            cleaned.append(record)
            continue

        riddle_text: str = record.get("riddle_text", "")
        sample_index: int = int(record.get("sample_index", 1))
        key = (riddle_text, sample_index)

        if key in seen_original_keys:
            dropped += 1
        else:
            seen_original_keys.add(key)
            cleaned.append(record)

    return cleaned, dropped


def clean_file(
    path: Path,
    *,
    dry_run: bool = False,
    backup: bool = True,
) -> tuple[int, int]:
    """Clean a single model-output JSONL file in-place.

    Parameters
    ----------
    path:
        Path to the ``.jsonl`` file to clean.
    dry_run:
        If *True*, report what would happen but do not modify any files.
    backup:
        If *True* (and not dry-run), write a ``.bak`` copy alongside the
        original before overwriting it.

    Returns
    -------
    ``(original_count, dropped_count)`` — the number of records before
    cleaning and the number that were removed.
    """
    records = load_jsonl(path)
    original_count = len(records)

    cleaned, dropped = clean_records(records)

    if dropped == 0:
        logger.info(
            "  %s — no duplicates found (%d records)", path.name, original_count
        )
        return original_count, 0

    orig_pct = dropped / original_count * 100 if original_count else 0.0
    logger.info(
        "  %s — %d → %d records (removed %d duplicates, %.1f%%)",
        path.name,
        original_count,
        len(cleaned),
        dropped,
        orig_pct,
    )

    if dry_run:
        # Report per-riddle type counts for clarity.
        orig_kept = sum(1 for r in cleaned if r.get("riddle_type") == "original")
        alt_kept = sum(1 for r in cleaned if r.get("riddle_type") == "altered")
        logger.info(
            "    [dry-run] would keep %d original + %d altered = %d records",
            orig_kept,
            alt_kept,
            len(cleaned),
        )
        return original_count, dropped

    # --- Write backup if requested ----------------------------------------
    if backup:
        backup_path = path.with_suffix(".jsonl.bak")
        shutil.copy2(path, backup_path)
        logger.info("    Backup written to %s", backup_path.name)

    # --- Overwrite with cleaned data --------------------------------------
    write_jsonl(path, cleaned)
    logger.info("    Cleaned file written to %s", path.name)

    return original_count, dropped


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_clean(args: argparse.Namespace) -> None:
    """Discover output files and clean them according to *args*."""
    dry_run: bool = args.dry_run
    backup: bool = not args.no_backup

    if dry_run:
        logger.info("DRY RUN — no files will be modified.")

    # --- Collect files to process -----------------------------------------
    files_to_process: list[Path] = []

    if args.file:
        p = Path(args.file)
        if not p.is_file():
            logger.error("File not found: %s", p)
            raise SystemExit(1)
        files_to_process = [p]
    else:
        output_dir = Path(args.output_dir)
        if not output_dir.is_dir():
            logger.error("Output directory not found: %s", output_dir)
            raise SystemExit(1)
        files_to_process = sorted(output_dir.glob("*.jsonl"))
        if not files_to_process:
            logger.warning("No .jsonl files found in %s", output_dir)
            return

    logger.info(
        "Processing %d file(s) in %s …",
        len(files_to_process),
        files_to_process[0].parent if files_to_process else ".",
    )

    # --- Process each file ------------------------------------------------
    total_before = 0
    total_dropped = 0

    for path in files_to_process:
        before, dropped = clean_file(path, dry_run=dry_run, backup=backup)
        total_before += before
        total_dropped += dropped

    # --- Summary ----------------------------------------------------------
    logger.info("=" * 60)
    if dry_run:
        logger.info(
            "DRY RUN complete — would remove %d / %d records (%.1f%%)",
            total_dropped,
            total_before,
            total_dropped / total_before * 100 if total_before else 0.0,
        )
    else:
        logger.info(
            "Done — removed %d / %d records (%.1f%%)",
            total_dropped,
            total_before,
            total_dropped / total_before * 100 if total_before else 0.0,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    version = get_benchmark_version()
    default_dir = str(Path(DEFAULT_MODEL_OUTPUTS) / version)

    parser = argparse.ArgumentParser(
        description=(
            "Remove duplicate original-riddle entries from model output files. "
            "Only 'original' riddle_type records are deduplicated; "
            "'altered' records are always kept."
        ),
    )

    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--file",
        metavar="PATH",
        default=None,
        help="Clean a single model-output JSONL file instead of a directory.",
    )
    source_group.add_argument(
        "--output-dir",
        default=default_dir,
        metavar="DIR",
        help=f"Directory containing model output .jsonl files (default: {default_dir})",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report what would be removed without modifying any files.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        default=False,
        help="Skip writing .bak backup files before overwriting.",
    )

    return parser


if __name__ == "__main__":
    run_clean(build_parser().parse_args())
