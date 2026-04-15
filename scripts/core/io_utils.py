"""io_utils.py — Shared I/O helpers for the Altered Riddles benchmark."""

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
    """Read a JSONL file. Skips blank/malformed lines."""
    filepath = Path(path)
    if not filepath.exists():
        logger.error("File not found: %s", filepath)
        raise SystemExit(1)
    entries: list[dict[str, Any]] = []
    with open(filepath, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Skipping bad JSON line %d in %s: %s", lineno, filepath, exc)
    return entries


def load_jsonl_if_exists(path: str | Path) -> list[dict[str, Any]]:
    """Like load_jsonl but returns [] if file doesn't exist."""
    if not Path(path).exists():
        return []
    return load_jsonl(path)


def write_jsonl(path: str | Path, entries: list[dict[str, Any]]) -> None:
    """Overwrite a JSONL file with entries."""
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    """Append a single JSON record to a JSONL file."""
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── JSON ──────────────────────────────────────────────────────────────


def write_json(path: str | Path, data: Any, indent: int = 2) -> None:
    """Write data as pretty-printed JSON."""
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)
        fh.write("\n")


# ── Jinja2 ────────────────────────────────────────────────────────────


def load_template(template_path: str | Path) -> jinja2.Template:
    """Load and compile a Jinja2 template."""
    tpl_path = Path(template_path)
    if not tpl_path.exists():
        logger.error("Template not found: %s", tpl_path)
        raise SystemExit(1)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(tpl_path.parent)),
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    return env.get_template(tpl_path.name)


# ── CSV ───────────────────────────────────────────────────────────────


def load_source_riddles(path: str | Path) -> list[dict[str, str]]:
    """Load riddles from CSV with riddles,answers columns.
    Splits on the last comma (riddle text may contain commas).
    """
    filepath = Path(path)
    if not filepath.exists():
        logger.warning("Source CSV %s not found.", path)
        return []
    entries: list[dict[str, str]] = []
    with open(filepath, encoding="utf-8") as fh:
        _header = fh.readline()
        for line in fh:
            line = line.strip()
            if not line:
                continue
            last_comma = line.rfind(",")
            if last_comma == -1:
                continue
            riddle = line[:last_comma].strip()
            answer = line[last_comma + 1 :].strip()
            if riddle and answer:
                entries.append({"riddle": riddle, "answer": answer})
    return entries


# ── Text helpers ──────────────────────────────────────────────────────


def sanitize_model_name(name: str) -> str:
    """Make a model name safe for filenames."""
    return re.sub(r"[/\\:]", "_", name)


def strip_markdown_fences(text: str) -> str:
    """Remove optional ```json ... ``` fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()
