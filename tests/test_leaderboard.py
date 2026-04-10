"""Tests for build_leaderboard() from scripts/evaluate.py."""

import math

from scripts.evaluate import build_leaderboard

# ---------------------------------------------------------------------------
# Helpers — build synthetic result dicts that match evaluate_model() output
# ---------------------------------------------------------------------------


def _make_result(
    model: str,
    altered_accuracy: float = 0.7,
    original_accuracy: float = 0.9,
    total_score: float = 0.65,
    pattern_override_rate: float = 0.1,
    conditioned_override_rate: float = 0.15,
    altered_num_riddles: int = 300,
    original_num_riddles: int = 300,
    provider: str = "openai",
    quantization: str = "",
) -> dict:
    """Return a minimal result dict shaped like evaluate_model() output."""
    return {
        "model": model,
        "provider": provider,
        "quantization": quantization,
        "summary": {
            "original_accuracy": original_accuracy,
            "altered_accuracy": altered_accuracy,
            "altered_weighted_accuracy": altered_accuracy + 0.02,
            "pattern_override_rate": pattern_override_rate,
            "conditioned_override_rate": conditioned_override_rate,
            "average_accuracy": total_score,
            "total_score": total_score,
            "total_input_tokens": 50000,
            "total_output_tokens": 20000,
            "original_input_tokens": 25000,
            "original_output_tokens": 10000,
            "altered_input_tokens": 25000,
            "altered_output_tokens": 10000,
            "original_num_riddles": original_num_riddles,
            "altered_num_riddles": altered_num_riddles,
            "per_type": {},
            "per_source": {},
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_models_below_250_filtered_out():
    """Models with fewer than 250 altered riddles should be excluded."""
    results = [
        _make_result("big-model", altered_num_riddles=300, total_score=0.8),
        _make_result("small-model", altered_num_riddles=100, total_score=0.9),
        _make_result("medium-model", altered_num_riddles=249, total_score=0.85),
        _make_result("just-enough", altered_num_riddles=250, total_score=0.7),
    ]
    leaderboard = build_leaderboard(results)
    model_names = [r["model"] for r in leaderboard]
    assert "big-model" in model_names
    assert "just-enough" in model_names
    assert "small-model" not in model_names
    assert "medium-model" not in model_names
    assert len(leaderboard) == 2


def test_sorted_by_total_score_descending():
    """Models should be sorted by total_score descending (primary key)."""
    results = [
        _make_result("low", total_score=0.50),
        _make_result("high", total_score=0.90),
        _make_result("mid", total_score=0.70),
    ]
    leaderboard = build_leaderboard(results)
    scores = [r["total_score"] for r in leaderboard]
    assert scores == sorted(scores, reverse=True)
    assert leaderboard[0]["model"] == "high"
    assert leaderboard[1]["model"] == "mid"
    assert leaderboard[2]["model"] == "low"


def test_tiebreak_by_pattern_override_rate():
    """When total_score is tied, lower pattern_override_rate ranks higher."""
    results = [
        _make_result("worse-override", total_score=0.80, pattern_override_rate=0.3),
        _make_result("better-override", total_score=0.80, pattern_override_rate=0.1),
    ]
    leaderboard = build_leaderboard(results)
    assert leaderboard[0]["model"] == "better-override"
    assert leaderboard[1]["model"] == "worse-override"


def test_ranks_assigned_correctly():
    """Each row should receive a sequential 1-based rank."""
    results = [
        _make_result("a", total_score=0.9),
        _make_result("b", total_score=0.7),
        _make_result("c", total_score=0.5),
    ]
    leaderboard = build_leaderboard(results)
    ranks = [r["rank"] for r in leaderboard]
    assert ranks == [1, 2, 3]


def test_ci95_values_computed():
    """CI95 columns should be present and mathematically correct."""
    n = 300
    p_acc = 0.70
    p_avg = 0.65
    p_ovr = 0.10

    results = [
        _make_result(
            "ci-model",
            altered_accuracy=p_acc,
            total_score=p_avg,
            pattern_override_rate=p_ovr,
            altered_num_riddles=n,
        ),
    ]
    leaderboard = build_leaderboard(results)
    row = leaderboard[0]

    expected_acc_ci = round(1.96 * math.sqrt(p_acc * (1 - p_acc) / n), 4)
    expected_avg_ci = round(1.96 * math.sqrt(p_avg * (1 - p_avg) / n), 4)
    expected_ovr_ci = round(1.96 * math.sqrt(p_ovr * (1 - p_ovr) / n), 4)

    assert row["altered_accuracy_ci95"] == expected_acc_ci
    assert row["average_accuracy_ci95"] == expected_avg_ci
    assert row["pattern_override_rate_ci95"] == expected_ovr_ci


def test_empty_input_returns_empty():
    """An empty results list should produce an empty leaderboard."""
    assert build_leaderboard([]) == []
