import json

import pandas as pd
import plotly.graph_objects as go

leaderboard_path = "results/leaderboard.json"
with open(leaderboard_path, "r") as f:
    data = json.load(f)

# Keep top-10 models based on their rank in the original leaderboard
data = sorted(data, key=lambda x: x["rank"])[:10]

for entry in data:
    model = entry["model"]
    if "/" in model:
        entry["model"] = model.split("/")[-1]

df = pd.DataFrame(data)

# Sort by rank descending so Rank 1 is at the top of the chart
df = df.sort_values("rank", ascending=False).reset_index(drop=True)


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
    if "kimi" in m or "moonshot" in m:
        return "#80c2c6"
    if "claude" in m:
        return "#e8a086"
    if "deepseek" in m:
        return "#80aed8"
    if "minimax" in m or "abab" in m:
        return "#d48e8e"
    if "llama" in m:
        return "#86b6f2"
    if "lfm" in m or "liquid" in m:
        return "#7dcfcf"
    return "#9e9e9e"


df["color"] = df["model"].apply(get_color)

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
            line=dict(color="#e5e7eb", width=1, dash="dot"),
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
            line=dict(color="#f1efec", width=6),
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
                color="#f9f7f4", size=14, line=dict(color=row["color"], width=3)
            ),
            hovertemplate=f"<b>{row['model']}</b><br>Original Acc: {row['original_accuracy']:.1%}<extra></extra>",
            showlegend=False,
        )
    )

    # --- 3) Layout Aesthetics & Annotations ---

    # Dynamic Rank Box Color
    box_color = (
        "#1a1a1a"
        if row["rank"] <= 3
        else ("#4a4a4a" if row["rank"] <= 6 else "#a0a0a0")
    )

    shapes.append(
        dict(
            type="rect",
            x0=0.08,
            x1=0.12,
            y0=i - 0.25,
            y1=i + 0.25,
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
            font=dict(color="white", size=14, family="monospace"),
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
            font=dict(size=14, family="monospace", color="#1a1a1a"),
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
            font=dict(size=13, family="monospace", color="#6b6b6b"),
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
        font=dict(size=14, family="monospace", color="#4a4a4a"),
    )
)

# X-Axis scale helpers at the bottom
annotations.append(
    dict(
        x=0.2,
        y=-0.6,
        text="20%",
        showarrow=False,
        font=dict(size=12, family="monospace", color="#9ca3af"),
    )
)
annotations.append(
    dict(
        x=1.0,
        y=-0.6,
        text="100%",
        showarrow=False,
        font=dict(size=12, family="monospace", color="#9ca3af"),
    )
)

fig.update_layout(
    font=dict(color="#1a1a1a", family="monospace"),
    xaxis=dict(
        showticklabels=False, showgrid=False, zeroline=False, range=[0.05, 1.25]
    ),
    yaxis=dict(
        showticklabels=False, showgrid=False, zeroline=False, range=[-1.0, len(df)]
    ),
    plot_bgcolor="#f9f7f4",
    paper_bgcolor="#f9f7f4",
    margin=dict(l=0, r=0, t=20, b=0),
    annotations=annotations,
    shapes=shapes,
    height=750,
)

fig.write_image("data/images/blog/original_vs_altered_chart.png", scale=3)
print("Updated blog chart created successfully.")
