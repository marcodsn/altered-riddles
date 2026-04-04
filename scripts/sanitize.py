#!/usr/bin/env python3
"""sanitize.py — Sanitize pool entries that embed parenthetical alternatives in altered_answer.

Finds entries where ``altered_answer`` contains parenthetical content such as:

  * ``"Encryption (or an encryption key)."``
  * ``"A die (or dice)."``
  * ``"A scent (or perfume/fragrance)."``
  * ``"A playing card (specifically a King, Queen, or Jack)."``

For each such entry the script:

1. Extracts the primary/canonical answer (text before the opening parenthesis).
2. Extracts the alternatives listed inside the parentheses.
3. Sets ``altered_answer`` to the clean primary answer.
4. Adds the alternatives to ``altered_accepted_answers`` (deduplicating, case-insensitive).

Usage examples::

    python -m scripts.sanitize
    python -m scripts.sanitize --input data/pool.jsonl
    python -m scripts.sanitize --input data/pool.jsonl --dry-run
    python -m scripts.sanitize --no-backup
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.core.io_utils import load_jsonl, write_jsonl

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("sanitize")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Matches:  "Main text (parenthetical content)."
#       or  "Main text (parenthetical content)"   (no trailing period)
_PAREN_RE = re.compile(r"^(.*?)\s*\((.+?)\)\.?\s*$", re.DOTALL)


def _parse_paren_content(paren_text: str) -> list[str]:
    """Return a list of alternative answers extracted from *paren_text*.

    Handles the three real-world patterns found in the pool:

    ``"or X"``
        Single alternative → ``["X"]``

    ``"or X/Y"``
        Slash-separated alternatives → ``["X", "Y"]``

    ``"specifically A, B, or C"``
        Comma/or-separated clarifications → ``["A", "B", "C"]``

    Any other prefix is treated as a single alternative (``[paren_text]``).
    """
    text = paren_text.strip()
    lower = text.lower()

    if lower.startswith("or "):
        rest = text[3:].strip()
        parts = [p.strip() for p in rest.split("/")]
        return [p for p in parts if p]

    if lower.startswith("specifically "):
        rest = text[13:].strip()
        # Split on " or " first, then on ", " to handle "A, B, or C"
        or_parts = re.split(r"\s+or\s+", rest)
        parts: list[str] = []
        for segment in or_parts:
            parts.extend(s.strip() for s in segment.split(","))
        return [p for p in parts if p]

    # Unknown prefix — treat the whole content as a single alternative.
    return [text]


def extract_answer_parts(altered_answer: str) -> tuple[str, list[str]] | None:
    """Split a parenthetical altered answer into ``(primary, [alternatives])``.

    Returns ``None`` if *altered_answer* contains no parseable parenthetical
    section.  The returned *primary* preserves a trailing period when the
    original string ended with one.
    """
    m = _PAREN_RE.match(altered_answer.strip())
    if not m:
        return None

    primary = m.group(1).strip()
    paren_content = m.group(2).strip()

    if altered_answer.rstrip().endswith(".") and not primary.endswith("."):
        primary += "."

    alternatives = _parse_paren_content(paren_content)
    return primary, alternatives


# ---------------------------------------------------------------------------
# Entry-level sanitisation
# ---------------------------------------------------------------------------


def sanitize_entry(entry: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Sanitise one pool entry.

    Returns ``(updated_entry, was_changed)``.  The original *entry* dict is
    never mutated.
    """
    raw_answer = entry.get("altered_answer", "")
    result = extract_answer_parts(raw_answer)
    if result is None:
        return entry, False

    primary, alternatives = result

    # Build a deduped accepted-answers list:
    #   1. primary answer (always first)
    #   2. any pre-existing accepted answers that are not the now-stale
    #      combined string
    #   3. extracted alternatives
    existing = list(entry.get("altered_accepted_answers", []))
    new_accepted: list[str] = [primary]

    for ans in existing:
        if ans == raw_answer:
            continue  # drop the old combined string
        if not any(a.lower() == ans.lower() for a in new_accepted):
            new_accepted.append(ans)

    for alt in alternatives:
        if not any(a.lower() == alt.lower() for a in new_accepted):
            new_accepted.append(alt)

    updated = {
        **entry,
        "altered_answer": primary,
        "altered_accepted_answers": new_accepted,
    }
    return updated, True


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def sanitize(args: argparse.Namespace) -> None:
    """Run the sanitisation pipeline according to parsed CLI *args*."""
    input_path = Path(args.input)
    entries = load_jsonl(input_path)
    logger.info("Loaded %d entries from %s", len(entries), input_path)

    changed_count = 0
    sanitized: list[dict[str, Any]] = []

    for entry in entries:
        updated, changed = sanitize_entry(entry)
        sanitized.append(updated)
        if changed:
            changed_count += 1
            n_added = len(updated["altered_accepted_answers"]) - 1
            logger.info(
                "  %s | '%s'  →  '%s'  (+%d alt(s): %s)",
                entry.get("id", "?"),
                entry.get("altered_answer", ""),
                updated["altered_answer"],
                n_added,
                ", ".join(repr(a) for a in updated["altered_accepted_answers"][1:]),
            )

    logger.info("=" * 60)
    logger.info("Entries scanned  : %d", len(entries))
    logger.info("Entries modified : %d", changed_count)

    if args.dry_run:
        logger.info("Dry run — no changes written to disk.")
        return

    if not args.no_backup and changed_count > 0:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_dir = input_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"{input_path.stem}_{ts}{input_path.suffix}"
        shutil.copy2(input_path, backup_path)
        logger.info("Backup written to %s", backup_path)

    write_jsonl(input_path, sanitized)
    logger.info("Sanitised file written to %s", input_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Sanitise pool JSONL entries that have parenthetical alternatives "
            "embedded in altered_answer, splitting them into separate "
            "altered_accepted_answers entries."
        ),
    )
    parser.add_argument(
        "--input",
        default="data/pool.jsonl",
        help="Path to pool JSONL file (default: data/pool.jsonl)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report what would change without modifying the file.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        default=False,
        help="Skip creating a timestamped backup before overwriting the file.",
    )
    return parser


if __name__ == "__main__":
    sanitize(build_parser().parse_args())
