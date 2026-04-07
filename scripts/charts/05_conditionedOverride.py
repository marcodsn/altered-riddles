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

# Sort by Conditioned Override Rate ascending (best/lowest rate at the top)
df = df.sort_values("conditioned_override_rate", ascending=True).reset_index(drop=True)

# Assign a new rank based on this specific metric's sorting
df["new_rank"] = df.index + 1


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

# 1) Background grey bar (100%)
fig.add_trace(
    go.Bar(
        y=y_vals,
        x=[1.0] * len(df),
        orientation="h",
        marker=dict(color="#f1efec"),
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
    box_color = (
        "#1a1a1a"
        if row["new_rank"] <= 3
        else ("#4a4a4a" if row["new_rank"] <= 6 else "#a0a0a0")
    )
    text_color = "white"

    shapes.append(
        dict(
            type="rect",
            x0=-0.08,
            x1=-0.02,
            y0=i - 0.25,
            y1=i + 0.25,
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
            font=dict(color=text_color, size=14, family="monospace"),
            xanchor="center",
            yanchor="middle",
        )
    )

    # Model Name
    annotations.append(
        dict(
            x=0.0,
            y=i,
            text=row["model"] + f" ({row.get('quantization', '')})"
            if row.get("quantization")
            else row["model"],
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            yshift=12,
            font=dict(size=14, family="monospace", color="#1a1a1a"),
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
            font=dict(size=14, family="monospace", color="#6b6b6b"),
        )
    )

fig.update_layout(
    font=dict(color="#1a1a1a", family="monospace"),
    barmode="overlay",
    title=dict(
        text="THE TRUE TRAP RATE<br>"
        "<span style='font-size:12px;font-weight:normal;color:#4a4a4a'>"
        "Conditioned override rate: How often a model defaults to the original answer,<br>"
        "given that it successfully solved the original version."
        "</span>",
        font=dict(family="monospace", size=16, color="#1a1a1a"),
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
    plot_bgcolor="#f9f7f4",
    paper_bgcolor="#f9f7f4",
    margin=dict(l=20, r=20, t=130, b=20),
    annotations=annotations,
    shapes=shapes,
    height=750,
)

fig.write_image("data/images/conditioned_override_chart.png", scale=3)
print("Conditioned Override chart created successfully.")
