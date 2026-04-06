import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go

leaderboard_path = "results/leaderboard.json"
with open(leaderboard_path, "r") as f:
    data = json.load(f)

# Keep top-10 models based on their rank in the original leaderboard
data = sorted(data, key=lambda x: x["rank"])[:10]

# Remove company name from model for cleaner display (everything before the /)
for entry in data:
    model = entry["model"]
    if "/" in model:
        entry["model"] = model.split("/")[-1]

df = pd.DataFrame(data)

# Calculate efficiency metric
df["tokens_per_riddle"] = df["altered_output_tokens"] / df["altered_num_riddles"]

# Calculate ranks for the dumbbell (method="min" handles any ties)
df["acc_rank"] = df["altered_accuracy"].rank(ascending=False, method="min")
df["eff_rank"] = df["tokens_per_riddle"].rank(ascending=True, method="min")

# Sort by accuracy rank descending so Rank 1 accuracy is at the top of the chart (highest y-value)
df = df.sort_values("acc_rank", ascending=False).reset_index(drop=True)


def get_color(model):
    m = model.lower()
    if "gemma" in m or "gemini" in m:
        return "#8ab4e8"
    if "gpt" in m:
        return "#82c8b4"
    if "mistral" in m:
        return "#f5ae76"
    if "qwen" in m:
        return "#b09ddd"
    if "glm" in m:
        return "#82bcd8"
    if "kimi" in m:
        return "#80c2c6"
    if "claude" in m:
        return "#e8a086"
    if "deepseek" in m:
        return "#80aed8"
    if "minimax" in m:
        return "#d48e8e"
    if "llama" in m:
        return "#86b6f2"
    if "lfm" in m or "liquid" in m:
        return "#7dcfcf"
    return "#9e9e9e"


df["color"] = df["model"].apply(get_color)

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
            line=dict(color="#e5e7eb", width=1, dash="dot"),
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
            line=dict(color="#f1efec", width=6),
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
                color="#f9f7f4", size=14, line=dict(color=row["color"], width=3)
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

    # Rank Box (Using original leaderboard rank from your dataset)
    box_color = (
        "#1a1a1a"
        if row["rank"] <= 3
        else ("#4a4a4a" if row["rank"] <= 6 else "#a0a0a0")
    )

    shapes.append(
        dict(
            type="rect",
            x0=11.4,
            x1=11.0,
            y0=i - 0.25,
            y1=i + 0.25,
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
            text=str(row["rank"]),
            showarrow=False,
            font=dict(color="white", size=14, family="monospace"),
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
            font=dict(size=14, family="monospace", color="#1a1a1a"),
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
            font=dict(size=13, family="monospace", color="#6b6b6b"),
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
        font=dict(size=14, family="monospace", color="#4a4a4a"),
    )
)

# X-Axis scale helpers at the bottom
annotations.append(
    dict(
        x=10,
        y=-0.6,
        text="Rank 10 (Worst)",
        showarrow=False,
        font=dict(size=12, family="monospace", color="#9ca3af"),
    )
)
annotations.append(
    dict(
        x=1,
        y=-0.6,
        text="Rank 1 (Best)",
        showarrow=False,
        font=dict(size=12, family="monospace", color="#9ca3af"),
    )
)

fig.update_layout(
    font=dict(color="#1a1a1a", family="monospace"),
    title=dict(
        text="ACCURACY VS EFFICIENCY<br>"
        "<span style='font-size:12px;font-weight:normal;color:#4a4a4a'>"
        "Comparing altered accuracy rank vs token efficiency rank (further right is better)"
        "</span>",
        font=dict(family="monospace", size=16, color="#1a1a1a"),
    ),
    # The reversed X-axis is the secret to making this layout work perfectly
    xaxis=dict(
        showticklabels=False, showgrid=False, zeroline=False, range=[11.5, -0.5]
    ),
    yaxis=dict(
        showticklabels=False, showgrid=False, zeroline=False, range=[-1.0, len(df)]
    ),
    plot_bgcolor="#f9f7f4",
    paper_bgcolor="#f9f7f4",
    margin=dict(l=20, r=20, t=90, b=20),
    annotations=annotations,
    shapes=shapes,
    height=750,
)

fig.write_image("data/images/token_efficiency_chart.png", scale=3)
print("Updated dumbbell chart created successfully.")
