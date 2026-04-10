"""Tests for scripts.core.io_utils helpers."""

from __future__ import annotations

import json

from scripts.core.io_utils import (
    get_max_benchmark_id,
    load_jsonl,
    sanitize_model_name,
    strip_markdown_fences,
    write_jsonl,
)

# ---------------------------------------------------------------------------
# strip_markdown_fences
# ---------------------------------------------------------------------------


def test_strip_markdown_fences_json_block():
    raw = '```json\n{"key": "value"}\n```'
    assert strip_markdown_fences(raw) == '{"key": "value"}'


def test_strip_markdown_fences_plain_block():
    raw = "```\nhello world\n```"
    assert strip_markdown_fences(raw) == "hello world"


def test_strip_markdown_fences_no_fences():
    raw = '{"already": "clean"}'
    assert strip_markdown_fences(raw) == '{"already": "clean"}'


def test_strip_markdown_fences_with_surrounding_whitespace():
    raw = "  \n```json\n[1, 2, 3]\n```\n  "
    assert strip_markdown_fences(raw) == "[1, 2, 3]"


# ---------------------------------------------------------------------------
# sanitize_model_name
# ---------------------------------------------------------------------------


def test_sanitize_model_name_with_slashes():
    assert sanitize_model_name("openai/gpt-4o") == "openai_gpt-4o"


def test_sanitize_model_name_with_colons():
    assert sanitize_model_name("meta:llama-3:70b") == "meta_llama-3_70b"


def test_sanitize_model_name_with_backslash():
    assert sanitize_model_name("org\\model") == "org_model"


def test_sanitize_model_name_already_clean():
    assert sanitize_model_name("gpt-4o-mini") == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# get_max_benchmark_id
# ---------------------------------------------------------------------------


def test_get_max_benchmark_id_with_entries(tmp_path):
    f = tmp_path / "benchmark.jsonl"
    entries = [
        {"id": "alt_001", "text": "first"},
        {"id": "alt_015", "text": "middle"},
        {"id": "alt_007", "text": "last"},
    ]
    with open(f, "w") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")

    assert get_max_benchmark_id(f) == 15


def test_get_max_benchmark_id_empty_file(tmp_path):
    f = tmp_path / "benchmark.jsonl"
    f.write_text("")
    assert get_max_benchmark_id(f) == 0


def test_get_max_benchmark_id_missing_file(tmp_path):
    f = tmp_path / "nonexistent.jsonl"
    assert get_max_benchmark_id(f) == 0


# ---------------------------------------------------------------------------
# load_jsonl / write_jsonl roundtrip
# ---------------------------------------------------------------------------


def test_jsonl_roundtrip(tmp_path):
    f = tmp_path / "data.jsonl"
    original = [
        {"id": "alt_001", "answer": "candle"},
        {"id": "alt_002", "answer": "shadow"},
        {"id": "alt_003", "answer": "echo", "extra": ["a", "b"]},
    ]

    write_jsonl(f, original)
    loaded = load_jsonl(f)

    assert loaded == original


def test_load_jsonl_skips_blank_lines(tmp_path):
    f = tmp_path / "data.jsonl"
    content = '{"id": 1}\n\n{"id": 2}\n\n'
    f.write_text(content)

    loaded = load_jsonl(f)
    assert len(loaded) == 2
    assert loaded[0]["id"] == 1
    assert loaded[1]["id"] == 2


def test_load_jsonl_skips_malformed_lines(tmp_path):
    f = tmp_path / "data.jsonl"
    content = '{"id": 1}\nNOT JSON\n{"id": 2}\n'
    f.write_text(content)

    loaded = load_jsonl(f)
    assert len(loaded) == 2
