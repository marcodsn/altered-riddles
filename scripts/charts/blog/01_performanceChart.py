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
df["error"] = 1.96 * np.sqrt(
    df["total_score"] * (1 - df["total_score"]) / df["num_riddles"]
)
df = df.sort_values("total_score", ascending=True).reset_index(drop=True)


def get_color(model):
    m = model.lower()
    if "gemma" in m or "gemini" in m:
        return "#8ab4e8"  # Gemini blue — pastel of brand #4796E3
    if "gpt" in m:
        return "#82c8b4"  # ChatGPT green — pastel of brand #10A37F
    if "mistral" in m:
        return "#f5ae76"  # Mistral orange — pastel of brand #FF8205
    if "qwen" in m:
        return "#b09ddd"  # Qwen purple-blue — pastel of Alibaba/Qwen identity
    if "glm" in m:
        return "#82bcd8"  # Zhipu GLM blue — pastel of brand identity
    if "kimi" in m:
        return "#80c2c6"  # Kimi teal — pastel of Moonshot AI identity
    if "claude" in m:
        return "#e8a086"  # Claude terra cotta — pastel of brand #DA7756
    if "deepseek" in m:
        return "#80aed8"  # DeepSeek blue — pastel of whale logo #2B6CB4
    if "minimax" in m:
        return "#d48e8e"  # MiniMax red — pastel of brand #B4393C
    if "llama" in m:
        return "#86b6f2"  # Meta/LLaMA blue — pastel of Meta #0082FB
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

# Altered accuracy intersected with average_accuracy is the total score
# Altered accuracy does not include partial score riddles, so it is always <= total_score
# weighted accuracy includes partial score riddles, but only counts the first sample

# 2) Faint bar for altered_weighted_accuracy
fig.add_trace(
    go.Bar(
        y=y_vals,
        x=df["average_accuracy"],
        orientation="h",
        marker=dict(color=df["color"], opacity=0.3),
        showlegend=False,
        width=0.35,
    )
)

# 3) Solid bar for altered_accuracy + error bars
fig.add_trace(
    go.Bar(
        y=y_vals,
        x=df["altered_accuracy"],
        orientation="h",
        marker=dict(color=df["color"], opacity=1.0),
        error_x=dict(
            type="data", array=df["error"], color="#111827", thickness=1.5, width=4
        ),
        showlegend=False,
        width=0.35,
    )
)

annotations = []
shapes = []

for i, row in df.iterrows():
    # Rank Box
    box_color = (
        "#1a1a1a"
        if row["rank"] <= 3
        else ("#4a4a4a" if row["rank"] <= 6 else "#a0a0a0")
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

    # Rank Text
    annotations.append(
        dict(
            x=-0.05,
            y=i,
            text=str(row["rank"]),
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

    # Score Text
    val = row["altered_accuracy"] * 100
    err = row["error"] * 100
    txt = f"{val:.2f} ±{err:.2f}"
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
    xaxis=dict(
        showticklabels=False, showgrid=False, zeroline=False, range=[-0.1, 1.05]
    ),
    yaxis=dict(
        showticklabels=False,
        showgrid=False,
        zeroline=False,
        range=[-0.5, len(df) - 0.1],
    ),
    plot_bgcolor="#f9f7f4",
    paper_bgcolor="#f9f7f4",
    margin=dict(l=0, r=0, t=0, b=0),
    annotations=annotations,
    shapes=shapes,
    height=750,
)

fig.write_image("data/images/blog/performance_chart.png", scale=3)
print("Updated blog chart created successfully.")
