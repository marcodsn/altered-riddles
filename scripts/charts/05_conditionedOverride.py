#!/usr/bin/env python3
"""Conditioned override rate chart — the true trap rate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import plotly.graph_objects as go

from scripts.charts.theme import (
    BG_COLOR,
    FONT_FAMILY,
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
    parser = argparse.ArgumentParser(description="Conditioned override rate chart")
    add_common_args(parser)
    args = parser.parse_args()

    df = load_leaderboard(top_n=args.top, path=args.leaderboard)

    # Sort by Conditioned Override Rate ascending (best/lowest rate at the top)
    df = df.sort_values("conditioned_override_rate", ascending=True).reset_index(
        drop=True
    )

    # Assign a new rank based on this specific metric's sorting
    df["new_rank"] = df.index + 1

    fig = go.Figure()
    y_vals = list(range(len(df)))

    # 1) Background grey bar (100%)
    fig.add_trace(
        go.Bar(
            y=y_vals,
            x=[1.0] * len(df),
            orientation="h",
            marker=dict(color=TRACK_COLOR),
            hoverinfo="none",
            showlegend=False,
            width=0.35,
        )
    )

    # 2) Solid bar for conditioned_override_rate
    fig.add_trace(
        go.Bar(
            y=y_vals,
            x=df["conditioned_override_rate"],
            orientation="h",
            marker=dict(color=df["color"], opacity=1.0),
            showlegend=False,
            width=0.35,
        )
    )

    annotations = []
    shapes = []

    for i, row in df.iterrows():
        # Rank Box (now using the new_rank based on Conditioned Override)
        box_color = rank_box_color(int(row["new_rank"]))

        shapes.append(
            dict(
                type="rect",
                x0=-0.08,
                x1=-0.02,
                y0=float(i) - 0.25,  # type: ignore[arg-type]
                y1=float(i) + 0.25,  # type: ignore[arg-type]
                fillcolor=box_color,
                line=dict(width=0),
                xref="x",
                yref="y",
            )
        )

        # New Rank Text
        annotations.append(
            dict(
                x=-0.05,
                y=i,
                text=str(row["new_rank"]),
                showarrow=False,
                font=dict(color="white", size=14, family=FONT_FAMILY),
                xanchor="center",
                yanchor="middle",
            )
        )

        # Model Name
        model_label = (
            row["model"] + f" ({row.get('quantization', '')})"
            if row.get("quantization")
            else row["model"]
        )
        annotations.append(
            dict(
                x=0.0,
                y=i,
                text=model_label,
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                yshift=12,
                font=dict(size=14, family=FONT_FAMILY, color=TEXT_COLOR),
            )
        )

        # Score Text (e.g., "14.2%")
        val = row["conditioned_override_rate"] * 100
        txt = f"{val:.1f}%"
        annotations.append(
            dict(
                x=1.0,
                y=i,
                text=txt,
                showarrow=False,
                xanchor="right",
                yanchor="bottom",
                yshift=12,
                font=dict(size=14, family=FONT_FAMILY, color=MUTED_TEXT),
            )
        )

    fig.update_layout(
        font=dict(color=TEXT_COLOR, family=FONT_FAMILY),
        barmode="overlay",
        title=dict(
            text="THE TRUE TRAP RATE<br>"
            f"<span style='font-size:12px;font-weight:normal;color:{SUBTLE_TEXT}'>"
            "Conditioned override rate: How often a model defaults to the original answer,<br>"
            "given that it successfully solved the original version."
            "</span>",
            font=dict(family=FONT_FAMILY, size=16, color=TEXT_COLOR),
        ),
        xaxis=dict(
            showticklabels=False, showgrid=False, zeroline=False, range=[-0.1, 1.05]
        ),
        yaxis=dict(
            showticklabels=False,
            showgrid=False,
            zeroline=False,
            range=[-0.5, len(df) - 0.1],
            autorange="reversed",  # Flips y-axis so index 0 (Rank 1) is at the top
        ),
        plot_bgcolor=BG_COLOR,
        paper_bgcolor=BG_COLOR,
        margin=dict(l=20, r=20, t=130, b=20),
        annotations=annotations,
        shapes=shapes,
        height=750,
    )

    if args.blog:
        fig.update_layout(**blog_layout_overrides())

    output_name = "conditioned_override_chart.png"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(args.output, scale=args.scale)
        print(f"Chart saved: {args.output}")
    else:
        save_chart(fig, output_name, blog=args.blog, scale=args.scale)


if __name__ == "__main__":
    main()
