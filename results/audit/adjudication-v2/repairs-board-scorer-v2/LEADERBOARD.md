# Development candidate — scorer v2, NOT a release

Open issues: 13 label-audit disagreements; 14 fresh token-cap stops, including 11/40 Longcat warned thinking-on repair replies.

# Altered Riddles v2 — leaderboard

_Generated 2026-09-09T10:21:50Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 2000 draws). Ranks are point estimates, not significant differences. Comparisons in the JSON use shared familiar items and jointly resampled clusters (pointwise intervals, not multiplicity-adjusted). Rows must pass scoring and pre-publish checks; Git commitment status is not verified._

| point rank | model | thinking | items | COR ↓ | CI95 | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | k | pending | familiarity | checks |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | nous:meituan/longcat-2.0:free | on | 8 | 0.0% | [0.0, 0.0] | 92.5% | 72.5% | -20.0% | 2.5% | 5.0% | 194.0 | 5 | 0 | direct | ok |
| 2 | jalapeno:GLM-5.3-Flash | on | 8 | 5.0% | [0.0, 15.0] | 95.0% | 100.0% | 5.0% | 0.0% | 0.0% | 169.5 | 5 | 0 | thinking | ok |
| 3 | nous:meituan/longcat-2.0:free | off | 8 | 17.5% | [0.0, 42.5] | 80.0% | 77.5% | -2.5% | 0.0% | 2.5% | 0.0 | 5 | 0 | direct | ok |

## Pre-publish checks

_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| nous:meituan/longcat-2.0:free | 17.5% | 0.0% | 17.5% |

## Not on the board

- jalapeno:DeepSeek-V4-Flash-0731 (off): other+abstain 15%: COR flattered, rank by accuracy
- jalapeno:DeepSeek-V4-Flash-0731 (on): other+abstain 12%: COR flattered, rank by accuracy
