import json

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
df["maj_gain"] = df["majority_vote_accuracy"] - df["average_accuracy"]
df["bon_gain"] = df["best_of_n_accuracy"] - df["average_accuracy"]
df = df.sort_values("average_accuracy", ascending=True).reset_index(drop=True)


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

# 1) Background grey bar (full width)
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

# 5) Best-of-N gain (always positive, gold segment)
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

# 3) Majority vote gain — POSITIVE (green segment extending right)
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

# 4) Majority vote gain — NEGATIVE (red segment extending left)
neg_mask = df["maj_gain"] < 0
fig.add_trace(
    go.Bar(
        y=[y_vals[i] for i in df.index[neg_mask]],
        x=df.loc[neg_mask, "maj_gain"].abs(),
        base=df.loc[neg_mask, "majority_vote_accuracy"],  # base is the lower value
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
    annotations.append(
        dict(
            x=0.0,
            y=i,
            text=row["model"],
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            yshift=12,
            font=dict(size=13, family="monospace", color="#1a1a1a"),
        )
    )
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
            font=dict(size=11, family="monospace", color="#6b6b6b"),
        )
    )

fig.update_layout(
    font=dict(color="#1a1a1a", family="monospace"),
    barmode="overlay",
    title=dict(
        text="SAMPLING GAIN COMPARISON<br>"
        "<span style='font-size:12px;font-weight:normal;color:#4a4a4a'>"
        "Base = avg accuracy | majority gain | majority loss | best-of-N gain"
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
    ),
    plot_bgcolor="#f9f7f4",
    paper_bgcolor="#f9f7f4",
    margin=dict(l=20, r=20, t=100, b=20),
    annotations=annotations,
    shapes=shapes,
    legend=dict(
        orientation="h",
        yanchor="top",
        y=-0.02,
        xanchor="center",
        x=0.5,
        font=dict(family="monospace", size=12),
    ),
    height=850,
)

fig.write_image("data/images/sampling_gain_chart.png", scale=3)
print("Updated chart created successfully.")
