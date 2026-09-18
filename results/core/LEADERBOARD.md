# Altered Riddles v2 — leaderboard

_Generated 2026-09-18T19:03:43Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 2000 draws). Ranks are point estimates, not significant differences; the rank spread counts rows whose pairwise interval excludes zero. Comparisons in the JSON use shared familiar items and jointly resampled clusters (pointwise intervals, not multiplicity-adjusted). Rows must pass scoring and pre-publish checks; Git commitment status is not verified._

| point rank | rank spread | model | thinking | items | COR ↓ | CI95 | orig acc | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | mean out tok | k | pending | familiarity | checks |
|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 1–6 | jalapeno:GLM-5.3 | on | 264 | 1.2% | [0.3, 2.5] | 93.4% | 98.0% | 97.3% | -0.6% | 0.1% | 0.6% | 119.0 | 280 | 3 | 0 | direct | ok |
| 2 | 1–6 | jalapeno:DeepSeek-V4-Flash-0731 | on | 264 | 1.5% | [0.4, 2.7] | 94.5% | 96.7% | 89.4% | -7.3% | 0.3% | 1.6% | 133.5 | 488 | 3 | 0 | direct | ok |
| 3 | 1–7 | jalapeno:Qwen3.5-397B-A17B | on | 264 | 1.7% | [0.5, 3.2] | 96.7% | 97.6% | 92.8% | -4.8% | 0.0% | 0.8% | 529.5 | 1176 | 3 | 0 | direct | ok |
| 4 | 1–8 | jalapeno:Qwen3.5-122B-A10B | on | 264 | 1.8% | [0.5, 3.4] | 95.9% | 97.0% | 97.0% | 0.0% | 0.0% | 1.0% | 638.5 | 1123 | 3 | 0 | direct | ok |
| 5 | 2–9 | jalapeno:GLM-5.3-Flash | on | 264 | 2.2% | [1.1, 3.8] | 98.8% | 97.0% | 98.8% | 1.8% | 0.0% | 0.8% | 100.0 | 182 | 5 | 0 | thinking | ok |
| 6 | 1–10 | jalapeno:Qwen3.5-35B-A3B | on | 264 | 2.6% | [1.0, 4.5] | 93.3% | 95.6% | 94.7% | -0.9% | 0.0% | 1.9% | 644.0 | 1263 | 3 | 0 | direct | ok |
| 7 | 3–11 | nous:meituan/longcat-2.0:free | on | 264 | 2.7% | [1.3, 4.3] | 97.1% | 95.4% | 83.3% | -12.1% | 0.2% | 1.7% | 133.0 | 326 | 5 | 0 | direct | ok |
| 8 | 3–11 | nous:upstage/solar-pro4:free | on | 264 | 3.1% | [1.3, 5.3] | 96.2% | 95.0% | 97.9% | 2.9% | 0.5% | 1.5% | 567.5 | 1151 | 5 | 0 | direct | ok |
| 9 | 6–12 | jalapeno:DeepSeek-V4-Pro | on | 264 | 4.1% | [2.1, 6.5] | 95.6% | 94.9% | 95.5% | 0.5% | 0.0% | 1.1% | 132.0 | 311 | 3 | 0 | direct | ok |
| 10 | 6–12 | jalapeno:Qwen3-Next-80B-A3B-Thinking | on | 264 | 4.3% | [2.0, 6.8] | 93.9% | 93.3% | 95.1% | 1.8% | 0.0% | 2.1% | 744.0 | 1207 | 3 | 0 | thinking | ok |
| 11 | 6–12 | nous:inclusionai/ling-3.0-flash-fin:free | on | 264 | 4.4% | [2.5, 6.6] | 90.8% | 91.9% | 93.6% | 1.7% | 0.4% | 3.0% | 187.0 | 429 | 5 | 0 | direct | ok |
| 12 | 9–12 | nous:inclusionai/ling-3.0-flash-sante:free | on | 264 | 5.3% | [3.0, 8.1] | 94.6% | 92.9% | 92.3% | -0.5% | 0.0% | 2.1% | 182.0 | 556 | 5 | 0 | direct | ok |
| 13 | 13–19 | jalapeno:Kimi-K2.5 | off | 264 | 8.6% | [5.4, 12.1] | 97.4% | 88.0% | 73.2% | -14.8% | 0.0% | 3.6% | 0.0 | 18 | 5 | 0 | direct | ok |
| 14 | 13–20 | jalapeno:Qwen3.5-397B-A17B | off | 264 | 9.8% | [6.6, 13.4] | 96.7% | 85.9% | 81.1% | -4.8% | 0.0% | 4.4% | 0.0 | 5 | 5 | 0 | direct | ok |
| 15 | 13–21 | jalapeno:GLM-5.2 | off | 264 | 10.6% | [7.0, 14.6] | 97.9% | 83.9% | 80.1% | -3.9% | 0.1% | 5.5% | 0.0 | 7 | 5 | 0 | direct | ok |
| 16 | 13–23 | nous:meituan/longcat-2.0:free | off | 264 | 11.5% | [7.6, 15.0] | 97.1% | 83.4% | 76.2% | -7.2% | 0.0% | 5.4% | 0.0 | 7 | 5 | 0 | direct | ok |
| 17 | 13–22 | nous:upstage/solar-pro4:free | off | 264 | 12.0% | [8.2, 15.7] | 96.2% | 81.6% | 78.8% | -2.8% | 0.0% | 6.9% | 0.0 | 7 | 5 | 0 | direct | ok |
| 18 | 14–22 | jalapeno:DeepSeek-V4-Pro | off | 264 | 12.3% | [8.6, 16.3] | 95.6% | 83.3% | 78.6% | -4.7% | 0.0% | 4.9% | 0.0 | 9 | 5 | 0 | direct | ok |
| 19 | 13–23 | jalapeno:GLM-5.1 | off | 264 | 12.5% | [8.6, 16.7] | 97.3% | 83.7% | 82.3% | -1.4% | 0.1% | 4.0% | 0.0 | 5 | 5 | 0 | direct | ok |
| 20 | 13–23 | jalapeno:DeepSeek-V4-Flash-0731 | off | 264 | 12.6% | [8.6, 16.9] | 94.5% | 81.1% | 77.0% | -4.1% | 0.0% | 7.0% | 0.0 | 10 | 5 | 0 | direct | ok |
| 21 | 15–23 | jalapeno:Qwen3.5-122B-A10B | off | 264 | 13.9% | [9.6, 18.4] | 95.9% | 82.0% | 79.2% | -2.8% | 0.1% | 4.5% | 0.0 | 6 | 5 | 0 | direct | ok |
| 22 | 16–23 | nous:inclusionai/ling-3.0-flash-sante:free | off | 264 | 14.2% | [10.2, 18.7] | 94.6% | 79.2% | 75.3% | -3.9% | 0.0% | 7.0% | 0.0 | 11 | 5 | 0 | direct | ok |
| 23 | 18–23 | jalapeno:Qwen3-Next-80B-A3B-Instruct | off | 264 | 15.3% | [10.6, 20.3] | 96.5% | 78.0% | 75.0% | -3.0% | 0.0% | 6.1% | 0.0 | 5 | 5 | 0 | direct | ok |

