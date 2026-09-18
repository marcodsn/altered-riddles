# Altered Riddles v2 — leaderboard

_Generated 2026-09-18T16:06:47Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 2000 draws). Ranks are point estimates, not significant differences; the rank spread counts rows whose pairwise interval excludes zero. Comparisons in the JSON use shared familiar items and jointly resampled clusters (pointwise intervals, not multiplicity-adjusted). Rows must pass scoring and pre-publish checks; Git commitment status is not verified._

| point rank | rank spread | model | thinking | items | COR ↓ | CI95 | orig acc | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | mean out tok | k | pending | familiarity | checks |
|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 1–5 | jalapeno:DeepSeek-V4-Flash-0731 | on | 264 | 2.0% | [0.8, 3.5] | 94.5% | 96.5% | 89.3% | -7.2% | 0.1% | 1.5% | 136.0 | 526 | 3 | 0 | direct | ok |
| 2 | 1–6 | jalapeno:GLM-5.3 | on | 264 | 2.2% | [0.9, 3.9] | 93.4% | 96.7% | 97.3% | 0.6% | 0.1% | 0.6% | 120.5 | 310 | 3 | 0 | direct | ok |
| 3 | 1–7 | jalapeno:Qwen3.5-397B-A17B | on | 264 | 3.4% | [1.6, 5.6] | 96.7% | 96.0% | 92.8% | -3.2% | 0.0% | 0.8% | 530.0 | 1225 | 3 | 0 | direct | ok |
| 4 | 1–10 | jalapeno:Qwen3.5-122B-A10B | on | 264 | 3.7% | [1.6, 6.0] | 95.9% | 95.3% | 96.6% | 1.3% | 0.0% | 1.1% | 638.5 | 1153 | 3 | 0 | direct | ok |
| 5 | 3–10 | jalapeno:GLM-5.3-Flash | on | 264 | 3.8% | [2.1, 5.8] | 98.8% | 95.3% | 98.8% | 3.5% | 0.0% | 0.9% | 100.0 | 184 | 5 | 0 | thinking | ok |
| 6 | 1–10 | jalapeno:Qwen3.5-35B-A3B | on | 264 | 4.0% | [1.8, 6.6] | 93.3% | 94.1% | 94.3% | 0.3% | 0.0% | 1.8% | 652.0 | 1297 | 3 | 0 | direct | ok |
| 7 | 2–10 | nous:upstage/solar-pro4:free | on | 264 | 4.6% | [2.4, 7.1] | 96.2% | 93.5% | 97.7% | 4.2% | 0.5% | 1.5% | 574.5 | 1190 | 5 | 0 | direct | ok |
| 8 | 4–11 | nous:meituan/longcat-2.0:free | on | 264 | 4.7% | [2.7, 6.7] | 97.1% | 93.5% | 83.3% | -10.2% | 0.4% | 1.6% | 130.5 | 373 | 5 | 0 | direct | ok |
| 9 | 4–11 | jalapeno:DeepSeek-V4-Pro | on | 264 | 5.7% | [3.4, 8.3] | 95.6% | 93.4% | 95.5% | 2.0% | 0.0% | 1.1% | 132.5 | 325 | 3 | 0 | direct | ok |
| 10 | 4–12 | nous:inclusionai/ling-3.0-flash-fin:free | on | 264 | 6.0% | [3.7, 8.6] | 90.8% | 90.6% | 92.7% | 2.0% | 0.3% | 3.0% | 191.0 | 422 | 5 | 0 | direct | ok |
| 11 | 8–12 | nous:inclusionai/ling-3.0-flash-sante:free | on | 264 | 6.7% | [4.1, 9.8] | 94.6% | 91.4% | 92.0% | 0.5% | 0.0% | 2.3% | 186.0 | 572 | 5 | 0 | direct | ok |
| 12 | 10–18 | jalapeno:Kimi-K2.5 | off | 264 | 9.4% | [6.3, 12.8] | 97.4% | 86.9% | 71.7% | -15.2% | 0.0% | 3.9% | 0.0 | 17 | 5 | 0 | direct | ok |
| 13 | 12–20 | jalapeno:Qwen3.5-397B-A17B | off | 264 | 11.1% | [7.4, 15.0] | 96.7% | 84.5% | 80.9% | -3.6% | 0.0% | 4.5% | 0.0 | 5 | 5 | 0 | direct | ok |
| 14 | 12–21 | jalapeno:GLM-5.2 | off | 264 | 11.8% | [7.8, 16.0] | 97.9% | 82.6% | 78.9% | -3.6% | 0.1% | 5.7% | 0.0 | 7 | 5 | 0 | direct | ok |
| 15 | 12–21 | nous:meituan/longcat-2.0:free | off | 264 | 12.0% | [8.3, 15.7] | 97.1% | 83.0% | 75.5% | -7.4% | 0.0% | 5.3% | 0.0 | 8 | 5 | 0 | direct | ok |
| 16 | 12–22 | nous:upstage/solar-pro4:free | off | 264 | 12.8% | [8.6, 16.8] | 96.2% | 81.1% | 78.5% | -2.6% | 0.0% | 6.7% | 0.0 | 7 | 5 | 0 | direct | ok |
| 17 | 12–23 | jalapeno:DeepSeek-V4-Flash-0731 | off | 264 | 12.8% | [8.8, 17.1] | 94.5% | 81.1% | 76.7% | -4.4% | 0.0% | 6.8% | 0.0 | 11 | 5 | 0 | direct | ok |
| 18 | 12–23 | jalapeno:GLM-5.1 | off | 264 | 13.4% | [9.3, 17.9] | 97.3% | 82.7% | 81.3% | -1.4% | 0.1% | 4.2% | 0.0 | 5 | 5 | 0 | direct | ok |
| 19 | 13–23 | jalapeno:DeepSeek-V4-Pro | off | 264 | 13.5% | [9.6, 17.7] | 95.6% | 82.2% | 78.0% | -4.2% | 0.0% | 4.8% | 0.0 | 9 | 5 | 0 | direct | ok |
| 20 | 13–23 | nous:inclusionai/ling-3.0-flash-fin:free | off | 264 | 13.6% | [9.6, 18.0] | 90.8% | 76.4% | 69.8% | -6.6% | 0.1% | 9.8% | 0.0 | 11 | 5 | 0 | direct | ok |
| 21 | 14–23 | jalapeno:Qwen3.5-122B-A10B | off | 264 | 14.9% | [10.4, 19.8] | 95.9% | 80.9% | 78.6% | -2.3% | 0.1% | 4.8% | 0.0 | 6 | 5 | 0 | direct | ok |
| 22 | 16–23 | nous:inclusionai/ling-3.0-flash-sante:free | off | 264 | 15.2% | [11.1, 19.4] | 94.6% | 78.1% | 74.2% | -3.9% | 0.0% | 7.0% | 0.0 | 12 | 5 | 0 | direct | ok |
| 23 | 17–23 | jalapeno:Qwen3-Next-80B-A3B-Instruct | off | 264 | 16.1% | [11.1, 21.3] | 96.5% | 77.3% | 74.2% | -3.0% | 0.0% | 6.1% | 0.0 | 5 | 5 | 0 | direct | ok |

