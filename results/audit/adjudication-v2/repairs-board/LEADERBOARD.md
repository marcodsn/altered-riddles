# Development candidate — NOT a release

# Altered Riddles v2 — leaderboard

_Generated 2026-09-09T10:12:45Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 2000 draws). Ranks are point estimates, not significant differences. Comparisons in the JSON use shared familiar items and jointly resampled clusters (pointwise intervals, not multiplicity-adjusted). Rows must pass scoring and pre-publish checks; Git commitment status is not verified._

| point rank | model | thinking | items | COR ↓ | CI95 | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | k | pending | familiarity | checks |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | jalapeno:DeepSeek-V4-Flash-0731 | on | 8 | 0.0% | [0.0, 0.0] | 91.7% | 100.0% | 8.3% | 0.0% | 8.3% | 131.0 | 3 | 0 | direct | ok |
| 2 | nous:meituan/longcat-2.0:free | on | 8 | 2.5% | [0.0, 7.5] | 92.5% | 100.0% | 7.5% | 0.0% | 5.0% | 194.0 | 5 | 0 | direct | ok |
| 3 | jalapeno:GLM-5.3-Flash | on | 8 | 5.0% | [0.0, 15.0] | 95.0% | 100.0% | 5.0% | 0.0% | 0.0% | 169.5 | 5 | 0 | thinking | ok |
| 4 | nous:meituan/longcat-2.0:free | off | 8 | 17.5% | [0.0, 42.5] | 80.0% | 77.5% | -2.5% | 0.0% | 2.5% | 0.0 | 5 | 0 | direct | ok |

## Pre-publish checks

_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| nous:meituan/longcat-2.0:free | 17.5% | 2.5% | 15.0% |

## Not on the board

- jalapeno:DeepSeek-V4-Flash-0731 (off): other+abstain 15%: COR flattered, rank by accuracy
