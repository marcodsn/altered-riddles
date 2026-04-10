"""theme.py — Shared chart utilities for the Altered Riddles benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

# ── Brand Colours ─────────────────────────────────────────────────────

COLORS = {
    "gemma": "#8ab4e8",
    "gemini": "#8ab4e8",
    "gpt": "#82c8b4",
    "mistral": "#f5ae76",
    "qwen": "#b09ddd",
    "glm": "#82bcd8",
    "kimi": "#80c2c6",
    "moonshot": "#80c2c6",
    "claude": "#e8a086",
    "deepseek": "#80aed8",
    "minimax": "#d48e8e",
    "abab": "#d48e8e",
    "llama": "#86b6f2",
    "lfm": "#7dcfcf",
    "liquid": "#7dcfcf",
}
DEFAULT_COLOR = "#9e9e9e"

# ── Layout Constants ──────────────────────────────────────────────────

BG_COLOR = "#f9f7f4"
TRACK_COLOR = "#f1efec"
FONT_FAMILY = "monospace"
TEXT_COLOR = "#1a1a1a"
MUTED_TEXT = "#6b6b6b"
SUBTLE_TEXT = "#4a4a4a"
GRID_COLOR = "#e5e7eb"
DEFAULT_HEIGHT = 750
DEFAULT_SCALE = 3
DEFAULT_TOP_N = 10
LEADERBOARD_PATH = "results/leaderboard.json"
IMAGE_DIR = "data/images"
BLOG_IMAGE_DIR = "data/images/blog"


def get_color(model: str) -> str:
    """Return a brand-aligned colour for *model*."""
    m = model.lower()
    for key, color in COLORS.items():
        if key in m:
            return color
    return DEFAULT_COLOR


def load_leaderboard(
    top_n: int = DEFAULT_TOP_N, path: str = LEADERBOARD_PATH
) -> pd.DataFrame:
    """Load leaderboard JSON, keep top-N by rank, clean model names."""
    with open(path, "r") as f:
        data = json.load(f)
    data = sorted(data, key=lambda x: x["rank"])[:top_n]
    for entry in data:
        model = entry["model"]
        if "/" in model:
            entry["model"] = model.split("/")[-1]
    df = pd.DataFrame(data)
    df["color"] = df["model"].apply(get_color)
    return df


def save_chart(fig, name: str, blog: bool = False, scale: int = DEFAULT_SCALE) -> None:
    """Write a chart to disk; when *blog* is True, also save a borderless copy."""
    out_dir = Path(BLOG_IMAGE_DIR if blog else IMAGE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.write_image(str(out_dir / name), scale=scale)
    print(f"Chart saved: {out_dir / name}")


def rank_box_color(rank: int) -> str:
    """Return fill colour for a rank badge."""
    if rank <= 3:
        return "#1a1a1a"
    if rank <= 6:
        return "#4a4a4a"
    return "#a0a0a0"


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Add shared CLI arguments to a chart script's argparser."""
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP_N, help="Number of top models to show"
    )
    parser.add_argument(
        "--leaderboard",
        type=str,
        default=LEADERBOARD_PATH,
        help="Path to leaderboard.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Custom output path for the chart image",
    )
    parser.add_argument(
        "--blog",
        action="store_true",
        default=False,
        help="Generate blog version (no titles/borders)",
    )
    parser.add_argument(
        "--scale", type=int, default=DEFAULT_SCALE, help="Image scale factor"
    )


def blog_layout_overrides() -> dict:
    """Return layout kwargs that strip titles and margins for blog images."""
    return dict(
        title=None,
        margin=dict(l=0, r=0, t=0, b=0),
    )
