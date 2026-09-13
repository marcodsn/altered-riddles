# Development candidate — scoped AI adjudication v1, NOT a release

AI adjudication, not human review or independent empirical validation; selected cases, not a representative judge-accuracy audit.

13 historical cases resolved (all match unchanged current samples); two cap answers resolved separately. Historical token caps remain; no 64k splicing. Source permissions and release checks remain outstanding.

# Altered Riddles v2 — leaderboard

_Generated 2026-09-12T14:51:41Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 2000 draws). Ranks are point estimates, not significant differences. Comparisons in the JSON use shared familiar items and jointly resampled clusters (pointwise intervals, not multiplicity-adjusted). Rows must pass scoring and pre-publish checks; Git commitment status is not verified._

| point rank | model | thinking | items | COR ↓ | CI95 | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | k | pending | familiarity | checks |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | jalapeno:DeepSeek-V4-Flash-0731 | on | 264 | 1.5% | [0.4, 2.7] | 96.7% | 89.4% | -7.3% | 0.3% | 1.6% | 133.5 | 3 | 0 | direct | ok |
| 2 | jalapeno:GLM-5.3-Flash | on | 264 | 2.2% | [1.1, 3.8] | 97.0% | 98.8% | 1.8% | 0.0% | 0.8% | 100.0 | 5 | 0 | thinking | ok |
| 3 | nous:meituan/longcat-2.0:free | on | 264 | 2.7% | [1.3, 4.3] | 95.4% | 83.3% | -12.1% | 0.2% | 1.7% | 133.0 | 5 | 0 | direct | ok |
| 4 | nous:meituan/longcat-2.0:free | off | 264 | 11.5% | [7.6, 15.0] | 83.4% | 76.2% | -7.2% | 0.0% | 5.4% | 0.0 | 5 | 0 | direct | ok |
| 5 | jalapeno:DeepSeek-V4-Flash-0731 | off | 264 | 12.6% | [8.6, 16.9] | 81.1% | 77.0% | -4.1% | 0.0% | 7.0% | 0.0 | 5 | 0 | direct | ok |

## Pre-publish checks

_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | 12.6% | 1.5% | 11.1% |
| nous:meituan/longcat-2.0:free | 11.5% | 2.7% | 8.8% |

## Items to review (validity flags)

_Explicitly labelled AI validity review before publishing; no human review is required. Nothing is dropped automatically. Read the traces: a defensible alternative reading means re-pin or drop; a genuine override stays._

| item | override, thinking on | override, thinking off | n on / off | why flagged |
|---|---:|---:|---:|---|
| bear-house-1 | 84.6% | 100.0% | 13 / 10 | overridden by everyone in both modes: very strong prior, or ambiguous |
| married-boat-1 | 76.9% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| yellow-hat-1 | 38.5% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| last-brick-2 | 30.8% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