## Pre-publish checks

_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | 12.8% | 2.0% | 10.8% |
| jalapeno:Qwen3.5-397B-A17B | 11.1% | 3.4% | 7.6% |
| jalapeno:Qwen3.5-122B-A10B | 14.9% | 3.7% | 11.2% |
| nous:upstage/solar-pro4:free | 12.8% | 4.6% | 8.1% |
| nous:meituan/longcat-2.0:free | 12.0% | 4.7% | 7.4% |
| jalapeno:DeepSeek-V4-Pro | 13.5% | 5.7% | 7.8% |
| nous:inclusionai/ling-3.0-flash-fin:free | 13.6% | 6.0% | 7.7% |
| nous:inclusionai/ling-3.0-flash-sante:free | 15.2% | 6.7% | 8.5% |

## Not on the board

- jalapeno:GLM-5.3 (off): 30% of replies truncated by max_tokens; other+abstain 12%: COR flattered, rank by accuracy
- jalapeno:Kimi-K2.5 (on): guardrail failed: unwarned: thinking requested but median reasoning tokens = 0.0; warned: thinking requested but median reasoning tokens = 0.0
- jalapeno:Qwen3-Next-80B-A3B-Thinking (off): missing unwarned or original run
- jalapeno:Qwen3-Next-80B-A3B-Thinking (on): incomplete/invalid scoring: 1 rows failed with API errors (retryable: resume the run); 0 missing items, 0 missing samples, 0 unexpected samples, 0 duplicate samples
- jalapeno:Qwen3.5-27B (off): other+abstain 28%: COR flattered, rank by accuracy; familiar with only 38% of item sources
- jalapeno:Qwen3.5-35B-A3B (off): other+abstain 11%: COR flattered, rank by accuracy
- nous:poolside/laguna-s-2.1:free (off): other+abstain 12%: COR flattered, rank by accuracy; familiar with only 80% of item sources
- nous:poolside/laguna-xs-2.1:free (off): other+abstain 15%: COR flattered, rank by accuracy; familiar with only 64% of item sources
- nous:poolside/laguna-xs-2.1:free (on): familiar with only 64% of item sources
- nous:stepfun/step-3.7-flash:free (on): guardrail failed: unwarned: error rate 16.1%; warned: error rate 53.9%

## Items to review (validity flags)

_Human look before publishing; nothing is dropped automatically. Read the traces: a defensible alternative reading means re-pin or drop; a genuine override stays._

| item | override, thinking on | override, thinking off | n on / off | why flagged |
|---|---:|---:|---:|---|
| mustard-family-3 | 89.6% | 71.8% | 48 / 85 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| bear-house-1 | 81.2% | 97.6% | 48 / 85 | overridden by everyone in both modes: very strong prior, or ambiguous |
| marys-father-1 | 70.8% | 77.6% | 48 / 85 | overridden by everyone in both modes: very strong prior, or ambiguous |
| hiccups-1 | 58.3% | 32.9% | 48 / 85 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| married-boat-1 | 56.2% | 28.2% | 48 / 85 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| johnnys-mother-1 | 41.7% | 18.8% | 48 / 85 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
