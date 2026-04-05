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

fig = go.Figure()

# Setup marker sizing so largest bubble is ~45px wide
sizeref = 2.0 * max(df["pattern_override_rate"]) / (45**2)

fig.add_trace(
    go.Scatter(
        x=df["original_accuracy"],
        y=df["altered_accuracy"],
        mode="markers+text",
        marker=dict(
            size=df["pattern_override_rate"],
            sizemode="area",
            sizeref=sizeref,
            sizemin=10,
            color=df["pattern_override_rate"],
            colorscale="Reds",
            showscale=True,
            colorbar=dict(
                title=dict(
                    text="Override Rate", font=dict(family="monospace", size=12)
                ),
                thickness=15,
                len=0.5,
                y=0.5,
            ),
            line=dict(width=1, color="#1f2937"),
        ),
        text=df["model"],
        textposition="top center",
        textfont=dict(family="monospace", size=12, color="#1a1a1a"),
        hovertemplate="<b>%{text}</b><br>Original Acc: %{x:.3f}<br>Altered Acc: %{y:.3f}<br>Override Rate: %{marker.color:.3f}<extra></extra>",
    )
)

fig.update_layout(
    xaxis=dict(
        title="Original Accuracy",
        range=[0.75, 0.95],
        gridcolor="#e5e7eb",
        zeroline=False,
    ),
    yaxis=dict(
        title="Altered Accuracy", range=[0.2, 0.95], gridcolor="#e5e7eb", zeroline=False
    ),
    plot_bgcolor="#f9f7f4",
    paper_bgcolor="#f9f7f4",
    margin=dict(l=0, r=0, t=0, b=0),
    font=dict(family="monospace", color="#1a1a1a"),
    height=800,
    width=950,
)

fig.write_image("data/images/blog/original_vs_altered_chart.png", scale=3)
print("Updated blog chart created successfully.")
