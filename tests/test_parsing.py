"""Tests for scripts.core.parsing helpers."""

from __future__ import annotations

import json

import pytest

from scripts.core.parsing import (
    parse_riddle_array,
    split_paren_alternatives,
    to_benchmark_format,
    validate_entry,
)

# ── parse_riddle_array ────────────────────────────────────────────────


class TestParseRiddleArray:
    def test_valid_json_array(self):
        raw = json.dumps([{"riddle": "What has keys?"}, {"riddle": "What has legs?"}])
        result = parse_riddle_array(raw)
        assert len(result) == 2
        assert result[0]["riddle"] == "What has keys?"

    def test_json_wrapped_in_object(self):
        payload = {"riddles": [{"riddle": "A"}, {"riddle": "B"}]}
        raw = json.dumps(payload)
        result = parse_riddle_array(raw)
        assert len(result) == 2
        assert result[1]["riddle"] == "B"

    def test_markdown_fences_stripped(self):
        inner = json.dumps([{"riddle": "X"}])
        raw = f"```json\n{inner}\n```"
        result = parse_riddle_array(raw)
        assert len(result) == 1
        assert result[0]["riddle"] == "X"

    def test_invalid_json_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            parse_riddle_array("this is not json")

    def test_unexpected_structure_raises(self):
        # A plain string is valid JSON but not an array or dict-wrapping-array
        with pytest.raises(ValueError, match="Unexpected JSON structure"):
            parse_riddle_array('"just a string"')


# ── validate_entry ────────────────────────────────────────────────────


class TestValidateEntry:
    COMPLETE_ENTRY = {
        "original_riddle": "What melts in heat?",
        "original_answer": "ice",
        "original_reasoning": "Ice melts when heated.",
        "altered_riddle": "What melts in cold?",
        "altered_answer": "chocolate",
        "altered_reasoning": "Reverse scenario.",
        "type": "constraint_addition",
    }

    def test_complete_entry_is_valid(self):
        assert validate_entry(self.COMPLETE_ENTRY) is True

    def test_missing_field_is_invalid(self):
        incomplete = {k: v for k, v in self.COMPLETE_ENTRY.items() if k != "type"}
        assert validate_entry(incomplete) is False

    def test_empty_field_is_invalid(self):
        bad = {**self.COMPLETE_ENTRY, "altered_answer": ""}
        assert validate_entry(bad) is False


# ── split_paren_alternatives ─────────────────────────────────────────


class TestSplitParenAlternatives:
    def test_or_alternative(self):
        result = split_paren_alternatives("Answer (or alternative).")
        assert result is not None
        primary, alts = result
        assert primary == "Answer."
        assert alts == ["alternative"]

    def test_specifically_list(self):
        result = split_paren_alternatives("Answer (specifically A, B, or C).")
        assert result is not None
        primary, alts = result
        assert primary == "Answer."
        assert set(alts) == {"A", "B", "C"}

    def test_no_parenthetical_returns_none(self):
        result = split_paren_alternatives("Just a plain answer")
        assert result is None

    def test_or_with_slash_alternatives(self):
        result = split_paren_alternatives("Key (or lock/latch)")
        assert result is not None
        primary, alts = result
        assert "lock" in alts
        assert "latch" in alts

    def test_generic_parenthetical(self):
        result = split_paren_alternatives("Encryption (an encryption key).")
        assert result is not None
        primary, alts = result
        assert primary == "Encryption."
        assert alts == ["an encryption key"]


# ── to_benchmark_format ──────────────────────────────────────────────


class TestToBenchmarkFormat:
    GENERATION_ENTRY = {
        "original_riddle": "What has keys but no locks?",
        "original_answer": "A piano",
        "original_reasoning": "Pianos have keys.",
        "altered_riddle": "What has keys and locks?",
        "altered_answer": "A door",
        "altered_reasoning": "Doors have both.",
        "type": "constraint_addition",
        "source": "gpt-4o",
        "competing_answers": ["gate"],
    }

    def test_basic_conversion(self):
        result = to_benchmark_format(self.GENERATION_ENTRY, "alt_042")
        assert result["id"] == "alt_042"
        assert result["original_riddle"] == "What has keys but no locks?"
        assert result["original_answer"] == "A piano"
        assert result["altered_answer"] == "A door"
        assert result["type"] == "constraint_addition"
        assert result["source"] == "gpt-4o"

    def test_accepted_answers_include_primary(self):
        result = to_benchmark_format(self.GENERATION_ENTRY, "alt_001")
        assert "A door" in result["altered_accepted_answers"]

    def test_competing_answers_populated(self):
        result = to_benchmark_format(self.GENERATION_ENTRY, "alt_001")
        assert "gate" in result["altered_competing_answers"]

    def test_competing_answers_exclude_original(self):
        entry = {
            **self.GENERATION_ENTRY,
            "competing_answers": ["A piano", "gate"],
        }
        result = to_benchmark_format(entry, "alt_001")
        # "A piano" matches original_answer (case-insensitive) → excluded
        assert "gate" in result["altered_competing_answers"]
        assert not any(a.lower() == "a piano" for a in result["altered_competing_answers"])

    def test_parenthetical_splitting_in_altered_answer(self):
        entry = {
            **self.GENERATION_ENTRY,
            "altered_answer": "Encryption (or an encryption key).",
        }
        result = to_benchmark_format(entry, "alt_001")
        assert result["altered_answer"] == "Encryption."
        assert any("encryption key" in a for a in result["altered_accepted_answers"])
