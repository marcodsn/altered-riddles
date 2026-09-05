# Altered Riddles v2 — leaderboard

_Generated 2026-09-05T21:20:28Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 2000 draws). Rows in the same **group** are not distinguishable at 95%. Rows are only listed when every run passed the guardrails and raw outputs are committed under `runs/`._

| group | model | thinking | items | COR ↓ | CI95 | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | k | pending | familiarity | checks |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | jalapeno:DeepSeek-V4-Flash-0731 | on | 266 | 2.8% | [1.2, 4.7] | 95.9% | 94.0% | -1.9% | 0.0% | 1.5% | 136.0 | 3 | 0 | direct | ok |
| 1 | jalapeno:GLM-5.3-Flash | on | 266 | 4.9% | [2.8, 7.0] | 94.2% | 98.6% | 4.4% | 0.0% | 0.9% | 100.0 | 5 | 0 | thinking | ok |
| 1 | nous:meituan/longcat-2.0:free | on | 266 | 5.4% | [3.3, 7.8] | 92.9% | 93.0% | 0.1% | 0.0% | 1.8% | 130.5 | 5 | 0 | direct | ok |
| 2 | nous:meituan/longcat-2.0:free | off | 266 | 13.2% | [9.5, 17.1] | 81.8% | 74.7% | -7.1% | 0.0% | 5.3% | 0.0 | 5 | 0 | direct | ok |
| 2 | jalapeno:DeepSeek-V4-Flash-0731 | off | 266 | 13.9% | [9.8, 18.5] | 80.3% | 75.9% | -4.4% | 0.0% | 6.5% | 0.0 | 5 | 0 | direct | ok |

## Pre-publish checks

_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | 13.9% | 2.8% | 11.2% |
| nous:meituan/longcat-2.0:free | 13.2% | 5.4% | 7.8% |

## Items to review (validity flags)

_Human look before publishing; nothing is dropped automatically. Read the traces: a defensible alternative reading means re-pin or drop; a genuine override stays._

| item | override, thinking on | override, thinking off | n on / off | why flagged |
|---|---:|---:|---:|---|
| cowboy-friday-2 | 100.0% | 100.0% | 13 / 10 | overridden by everyone in both modes: very strong prior, or ambiguous |
| greenhouse-3 | 100.0% | 100.0% | 13 / 10 | overridden by everyone in both modes: very strong prior, or ambiguous |
| mustard-family-3 | 92.3% | 70.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| bear-house-1 | 84.6% | 100.0% | 13 / 10 | overridden by everyone in both modes: very strong prior, or ambiguous |
| months-28-days-1 | 76.9% | 100.0% | 13 / 10 | overridden by everyone in both modes: very strong prior, or ambiguous |
| married-boat-1 | 76.9% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| marys-father-1 | 61.5% | 60.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| johnnys-mother-1 | 46.2% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| yellow-hat-1 | 38.5% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| hiccups-1 | 38.5% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| parachute-1 | 38.5% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
| last-brick-2 | 30.8% | 0.0% | 13 / 10 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
