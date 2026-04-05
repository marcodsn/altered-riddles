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

# --- FIX: Use the separated metrics from the updated evaluate.py ---
# This calculates tokens spent per individual attempt on the altered tasks
df["tokens_per_riddle"] = df["altered_output_tokens"] / df["altered_num_riddles"]

FAMILY_COLORS = {
    "gemma": "#4db6ac",  # teal
    "gpt": "#81c784",  # green
    "mistral": "#ffb74d",  # orange
    "qwen": "#f06292",  # pink
    "glm": "#64b5f6",  # blue
    "kimi": "#ba68c8",  # purple
}


def get_family(model):
    m = model.lower()
    for key in FAMILY_COLORS:
        if key in m:
            return key
    return "other"


df["family"] = df["model"].apply(get_family)
df["color"] = df["family"].apply(lambda f: FAMILY_COLORS.get(f, "#9e9e9e"))

fig = go.Figure()

# --- Iso-efficiency guide lines (score / tokens_per_riddle = constant) ---
x_range = np.logspace(np.log10(5), np.log10(5000000), 300)

# Define the models you want to use as reference anchors
reference_models = [
    ("gemma-4-26b-a4b-it:reasoning", "dot", None),  # top-performer reference
    ("gpt-oss-20b:reasoning", "dash", "iso-efficiency"),  # mid-tier reasoning reference
    ("gemma-4-31b-it", "dot", None),  # standard model reference
]

for ref_model, dash, label in reference_models:
    # Find the model in the dataframe
    row = df[df["model"] == ref_model]

    if not row.empty:
        # Dynamically calculate the iso_val (slope) for this specific model
        iso_val = row["altered_accuracy"].values[0] / row["tokens_per_riddle"].values[0]

        y_iso = iso_val * x_range
        mask = (y_iso >= 0.1) & (y_iso <= 0.9)

        fig.add_trace(
            go.Scatter(
                x=x_range[mask],
                y=y_iso[mask],
                mode="lines",
                line=dict(dash=dash, color="#d1d5db", width=1.2),
                showlegend=False,
                hoverinfo="skip",
            )
        )

# Annotate one iso line as the legend surrogate
fig.add_annotation(
    x=np.log10(1800),
    y=0.82,
    text="iso-efficiency lines",
    showarrow=False,
    font=dict(color="#9ca3af", size=11, family="monospace"),
    xref="x",
    yref="y",
)

# --- One scatter trace per family for legend ---
for family, color in FAMILY_COLORS.items():
    sub = df[df["family"] == family]
    if sub.empty:
        continue
    fig.add_trace(
        go.Scatter(
            x=sub["tokens_per_riddle"],
            y=sub["altered_accuracy"],
            mode="markers",
            name=family,
            marker=dict(color=color, size=14, line=dict(width=1, color="#1f2937")),
            showlegend=False,
            hovertemplate="<b>%{text}</b><br>Tokens/sample: %{x:,.0f}<br>Altered Acc: %{y:.3f}<extra></extra>",
            text=sub["model"],
        )
    )

# --- Labels directly on bubbles ---
for _, row in df.iterrows():
    fig.add_annotation(
        x=np.log10(row["tokens_per_riddle"]),
        y=row["altered_accuracy"],
        text=row["model"] + f" ({row.get('quantization', '')})"
        if row.get("quantization")
        else row["model"],
        showarrow=False,
        yshift=14,
        font=dict(size=11, family="monospace", color="#374151"),
        xanchor="center",
    )

fig.update_layout(
    font=dict(color="#1a1a1a", family="monospace"),
    xaxis=dict(
        title="Output Tokens / Altered Sample (log scale)",
        type="log",
        range=[np.log10(1), np.log10(5000000)],
        gridcolor="#e5e7eb",
        zeroline=False,
        tickformat=",",
        tickfont=dict(family="monospace"),
        tickmode="array",
        tickvals=[10, 100, 1000, 10000, 100000, 1000000],
        ticktext=["10", "100", "1k", "10k", "100k", "1M"],
    ),
    yaxis=dict(
        title="Altered Accuracy",
        range=[0.18, 0.65],
        gridcolor="#e5e7eb",
        zeroline=False,
        tickformat=".0%",
        tickfont=dict(family="monospace"),
    ),
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.08,
        xanchor="center",
        x=0.5,
        font=dict(family="monospace", size=12),
    ),
    plot_bgcolor="#f9f7f4",
    paper_bgcolor="#f9f7f4",
    margin=dict(l=0, r=0, t=0, b=0),
    height=750,
    width=1000,
)

fig.write_image("data/images/blog/token_efficiency.png", scale=3)
print("Updated blog chart created successfully.")
