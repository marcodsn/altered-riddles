#!/usr/bin/env python3
"""Accuracy vs Efficiency dumbbell chart — comparing accuracy rank vs token efficiency rank."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import plotly.graph_objects as go

# Ensure the repo root is in sys.path for absolute imports
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
    parser = argparse.ArgumentParser(
        description="Accuracy vs Efficiency dumbbell chart"
    )
    add_common_args(parser)
    args = parser.parse_args()

    # Load all models, then filter to reasoning models only
    df = load_leaderboard(top_n=9999, path=args.leaderboard)
    df = (
        df[df["model"].str.endswith(":reasoning")].head(args.top).reset_index(drop=True)
    )

    # Calculate efficiency metric
    df["tokens_per_riddle"] = df["altered_output_tokens"] / df["altered_num_riddles"]

    # Calculate ranks for the dumbbell (method="min" handles any ties)
    df["acc_rank"] = df["altered_accuracy"].rank(ascending=False, method="min")  # type: ignore[union-attr]
    df["eff_rank"] = df["tokens_per_riddle"].rank(ascending=True, method="min")  # type: ignore[union-attr]

    # Calculate a combined rank (average of accuracy and efficiency)
    df["combined_rank"] = ((df["acc_rank"] + df["eff_rank"]) / 2).rank(method="min")  # type: ignore[union-attr]

    # Sort by combined rank descending so Rank 1 is at the top of the chart (highest y-value)
    df = df.sort_values("combined_rank", ascending=False).reset_index(drop=True)  # type: ignore[call-overload]

    fig = go.Figure()
    y_vals = list(range(len(df)))

    annotations = []
    shapes = []

    # --- 1) Background Grid for Ranks ---
    for r in range(1, 11):
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

        # Background grey track from rank 10 to 1
        fig.add_trace(
            go.Scatter(
                x=[10, 1],
                y=[i, i],
                mode="lines",
                line=dict(color=TRACK_COLOR, width=6),
                hoverinfo="none",
                showlegend=False,
            )
        )

        # Connecting line between efficiency rank and accuracy rank
        fig.add_trace(
            go.Scatter(
                x=[row["eff_rank"], row["acc_rank"]],
                y=[i, i],
                mode="lines",
                line=dict(color=row["color"], width=3),
                hoverinfo="none",
                showlegend=False,
            )
        )

        # Efficiency Marker (Hollow circle)
        fig.add_trace(
            go.Scatter(
                x=[row["eff_rank"]],
                y=[i],
                mode="markers",
                marker=dict(
                    color=BG_COLOR, size=14, line=dict(color=row["color"], width=3)
                ),
                hovertemplate=(
                    f"<b>{row['model']}</b><br>"
                    f"Efficiency Rank: {int(row['eff_rank'])}<br>"
                    f"Tokens/Riddle: {row['tokens_per_riddle']:,.0f}<extra></extra>"
                ),
                showlegend=False,
            )
        )

        # Accuracy Marker (Solid circle)
        fig.add_trace(
            go.Scatter(
                x=[row["acc_rank"]],
                y=[i],
                mode="markers",
                marker=dict(color=row["color"], size=16),
                hovertemplate=(
                    f"<b>{row['model']}</b><br>"
                    f"Accuracy Rank: {int(row['acc_rank'])}<br>"
                    f"Altered Acc: {row['altered_accuracy']:.1%}<extra></extra>"
                ),
                showlegend=False,
            )
        )

        # --- 3) Layout Aesthetics & Annotations ---

        # Rank Box (Using combined rank)
        box_color = rank_box_color(int(row["combined_rank"]))

        shapes.append(
            dict(
                type="rect",
                x0=11.5,
                x1=10.9,
                y0=float(i) - 0.25,  # type: ignore[arg-type]
                y1=float(i) + 0.25,  # type: ignore[arg-type]
                fillcolor=box_color,
                line=dict(width=0),
                xref="x",
                yref="y",
            )
        )

        # Rank Text
        annotations.append(
            dict(
                x=11.2,
                y=i,
                text=str(int(row["combined_rank"])),
                showarrow=False,
                font=dict(color="white", size=14, family=FONT_FAMILY),
                xanchor="center",
                yanchor="middle",
            )
        )

        # Model Name
        model_name = row["model"] + (
            f" ({row.get('quantization', '')})" if row.get("quantization") else ""
        )
        annotations.append(
            dict(
                x=10.8,
                y=i,
                text=model_name,
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                yshift=12,
                font=dict(size=14, family=FONT_FAMILY, color=TEXT_COLOR),
            )
        )

        # Score Text (repurposed to show raw values instead of error bars)
        acc_val = row["altered_accuracy"] * 100
        tok_val = row["tokens_per_riddle"]
        annotations.append(
            dict(
                x=0.0,
                y=i,
                text=f"Acc: {acc_val:.1f}% | Tok: {tok_val:,.0f}",
                showarrow=False,
                xanchor="right",
                yanchor="bottom",
                yshift=12,
                font=dict(size=13, family=FONT_FAMILY, color=MUTED_TEXT),
            )
        )

    # --- 4) Legend and Axis Labels ---

    # Custom legend at the top
    annotations.append(
        dict(
            x=5.5,
            y=len(df) - 0.1,
            text="● Accuracy Rank &nbsp;&nbsp;&nbsp; ○ Efficiency Rank",
            showarrow=False,
            xanchor="center",
            yanchor="bottom",
            font=dict(size=14, family=FONT_FAMILY, color=SUBTLE_TEXT),
        )
    )

    # X-Axis scale helpers at the bottom
    annotations.append(
        dict(
            x=10,
            y=-0.6,
            text="Rank 10 (Worst)",
            showarrow=False,
            font=dict(size=12, family=FONT_FAMILY, color="#9ca3af"),
        )
    )
    annotations.append(
        dict(
            x=1,
            y=-0.6,
            text="Rank 1 (Best)",
            showarrow=False,
            font=dict(size=12, family=FONT_FAMILY, color="#9ca3af"),
        )
    )

    fig.update_layout(
        font=dict(color=TEXT_COLOR, family=FONT_FAMILY),
        title=dict(
            text="ACCURACY VS EFFICIENCY<br>"
            f"<span style='font-size:12px;font-weight:normal;color:{SUBTLE_TEXT}'>"
            "Comparing altered accuracy rank vs token efficiency rank (further right is better)"
            "</span>",
            font=dict(family=FONT_FAMILY, size=16, color=TEXT_COLOR),
        ),
        # The reversed X-axis is the secret to making this layout work perfectly
        xaxis=dict(
            showticklabels=False, showgrid=False, zeroline=False, range=[11.5, -0.5]
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

    output_name = "token_efficiency_chart.png"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(args.output, scale=args.scale)
        print(f"Chart saved: {args.output}")
    else:
        save_chart(fig, output_name, blog=args.blog, scale=args.scale)


if __name__ == "__main__":
    main()