## Pre-publish checks

_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | 12.6% | 1.5% | 11.1% |
| jalapeno:Qwen3.5-397B-A17B | 9.8% | 1.7% | 8.1% |
| jalapeno:Qwen3.5-122B-A10B | 13.9% | 1.8% | 12.1% |
| nous:meituan/longcat-2.0:free | 11.5% | 2.7% | 8.8% |
| nous:upstage/solar-pro4:free | 12.0% | 3.1% | 8.8% |
| jalapeno:DeepSeek-V4-Pro | 12.3% | 4.1% | 8.2% |
| nous:inclusionai/ling-3.0-flash-sante:free | 14.2% | 5.3% | 8.9% |

## Not on the board

- nous:poolside/laguna-s-2.1:free (off): other+abstain 12%: COR flattered, rank by accuracy; familiar with only 80% of item sources
- nous:inclusionai/ling-3.0-flash-fin:free (off): other+abstain 10%: COR flattered, rank by accuracy
- jalapeno:GLM-5.3 (off): 30% of replies truncated by max_tokens; other+abstain 12%: COR flattered, rank by accuracy
- jalapeno:Qwen3.5-27B (off): other+abstain 28%: COR flattered, rank by accuracy; familiar with only 38% of item sources
- jalapeno:Qwen3.5-35B-A3B (off): other+abstain 10%: COR flattered, rank by accuracy
- nous:poolside/laguna-xs-2.1:free (off): other+abstain 15%: COR flattered, rank by accuracy; familiar with only 64% of item sources
- nous:poolside/laguna-xs-2.1:free (on): familiar with only 64% of item sources
- jalapeno:Kimi-K2.5 (on): guardrail failed: unwarned: thinking requested but median reasoning tokens = 0.0; warned: thinking requested but median reasoning tokens = 0.0

## Items to review (validity flags)

_Human look before publishing; nothing is dropped automatically. Read the traces: a defensible alternative reading means re-pin or drop; a genuine override stays._

| item | override, thinking on | override, thinking off | n on / off | why flagged |
|---|---:|---:|---:|---|
| bear-house-1 | 82.4% | 97.6% | 51 / 85 | overridden by everyone in both modes: very strong prior, or ambiguous |
| married-boat-1 | 58.8% | 28.2% | 51 / 85 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
