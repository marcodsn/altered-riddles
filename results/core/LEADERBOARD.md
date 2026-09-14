# Altered Riddles v2 — leaderboard

_Generated 2026-09-14T06:57:48Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 2000 draws). Ranks are point estimates, not significant differences; the rank spread counts rows whose pairwise interval excludes zero. Comparisons in the JSON use shared familiar items and jointly resampled clusters (pointwise intervals, not multiplicity-adjusted). Rows must pass scoring and pre-publish checks; Git commitment status is not verified._

| point rank | rank spread | model | thinking | items | COR ↓ | CI95 | orig acc | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | mean out tok | k | pending | familiarity | checks |
|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 1–2 | jalapeno:DeepSeek-V4-Flash-0731 | on | 264 | 1.5% | [0.4, 2.7] | 94.5% | 96.7% | 89.4% | -7.3% | 0.3% | 1.6% | 133.5 | 488 | 3 | 0 | direct | ok |
| 2 | 1–3 | jalapeno:GLM-5.3-Flash | on | 264 | 2.2% | [1.1, 3.8] | 98.8% | 97.0% | 98.8% | 1.8% | 0.0% | 0.8% | 100.0 | 182 | 5 | 0 | thinking | ok |
| 3 | 2–4 | nous:meituan/longcat-2.0:free | on | 264 | 2.7% | [1.3, 4.3] | 97.1% | 95.4% | 83.3% | -12.1% | 0.2% | 1.7% | 133.0 | 326 | 5 | 0 | direct | ok |
| 4 | 3–4 | nous:inclusionai/ling-3.0-flash-fin:free | on | 264 | 4.4% | [2.5, 6.6] | 90.8% | 91.9% | 93.5% | 1.6% | 0.3% | 3.0% | 189.0 | 419 | 5 | 0 | direct | ok |
| 5 | 5–9 | jalapeno:Kimi-K2.5 | off | 264 | 8.6% | [5.5, 12.4] | 97.4% | 88.0% | — | — | 0.0% | 3.6% | 0.0 | 18 | 5 | 0 | direct | ok |
| 6 | 5–12 | jalapeno:GLM-5.2 | off | 264 | 10.5% | [6.9, 14.5] | 97.9% | 83.9% | 80.0% | -3.9% | 0.1% | 5.6% | 0.0 | 7 | 5 | 0 | direct | ok |
| 7 | 5–14 | nous:meituan/longcat-2.0:free | off | 264 | 11.5% | [7.6, 15.0] | 97.1% | 83.4% | 76.2% | -7.2% | 0.0% | 5.4% | 0.0 | 7 | 5 | 0 | direct | ok |
| 8 | 6–14 | nous:inclusionai/ling-3.0-flash-fin:free | off | 264 | 12.2% | [8.2, 16.1] | 90.8% | 77.7% | 70.9% | -6.7% | 0.1% | 9.8% | 0.0 | 11 | 5 | 0 | direct | ok |
| 9 | 6–13 | jalapeno:DeepSeek-V4-Pro | off | 264 | 12.2% | [8.4, 15.9] | 95.6% | 83.3% | 78.6% | -4.6% | 0.0% | 5.0% | 0.0 | 9 | 5 | 0 | direct | ok |
| 10 | 5–14 | jalapeno:GLM-5.1 | off | 264 | 12.3% | [8.3, 16.5] | 97.3% | 83.9% | 82.3% | -1.6% | 0.1% | 4.0% | 0.0 | 5 | 5 | 0 | direct | ok |
| 11 | 5–14 | jalapeno:DeepSeek-V4-Flash-0731 | off | 264 | 12.6% | [8.6, 16.9] | 94.5% | 81.1% | 77.0% | -4.1% | 0.0% | 7.0% | 0.0 | 10 | 5 | 0 | direct | ok |
| 12 | 6–14 | jalapeno:Qwen3.5-122B-A10B | off | 264 | 13.9% | [9.6, 18.4] | 95.9% | 82.0% | 79.2% | -2.7% | 0.1% | 4.5% | 0.0 | 6 | 5 | 0 | direct | ok |
| 13 | 7–14 | nous:inclusionai/ling-3.0-flash-sante:free | off | 264 | 14.4% | [10.4, 18.9] | 94.6% | 78.9% | 75.2% | -3.8% | 0.0% | 7.0% | 0.0 | 11 | 5 | 0 | direct | ok |
| 14 | 8–14 | jalapeno:Qwen3-Next-80B-A3B-Instruct | off | 264 | 15.3% | [10.6, 20.3] | 96.5% | 78.0% | 75.0% | -3.0% | 0.0% | 6.1% | 0.0 | 5 | 5 | 0 | direct | ok |

## Pre-publish checks

_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | 12.6% | 1.5% | 11.1% |
| nous:meituan/longcat-2.0:free | 11.5% | 2.7% | 8.8% |
| nous:inclusionai/ling-3.0-flash-fin:free | 12.2% | 4.4% | 7.7% |

## Not on the board

- nous:poolside/laguna-s-2.1:free (off): other+abstain 11%: COR flattered, rank by accuracy; familiar with only 80% of item sources

## Items to review (validity flags)

_Human look before publishing; nothing is dropped automatically. Read the traces: a defensible alternative reading means re-pin or drop; a genuine override stays._

| item | override, thinking on | override, thinking off | n on / off | why flagged |
|---|---:|---:|---:|---|
| bear-house-1 | 88.9% | 100.0% | 18 / 55 | overridden by everyone in both modes: very strong prior, or ambiguous |
| married-boat-1 | 66.7% | 30.9% | 18 / 55 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
