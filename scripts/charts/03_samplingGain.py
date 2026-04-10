#!/usr/bin/env python3
"""Sampling gain comparison chart — majority vote and best-of-N gains."""

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
    MUTED_TEXT,
    TEXT_COLOR,
    TRACK_COLOR,
    add_common_args,
    blog_layout_overrides,
    load_leaderboard,
    rank_box_color,
    save_chart,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sampling gain comparison chart")
    add_common_args(parser)
    args = parser.parse_args()

    df = load_leaderboard(top_n=args.top, path=args.leaderboard)
    df["maj_gain"] = df["majority_vote_accuracy"] - df["average_accuracy"]
    df["bon_gain"] = df["best_of_n_accuracy"] - df["average_accuracy"]
    df = df.sort_values("average_accuracy", ascending=True).reset_index(drop=True)

    fig = go.Figure()
    y_vals = list(range(len(df)))

    # 1) Background grey bar (full width)
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

    # 2) Base bar (average_accuracy)
    fig.add_trace(
        go.Bar(
            y=y_vals,
            x=df["average_accuracy"],
            orientation="h",
            name="Avg Accuracy",
            showlegend=False,
            marker=dict(color=df["color"], opacity=0.85),
            width=0.35,
        )
    )

    # 3) Best-of-N gain (always positive, gold segment)
    fig.add_trace(
        go.Bar(
            y=y_vals,
            x=df["bon_gain"],
            base=df["average_accuracy"],
            orientation="h",
            name="Best-of-N Gain",
            marker=dict(color="#f9d48e", opacity=0.75),
            width=0.35,
        )
    )

    # 4) Majority vote gain — POSITIVE (green segment extending right)
    pos_mask = df["maj_gain"] >= 0
    fig.add_trace(
        go.Bar(
            y=[y_vals[i] for i in df.index[pos_mask]],
            x=df.loc[pos_mask, "maj_gain"],
            base=df.loc[pos_mask, "average_accuracy"],
            orientation="h",
            name="Majority Vote Gain (+)",
            marker=dict(color="#a2d9b5", opacity=0.9),
            width=0.35,
        )
    )

    # 5) Majority vote gain — NEGATIVE (red segment extending left)
    neg_mask = df["maj_gain"] < 0
    fig.add_trace(
        go.Bar(
            y=[y_vals[i] for i in df.index[neg_mask]],
            x=df.loc[neg_mask, "maj_gain"].abs(),
            base=df.loc[neg_mask, "majority_vote_accuracy"],
            orientation="h",
            name="Majority Vote Loss (−)",
            marker=dict(color="#fca5a5", opacity=0.9),
            width=0.35,
        )
    )

    # Annotations: rank box + model name on top + score on right
    annotations = []
    shapes = []
    for i, row in df.iterrows():
        box_color = rank_box_color(int(row["rank"]))

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

        # Rank Text
        annotations.append(
            dict(
                x=-0.05,
                y=i,
                text=str(row["rank"]),
                showarrow=False,
                font=dict(color="white", size=14, family=FONT_FAMILY),
                xanchor="center",
                yanchor="middle",
            )
        )

        # Model Name
        annotations.append(
            dict(
                x=0.0,
                y=i,
                text=row["model"],
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                yshift=12,
                font=dict(size=13, family=FONT_FAMILY, color=TEXT_COLOR),
            )
        )

        # Score Text
        bon_pct = row["bon_gain"] * 100
        maj_pct = row["maj_gain"] * 100
        avg_pct = row["average_accuracy"] * 100
        sign = "+" if maj_pct >= 0 else ""
        txt = f"avg {avg_pct:.1f}%   maj {sign}{maj_pct:.1f}%   bon +{bon_pct:.1f}%"
        annotations.append(
            dict(
                x=1.0,
                y=i,
                text=txt,
                showarrow=False,
                xanchor="right",
                yanchor="bottom",
                yshift=12,
                font=dict(size=11, family=FONT_FAMILY, color=MUTED_TEXT),
            )
        )

    fig.update_layout(
        font=dict(color=TEXT_COLOR, family=FONT_FAMILY),
        barmode="overlay",
        title=dict(
            text="SAMPLING GAIN COMPARISON<br>"
            f"<span style='font-size:12px;font-weight:normal;color:{MUTED_TEXT}'>"
            "Base = avg accuracy | majority gain | majority loss | best-of-N gain"
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
        ),
        plot_bgcolor=BG_COLOR,
        paper_bgcolor=BG_COLOR,
        margin=dict(l=20, r=20, t=100, b=20),
        annotations=annotations,
        shapes=shapes,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.02,
            xanchor="center",
            x=0.5,
            font=dict(family=FONT_FAMILY, size=12),
        ),
        height=850,
    )

    if args.blog:
        fig.update_layout(**blog_layout_overrides())

    output_name = "sampling_gain_chart.png"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        fig.write_image(args.output, scale=args.scale)
        print(f"Chart saved: {args.output}")
    else:
        save_chart(fig, output_name, blog=args.blog, scale=args.scale)


if __name__ == "__main__":
    main()
