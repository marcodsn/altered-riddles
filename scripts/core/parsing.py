"""parsing.py — Consolidated parsing helpers for the Altered Riddles pipeline.

Centralises duplicated parsing, validation, and format-conversion functions
that were previously copy-pasted across ``generate.py``, ``generate_all.py``,
``validate.py``, and ``sanitize.py``.

Public API
----------
- ``REQUIRED_FIELDS``
- ``parse_riddle_array(raw_text)``
- ``validate_entry(entry)``
- ``parse_validation_response(raw_text)``
- ``split_paren_alternatives(text)``
- ``to_benchmark_format(entry, new_id)``
"""

from __future__ import annotations

import json
import re
from typing import Any

from scripts.core.io_utils import strip_markdown_fences

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: set[str] = {
    "original_riddle",
    "original_answer",
    "original_reasoning",
    "altered_riddle",
    "altered_answer",
    "altered_reasoning",
    "type",
}

# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------


def parse_riddle_array(raw_text: str) -> list[dict[str, Any]]:
    """Parse the LLM response text into a list of riddle-pair dicts.

    The response may be a JSON array directly or a JSON object wrapping one
    (e.g. ``{"riddles": [...]}``)  — we handle both.
    """
    text = strip_markdown_fences(raw_text)

    parsed = json.loads(text)

    if isinstance(parsed, list):
        return parsed

    # If the model wrapped the array in an object, grab the first list value.
    if isinstance(parsed, dict):
        for value in parsed.values():
            if isinstance(value, list):
                return value

    raise ValueError(f"Unexpected JSON structure: {type(parsed)}")


def parse_validation_response(raw_text: str) -> dict[str, Any]:
    """Parse the LLM validation response into a dict.

    The response should be a single JSON object.  We handle minor quirks like
    wrapping markdown fences.
    """
    text = strip_markdown_fences(raw_text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError(f"Expected a JSON object, got {type(parsed)}")
    return parsed


# ---------------------------------------------------------------------------
# Entry validation
# ---------------------------------------------------------------------------


def validate_entry(entry: dict[str, Any]) -> bool:
    """Return True if the entry has all required fields with non-empty values."""
    return all(entry.get(f) for f in REQUIRED_FIELDS)


# ---------------------------------------------------------------------------
# Parenthetical-answer splitting
# ---------------------------------------------------------------------------

_PAREN_RE = re.compile(r"^(.*?)\s*\((.+?)\)\.?\s*$", re.DOTALL)


def split_paren_alternatives(text: str) -> tuple[str, list[str]] | None:
    """Split ``"Answer (or alternative)."`` into ``("Answer.", ["alternative"])``.

    Returns ``None`` when *text* contains no parseable parenthetical section.
    Handles three patterns:

    * ``"or X"`` / ``"or X/Y"`` — slash-separated alternatives
    * ``"specifically A, B, or C"`` — comma/or-separated clarifications
    * Any other prefix — treated as a single alternative

    .. note::

       ``scripts/sanitize.py`` has its own ``extract_answer_parts`` function
       that uses the same underlying regex pattern but routes through a
       separate ``_parse_paren_content`` helper.  That copy is intentionally
       kept as-is because its interface differs (returns the same data but
       via a different internal path).
    """
    m = _PAREN_RE.match(text.strip())
    if not m:
        return None
    primary = m.group(1).strip()
    paren = m.group(2).strip()
    if text.rstrip().endswith(".") and not primary.endswith("."):
        primary += "."
    lower = paren.lower()
    if lower.startswith("or "):
        parts = [p.strip() for p in paren[3:].split("/")]
        return primary, [p for p in parts if p]
    if lower.startswith("specifically "):
        rest = paren[13:].strip()
        or_parts = re.split(r"\s+or\s+", rest)
        parts: list[str] = []
        for segment in or_parts:
            parts.extend(s.strip() for s in segment.split(","))
        return primary, [p for p in parts if p]
    return primary, [paren]


# Keep the underscore-prefixed name available as an alias so that any
# internal callers that referenced the old private name still work.
_split_paren_alternatives = split_paren_alternatives


# ---------------------------------------------------------------------------
# Benchmark format conversion
# ---------------------------------------------------------------------------


def to_benchmark_format(entry: dict[str, Any], new_id: str) -> dict[str, Any]:
    """Convert a validated generation entry to the benchmark JSONL format.

    This is the *complete* implementation (originally from ``validate.py``)
    that handles parenthetical splitting of ``altered_answer`` and merges
    the validator LLM's ``altered_accepted_answers`` list.
    """
    original_answer_lower = entry.get("original_answer", "").strip().lower()

    # ── Clean up altered_answer ────────────────────────────────────────
    # Split out any parenthetical alternatives baked into the raw answer
    # (e.g. "Encryption (or an encryption key)." from the generation LLM).
    raw_answer = entry.get("altered_answer", "")
    paren_result = split_paren_alternatives(raw_answer)
    if paren_result is not None:
        primary_answer, paren_alts = paren_result
    else:
        primary_answer, paren_alts = raw_answer, []

    # ── Build accepted-answers list ────────────────────────────────────
    # Prefer the validator LLM's explicit list; fall back to paren-split.
    llm_accepted: list[str] | None = entry.get("altered_accepted_answers")
    if llm_accepted and isinstance(llm_accepted, list):
        seen: set[str] = set()
        accepted: list[str] = []
        for ans in [primary_answer, *llm_accepted]:
            key = ans.strip().lower()
            if key and key not in seen:
                seen.add(key)
                accepted.append(ans)
    else:
        seen = set()
        accepted = []
        for ans in [primary_answer, *paren_alts]:
            key = ans.strip().lower()
            if key and key not in seen:
                seen.add(key)
                accepted.append(ans)

    competing = [
        a
        for a in entry.get("competing_answers", [])
        if a.strip().lower() != original_answer_lower
    ]

    return {
        "id": new_id,
        "original_riddle": entry.get("original_riddle", ""),
        "original_answer": entry.get("original_answer", ""),
        "original_accepted_answers": [entry.get("original_answer", "")],
        "original_reasoning": entry.get("original_reasoning", ""),
        "altered_riddle": entry.get("altered_riddle", ""),
        "altered_answer": primary_answer,
        "altered_accepted_answers": accepted,
        "altered_competing_answers": competing,
        "altered_reasoning": entry.get("altered_reasoning", ""),
        "source": entry.get("source", ""),
        "type": entry.get("type", "constraint_addition"),
    }
