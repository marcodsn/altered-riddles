# Altered Riddles v2 — leaderboard

_Generated 2026-09-16T07:22:11Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 2000 draws). Ranks are point estimates, not significant differences; the rank spread counts rows whose pairwise interval excludes zero. Comparisons in the JSON use shared familiar items and jointly resampled clusters (pointwise intervals, not multiplicity-adjusted). Rows must pass scoring and pre-publish checks; Git commitment status is not verified._

| point rank | rank spread | model | thinking | items | COR ↓ | CI95 | orig acc | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | mean out tok | k | pending | familiarity | checks |
|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 1–2 | jalapeno:DeepSeek-V4-Flash-0731 | on | 264 | 1.5% | [0.4, 2.7] | 94.5% | 96.7% | 89.4% | -7.3% | 0.3% | 1.6% | 133.5 | 488 | 3 | 0 | direct | ok |
| 2 | 1–4 | jalapeno:GLM-5.3-Flash | on | 264 | 2.2% | [1.1, 3.8] | 98.8% | 97.0% | 98.8% | 1.8% | 0.0% | 0.8% | 100.0 | 182 | 5 | 0 | thinking | ok |
| 3 | 2–5 | nous:meituan/longcat-2.0:free | on | 264 | 2.7% | [1.3, 4.3] | 97.1% | 95.4% | 83.3% | -12.1% | 0.2% | 1.7% | 133.0 | 326 | 5 | 0 | direct | ok |
| 4 | 2–5 | nous:upstage/solar-pro4:free | on | 264 | 3.1% | [1.3, 5.3] | 96.2% | 95.0% | 97.8% | 2.8% | 0.5% | 1.5% | 572.0 | 1147 | 5 | 0 | direct | ok |
| 5 | 3–6 | nous:inclusionai/ling-3.0-flash-fin:free | on | 264 | 4.4% | [2.5, 6.6] | 90.8% | 91.9% | 93.5% | 1.6% | 0.3% | 3.0% | 189.0 | 419 | 5 | 0 | direct | ok |
| 6 | 5–6 | nous:inclusionai/ling-3.0-flash-sante:free | on | 264 | 5.4% | [3.1, 8.2] | 94.6% | 92.7% | 92.3% | -0.5% | 0.1% | 2.1% | 184.0 | 573 | 5 | 0 | direct | ok |
| 7 | 7–13 | jalapeno:Kimi-K2.5 | off | 264 | 8.6% | [5.5, 12.4] | 97.4% | 88.0% | — | — | 0.0% | 3.6% | 0.0 | 18 | 5 | 0 | direct | ok |
| 8 | 7–15 | jalapeno:Qwen3.5-397B-A17B | off | 264 | 9.9% | [6.6, 13.5] | 96.7% | 85.8% | 81.2% | -4.6% | 0.0% | 4.4% | 0.0 | 5 | 5 | 0 | direct | ok |
| 9 | 7–16 | jalapeno:GLM-5.2 | off | 264 | 10.5% | [6.9, 14.5] | 97.9% | 83.9% | 80.0% | -3.9% | 0.1% | 5.6% | 0.0 | 7 | 5 | 0 | direct | ok |
| 10 | 7–18 | nous:meituan/longcat-2.0:free | off | 264 | 11.5% | [7.6, 15.0] | 97.1% | 83.4% | 76.2% | -7.2% | 0.0% | 5.4% | 0.0 | 7 | 5 | 0 | direct | ok |
| 11 | 7–17 | nous:upstage/solar-pro4:free | off | 264 | 12.0% | [8.1, 15.8] | 96.2% | 81.6% | 78.9% | -2.7% | 0.0% | 6.9% | 0.0 | 7 | 5 | 0 | direct | ok |
| 12 | 8–18 | nous:inclusionai/ling-3.0-flash-fin:free | off | 264 | 12.2% | [8.2, 16.1] | 90.8% | 77.7% | 70.9% | -6.7% | 0.1% | 9.8% | 0.0 | 11 | 5 | 0 | direct | ok |
| 13 | 8–17 | jalapeno:DeepSeek-V4-Pro | off | 264 | 12.2% | [8.4, 15.9] | 95.6% | 83.3% | 78.6% | -4.6% | 0.0% | 5.0% | 0.0 | 9 | 5 | 0 | direct | ok |
| 14 | 7–18 | jalapeno:GLM-5.1 | off | 264 | 12.3% | [8.3, 16.5] | 97.3% | 83.9% | 82.3% | -1.6% | 0.1% | 4.0% | 0.0 | 5 | 5 | 0 | direct | ok |
| 15 | 7–18 | jalapeno:DeepSeek-V4-Flash-0731 | off | 264 | 12.6% | [8.6, 16.9] | 94.5% | 81.1% | 77.0% | -4.1% | 0.0% | 7.0% | 0.0 | 10 | 5 | 0 | direct | ok |
| 16 | 9–18 | jalapeno:Qwen3.5-122B-A10B | off | 264 | 13.9% | [9.6, 18.4] | 95.9% | 82.0% | 79.2% | -2.7% | 0.1% | 4.5% | 0.0 | 6 | 5 | 0 | direct | ok |
| 17 | 10–18 | nous:inclusionai/ling-3.0-flash-sante:free | off | 264 | 14.4% | [10.4, 18.9] | 94.6% | 78.9% | 75.2% | -3.8% | 0.0% | 7.0% | 0.0 | 11 | 5 | 0 | direct | ok |
| 18 | 12–18 | jalapeno:Qwen3-Next-80B-A3B-Instruct | off | 264 | 15.3% | [10.6, 20.3] | 96.5% | 78.0% | 75.0% | -3.0% | 0.0% | 6.1% | 0.0 | 5 | 5 | 0 | direct | ok |

## Pre-publish checks

_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | 12.6% | 1.5% | 11.1% |
| nous:meituan/longcat-2.0:free | 11.5% | 2.7% | 8.8% |
| nous:upstage/solar-pro4:free | 12.0% | 3.1% | 8.8% |
| nous:inclusionai/ling-3.0-flash-fin:free | 12.2% | 4.4% | 7.7% |
| nous:inclusionai/ling-3.0-flash-sante:free | 14.4% | 5.4% | 9.0% |

## Not on the board

- nous:poolside/laguna-s-2.1:free (off): other+abstain 11%: COR flattered, rank by accuracy; familiar with only 80% of item sources
- jalapeno:GLM-5.3 (off): 29% of replies truncated by max_tokens; other+abstain 12%: COR flattered, rank by accuracy; familiar with only 10% of item sources
- jalapeno:Qwen3.5-27B (off): other+abstain 28%: COR flattered, rank by accuracy; familiar with only 38% of item sources
- jalapeno:Qwen3.5-35B-A3B (off): other+abstain 10%: COR flattered, rank by accuracy
- nous:poolside/laguna-xs-2.1:free (off): other+abstain 15%: COR flattered, rank by accuracy; familiar with only 64% of item sources
- nous:poolside/laguna-xs-2.1:free (on): familiar with only 64% of item sources

## Items to review (validity flags)

_Human look before publishing; nothing is dropped automatically. Read the traces: a defensible alternative reading means re-pin or drop; a genuine override stays._

| item | override, thinking on | override, thinking off | n on / off | why flagged |
|---|---:|---:|---:|---|
| bear-house-1 | 93.9% | 97.6% | 33 / 85 | overridden by everyone in both modes: very strong prior, or ambiguous |
| married-boat-1 | 66.7% | 28.2% | 33 / 85 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
