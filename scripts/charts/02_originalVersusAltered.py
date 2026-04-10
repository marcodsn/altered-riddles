#!/usr/bin/env python3
"""Original vs Altered accuracy dumbbell chart."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import plotly.graph_objects as go

# Ensure repo root is importable when running as a standalone script
_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from scripts.charts.theme import (
    BG_COLOR,
    FONT_FAMILY,
    GRID_COLOR,
    MUTED_TEXT,
    SUBTLE_TEXT,
    TEXT_COLOR,
    TRACK_COLOR,
    add_common_args,
    blog_layout_overrides,
    load_leaderboard,
    rank_box_color,
    save_chart,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Original vs Altered accuracy chart")
    add_common_args(parser)
    args = parser.parse_args()

    df = load_leaderboard(top_n=args.top, path=args.leaderboard)

    # Sort by rank descending so Rank 1 is at the top of the chart
    df = df.sort_values("rank", ascending=False).reset_index(drop=True)

    fig = go.Figure()

    annotations = []
    shapes = []

    # --- 1) Background Grid for Accuracies ---
    # Creates vertical dotted lines every 10%
    for r in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        shapes.append(
            dict(
                type="line",
                x0=r,
                x1=r,
                y0=-0.5,
                y1=len(df) - 0.5,
                line=dict(color=GRID_COLOR, width=1, dash="dot"),
                layer="below",
            )
        )

    for i, row in df.iterrows():
        # --- 2) Dumbbell Traces ---

        # Background grey track from 20% to 100%
        fig.add_trace(
            go.Scatter(
                x=[0.2, 1.0],
                y=[i, i],
                mode="lines",
                line=dict(color=TRACK_COLOR, width=6),
                hoverinfo="none",
                showlegend=False,
            )
        )

        # Connecting line between original and altered accuracy
        fig.add_trace(
            go.Scatter(
                x=[row["altered_accuracy"], row["original_accuracy"]],
                y=[i, i],
                mode="lines",
                line=dict(color=row["color"], width=3),
                hoverinfo="none",
                showlegend=False,
            )
        )

        # Altered Marker (Solid circle) - represents the degraded accuracy
        fig.add_trace(
            go.Scatter(
                x=[row["altered_accuracy"]],
                y=[i],
                mode="markers",
                marker=dict(color=row["color"], size=16),
                hovertemplate=f"<b>{row['model']}</b><br>Altered Acc: {row['altered_accuracy']:.1%}<extra></extra>",
                showlegend=False,
            )
        )

        # Original Marker (Hollow circle) - represents the starting accuracy
        fig.add_trace(
            go.Scatter(
                x=[row["original_accuracy"]],
                y=[i],
                mode="markers",
                marker=dict(
                    color=BG_COLOR, size=14, line=dict(color=row["color"], width=3)
                ),
                hovertemplate=f"<b>{row['model']}</b><br>Original Acc: {row['original_accuracy']:.1%}<extra></extra>",
                showlegend=False,
            )
        )

        # --- 3) Layout Aesthetics & Annotations ---

        # Dynamic Rank Box Color
        box_color = rank_box_color(int(row["rank"]))

        shapes.append(
            dict(
                type="rect",
                x0=0.07,
                x1=0.13,
                y0=float(i) - 0.25,  # type: ignore[arg-type]
                y1=float(i) + 0.25,  # type: ignore[arg-type]
                fillcolor=box_color,
                line=dict(width=0),
            )
        )

        # Rank Text
        annotations.append(
            dict(
                x=0.10,
                y=i,
                text=str(row["rank"]),
                showarrow=False,
                font=dict(color="white", size=14, family=FONT_FAMILY),
                xanchor="center",
                yanchor="middle",
            )
        )

        # Model Name
        model_name = row["model"]
        annotations.append(
            dict(
                x=0.14,
                y=i,
                text=model_name,
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                yshift=12,
                font=dict(size=14, family=FONT_FAMILY, color=TEXT_COLOR),
            )
        )

        # Right-aligned Score Text
        orig_val = row["original_accuracy"] * 100
        alt_val = row["altered_accuracy"] * 100
        annotations.append(
            dict(
                x=0.8,
                y=i,
                text=f"Orig: {orig_val:.1f}% | Alt: {alt_val:.1f}%",
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                yshift=12,
                font=dict(size=13, family=FONT_FAMILY, color=MUTED_TEXT),
            )
        )

    # --- 4) Legend and Axis Labels ---

    # Custom legend at the top
    annotations.append(
        dict(
            x=0.6,
            y=len(df) - 0.1,
            text="○ Original Accuracy &nbsp;&nbsp;&nbsp; ● Altered Accuracy",
            showarrow=False,
            xanchor="center",
            yanchor="bottom",
            font=dict(size=14, family=FONT_FAMILY, color=SUBTLE_TEXT),
        )
    )

    # X-Axis scale helpers at the bottom
    annotations.append(
        dict(
            x=0.2,
            y=-0.6,
            text="20%",
            showarrow=False,
            font=dict(size=12, family=FONT_FAMILY, color="#9ca3af"),
        )
    )
    annotations.append(
        dict(
            x=1.0,
            y=-0.6,
            text="100%",
            showarrow=False,
            font=dict(size=12, family=FONT_FAMILY, color="#9ca3af"),
        )
    )

    fig.update_layout(
        font=dict(color=TEXT_COLOR, family=FONT_FAMILY),
        title=dict(
            text="ORIGINAL VS ALTERED ACCURACY<br>"
            f"<span style='font-size:12px;font-weight:normal;color:{SUBTLE_TEXT}'>"
            "Comparing original accuracy vs altered accuracy drop (further right is better)"
            "</span>",
            font=dict(family=FONT_FAMILY, size=16, color=TEXT_COLOR),
        ),
        xaxis=dict(
            showticklabels=False, showgrid=False, zeroline=False, range=[0.05, 1.25]
        ),
        yaxis=dict(
            showticklabels=False, showgrid=False, zeroline=False, range=[-1.0, len(df)]
        ),
        plot_bgcolor=BG_COLOR,
        paper_bgcolor=BG_COLOR,
        margin=dict(l=20, r=20, t=90, b=20),
        annotations=annotations,
        shapes=shapes,
        height=750,
    )

    if args.blog:
        fig.update_layout(**blog_layout_overrides())

    output_name = "original_vs_altered_chart.png"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(args.output, scale=args.scale)
        print(f"Chart saved: {args.output}")
    else:
        save_chart(fig, output_name, blog=args.blog, scale=args.scale)


if __name__ == "__main__":
    main()
