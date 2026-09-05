# Altered Riddles v2 — leaderboard

_Generated 2026-09-05T15:52:27Z. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, 1000 draws). Rows in the same **group** are not distinguishable at 95%. Rows are only listed when every run passed the guardrails and raw outputs are committed under `runs/`._

| group | model | thinking | items | COR ↓ | CI95 | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | k | pending | familiarity | checks |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | jalapeno:DeepSeek-V4-Flash-0731 | on | 40 | 0.0% | [0.0, 0.0] | 95.0% | 95.0% | 0.0% | 0.0% | 2.5% | 141.5 | 1 | 0 | direct | see below |
| 1 | nous:meituan/longcat-2.0:free | on | 40 | 3.5% | [0.0, 7.7] | 95.0% | 95.0% | 0.0% | 0.0% | 1.7% | 146.0 | 3 | 0 | direct | see below |
| 1 | jalapeno:Qwen3.5-35B-A3B | on | 40 | 6.2% | [0.0, 15.6] | 92.5% | 95.0% | 2.5% | 0.0% | 0.8% | 667.0 | 3 | 0 | direct | see below |
| 1 | jalapeno:GLM-5.3-Flash | on | 40 | 6.8% | [0.9, 13.7] | 92.5% | 100.0% | 7.5% | 0.0% | 0.8% | 102.0 | 3 | 0 | thinking | see below |
| 1 | jalapeno:DeepSeek-V4-Flash-0731 | off | 40 | 13.1% | [3.0, 24.5] | 84.2% | 75.0% | -9.2% | 0.0% | 5.0% | 0.0 | 3 | 0 | direct | see below |
| 1 | jalapeno:Qwen3-Next-80B-A3B-Instruct | off | 40 | 15.8% | [5.3, 27.5] | 82.5% | 75.0% | -7.5% | 0.0% | 0.0% | 0.0 | 3 | 0 | direct | see below |
| 1 | nous:meituan/longcat-2.0:free | off | 40 | 19.3% | [8.3, 31.6] | 78.3% | 72.5% | -5.8% | 0.0% | 3.3% | 0.0 | 3 | 0 | direct | see below |
| 1 | jalapeno:Qwen3.5-35B-A3B | off | 40 | 22.9% | [10.8, 37.5] | 75.0% | 70.0% | -5.0% | 0.0% | 6.7% | 0.0 | 3 | 0 | direct | see below |

## Pre-publish checks

- **jalapeno:DeepSeek-V4-Flash-0731 (on)**: 40 rows predate text hashes (item set unverifiable)
- **nous:meituan/longcat-2.0:free (on)**: 40 rows predate text hashes (item set unverifiable)
- **jalapeno:Qwen3.5-35B-A3B (on)**: 40 rows predate text hashes (item set unverifiable)
- **jalapeno:GLM-5.3-Flash (on)**: 40 rows predate text hashes (item set unverifiable)
- **jalapeno:DeepSeek-V4-Flash-0731 (off)**: 40 rows predate text hashes (item set unverifiable)
- **jalapeno:Qwen3-Next-80B-A3B-Instruct (off)**: 40 rows predate text hashes (item set unverifiable)
- **nous:meituan/longcat-2.0:free (off)**: 40 rows predate text hashes (item set unverifiable)
- **jalapeno:Qwen3.5-35B-A3B (off)**: 40 rows predate text hashes (item set unverifiable)

## Thinking gap (COR off minus COR on, same model)

| model | COR off | COR on | gap |
|---|---:|---:|---:|
| jalapeno:DeepSeek-V4-Flash-0731 | 13.1% | 0.0% | 13.1% |
| nous:meituan/longcat-2.0:free | 19.3% | 3.5% | 15.8% |
| jalapeno:Qwen3.5-35B-A3B | 22.9% | 6.2% | 16.7% |

## Not on the board

- jalapeno:GLM-5.3-Flash (off): missing unwarned or original run

## Items to review (validity flags)

_Human look before publishing; nothing is dropped automatically. Read the traces: a defensible alternative reading means re-pin or drop; a genuine override stays._

| item | override, thinking on | override, thinking off | n on / off | why flagged |
|---|---:|---:|---:|---|
| marys-father-1 | 70.0% | 75.0% | 10 / 12 | overridden by everyone in both modes: very strong prior, or ambiguous |
| craw-0007-1 | 60.0% | 16.7% | 10 / 12 | thinking-on override above thinking-off: reasoning finds an alternative reading? |
