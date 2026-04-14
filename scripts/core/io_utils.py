"""io_utils.py — Shared I/O helpers for the Altered Riddles benchmark.

Centralises JSONL reading/writing, Jinja2 template loading, and JSON
output so that every script uses the same robust implementations.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import jinja2

logger = logging.getLogger(__name__)


# ── JSONL ─────────────────────────────────────────────────────────────


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSONL file and return a list of dicts.

    Blank lines are silently skipped.  Malformed lines emit a warning
    and are skipped so that a single bad line never crashes the caller.
    """
    filepath = Path(path)
    if not filepath.exists():
        logger.error("File not found: %s", filepath)
        raise SystemExit(1)

    entries: list[dict[str, Any]] = []
    with open(filepath, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping malformed JSON on line %d in %s: %s",
                    lineno,
                    filepath,
                    exc,
                )
    return entries


def load_jsonl_if_exists(path: str | Path) -> list[dict[str, Any]]:
    """Like :func:`load_jsonl` but returns an empty list when *path*
    does not exist instead of raising ``SystemExit``.
    """
    filepath = Path(path)
    if not filepath.exists():
        return []
    return load_jsonl(filepath)


def write_jsonl(path: str | Path, entries: list[dict[str, Any]]) -> None:
    """Write *entries* to a JSONL file (overwrites any existing content)."""
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    """Append a single JSON record as one line to *path*."""
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_jsonl_entry(fh: Any, entry: dict[str, Any]) -> None:
    """Write a single JSON object as one line to an already-open file handle."""
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Plain JSON ────────────────────────────────────────────────────────


def write_json(path: str | Path, data: Any, indent: int = 2) -> None:
    """Write *data* as pretty-printed JSON to *path*."""
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)
        fh.write("\n")


# ── Jinja2 templates ─────────────────────────────────────────────────


def load_template(template_path: str | Path) -> jinja2.Template:
    """Load and compile a Jinja2 template from *template_path*.

    Uses ``StrictUndefined`` so missing variables cause immediate errors
    rather than silent empty strings.
    """
    tpl_path = Path(template_path)
    if not tpl_path.exists():
        logger.error("Template file not found: %s", tpl_path)
        raise SystemExit(1)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tpl_path.parent)),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    return env.get_template(tpl_path.name)


# ── CSV source loading ────────────────────────────────────────────────


def load_source_riddles_csv(path: str | Path) -> list[dict[str, str]]:
    """Load riddles from a CSV file with ``riddles,answers`` columns.

    The CSV is *not* properly quoted (riddle texts contain commas), so we
    split each line on the **last** comma — everything before it is the
    riddle, everything after is the answer.

    Returns a list of ``{"riddle": ..., "answer": ...}`` dicts.
    """
    filepath = Path(path)
    if not filepath.exists():
        logger.warning("Source CSV %s not found — returning empty list.", path)
        return []

    entries: list[dict[str, str]] = []
    with open(filepath, encoding="utf-8") as fh:
        _header = fh.readline()  # skip header row
        for line in fh:
            line = line.strip()
            if not line:
                continue
            last_comma = line.rfind(",")
            if last_comma == -1:
                logger.warning("Skipping malformed CSV line (no comma): %s", line[:80])
                continue
            riddle = line[:last_comma].strip()
            answer = line[last_comma + 1 :].strip()
            if riddle and answer:
                entries.append({"riddle": riddle, "answer": answer})
    return entries


# ── Text helpers ──────────────────────────────────────────────────────


def sanitize_model_name(name: str) -> str:
    """Make a model name safe for use as a filename component."""
    return re.sub(r"[/\\:]", "_", name)


def strip_markdown_fences(text: str) -> str:
    """Remove optional markdown code fences (```json ... ```) from *text*."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def get_max_benchmark_id(benchmark_path: str | Path) -> int:
    """Return the maximum numeric ID (from ``alt_NNN``) in *benchmark_path*.

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


def get_max_pool_id(pool_path: str | Path) -> int:
    """Return the maximum numeric ID (from ``pool_NNNN``) in *pool_path*.

    Returns 0 if the file does not exist or is empty.
    """
    filepath = Path(pool_path)
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
            match = re.match(r"pool_(\d+)", entry_id)
            if match:
                max_id = max(max_id, int(match.group(1)))
    return max_id
