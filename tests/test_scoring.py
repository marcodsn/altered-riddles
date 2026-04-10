"""Tests for the scoring logic in scripts/evaluate.py."""

import pytest

from scripts.evaluate import (
    COMPETING_ANSWER_WEIGHT,
    _score_single_output,
    extract_accepted_answers,
    extract_competing_answers,
    extract_original_answers,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_ENTRY = {
    "id": "alt_001",
    "original_riddle": "test original",
    "original_answer": "candle",
    "original_accepted_answers": ["candle"],
    "original_reasoning": "wax melts",
    "altered_riddle": "test altered",
    "altered_answer": "plant",
    "altered_accepted_answers": ["plant", "tree"],
    "altered_competing_answers": ["flower"],
    "altered_reasoning": "test",
    "source": "test",
    "type": "constraint_addition",
}


def _make_output(riddle_type="altered", model_answer="plant", sample_index=1):
    return {
        "riddle_id": "alt_001",
        "riddle_type": riddle_type,
        "model_answer": model_answer,
        "riddle_text": "test riddle text",
        "sample_index": sample_index,
    }


# ---------------------------------------------------------------------------
# _score_single_output — altered riddle tests
# ---------------------------------------------------------------------------


class TestScoreSingleOutputAltered:
    """Tests for _score_single_output with riddle_type='altered'."""

    def test_correct_answer_scores_1(self):
        output = _make_output(model_answer="plant")
        judgment = {"correct": True, "gave_original": False, "competing": False}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment)

        assert result is not None
        assert result["correct"] is True
        assert result["score"] == 1.0

    def test_competing_answer_scores_half(self):
        output = _make_output(model_answer="flower")
        judgment = {"correct": False, "gave_original": False, "competing": True}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment)

        assert result is not None
        assert result["correct"] is False
        assert result["score"] == COMPETING_ANSWER_WEIGHT
        assert result["competing_match"] is True

    def test_original_answer_scores_0(self):
        output = _make_output(model_answer="candle")
        judgment = {"correct": False, "gave_original": True, "competing": False}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment)

        assert result is not None
        assert result["correct"] is False
        assert result["gave_original_answer"] is True
        assert result["score"] == 0.0

    def test_competing_but_gave_original_scores_0(self):
        """If judge says both competing and gave_original, score should be 0."""
        output = _make_output(model_answer="candle")
        judgment = {"correct": False, "gave_original": True, "competing": True}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment)

        assert result is not None
        assert result["score"] == 0.0

    def test_wrong_answer_scores_0(self):
        output = _make_output(model_answer="banana")
        judgment = {"correct": False, "gave_original": False, "competing": False}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment)

        assert result is not None
        assert result["correct"] is False
        assert result["score"] == 0.0

    def test_custom_competing_weight(self):
        output = _make_output(model_answer="flower")
        judgment = {"correct": False, "gave_original": False, "competing": True}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment, competing_weight=0.25)

        assert result is not None
        assert result["score"] == 0.25

    def test_none_benchmark_entry_returns_none(self):
        output = _make_output(model_answer="plant")
        judgment = {"correct": True}

        result = _score_single_output(output, None, judgment)

        assert result is None

    def test_detail_fields_populated(self):
        output = _make_output(model_answer="plant", sample_index=3)
        judgment = {"correct": True, "gave_original": False, "competing": False}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment)

        assert result["riddle_id"] == "alt_001"
        assert result["riddle_type"] == "altered"
        assert result["model_answer"] == "plant"
        assert result["accepted_answers"] == ["plant", "tree"]
        assert result["sample_index"] == 3


# ---------------------------------------------------------------------------
# _score_single_output — original riddle tests
# ---------------------------------------------------------------------------


class TestScoreSingleOutputOriginal:
    """Tests for _score_single_output with riddle_type='original'."""

    def test_correct_original_has_no_score_field(self):
        """Original riddles don't get a numeric score — only 'correct'."""
        output = _make_output(riddle_type="original", model_answer="candle")
        judgment = {"correct": True}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment)

        assert result is not None
        assert result["correct"] is True
        # Original riddle type doesn't go through the altered scoring branch
        assert "score" not in result

    def test_incorrect_original(self):
        output = _make_output(riddle_type="original", model_answer="wrong")
        judgment = {"correct": False}

        result = _score_single_output(output, SAMPLE_ENTRY, judgment)

        assert result is not None
        assert result["correct"] is False


# ---------------------------------------------------------------------------
# Helper extraction functions
# ---------------------------------------------------------------------------


class TestExtractFunctions:
    def test_extract_accepted_answers_altered(self):
        answers = extract_accepted_answers(SAMPLE_ENTRY, "altered")
        assert answers == ["plant", "tree"]

    def test_extract_accepted_answers_original(self):
        answers = extract_accepted_answers(SAMPLE_ENTRY, "original")
        assert answers == ["candle"]

    def test_extract_accepted_answers_fallback(self):
        entry = {"altered_answer": "solo", "original_answer": "only"}
        assert extract_accepted_answers(entry, "altered") == ["solo"]
        assert extract_accepted_answers(entry, "original") == ["only"]

    def test_extract_original_answers(self):
        assert extract_original_answers(SAMPLE_ENTRY) == ["candle"]

    def test_extract_competing_answers(self):
        assert extract_competing_answers(SAMPLE_ENTRY) == ["flower"]

    def test_extract_competing_answers_missing(self):
        assert extract_competing_answers({}) == []
