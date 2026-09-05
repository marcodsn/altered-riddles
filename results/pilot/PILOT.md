# Pilot (M3) — 40 items, 5 Tier-0 models, 2026-09-04

Items: 40 gate-passed items over 37 sources, stratified by type (19 hard_constraint,
8 question_swap, 6 negated_premise, 4 trivialized, 3 stated). Conditions: `original`
(familiarity, k=5), `unwarned` (k=3; k=1 for DeepSeek thinking-on), `warned` (k=1).
Judge: DeepSeek-V4-Flash-0731, thinking off. Raw outputs under `runs/pilot/`.

## Acceptance checks (PLAN.md M3)

| check | target | result |
|---|---|---|
| deterministic alias coverage | ≥ 70% | 82–100% per run; the judge saw 0–9 rows per run |
| guardrail trips on a fake thinking run | must FAIL | "thinking on" on Qwen3-Next-Instruct (no thinking mode) → FAIL, median reasoning tokens 0 |
| error rate | ≤ 5% | 0% on every scored run; GLM-5.3-Flash's thinking-off familiarity run failed 100% because the switch is unsupported, redone in thinking mode and labelled `familiarity: thinking` |
| judge vs human agreement | ≥ 95% on 100 answers | **pending Marco**: `results/pilot/labeling_sheet_judge_only.jsonl`, the 61 answers the judge actually decided, blind (machine labels in the `.key.jsonl`); the earlier 100-row sheet was 92% alias matches |
| "neither" (other) share, H5 | ≤ 10% | 0–7% (v1: 29%) |
| thinking length for pricing | measured | see PLAN.md section 6; unwarned thinking is 100–700 tokens median, warned 2–4× longer |

## What the 40 items already show

- **Thinking gap is the headline.** For every model that has both modes, COR drops from
  13–23% (thinking off) to 0–7% (thinking on): DeepSeek 13.1→0.0, longcat 19.3→3.5,
  Qwen3.5-35B 22.9→6.2. H3 (≥ 8 points on ≥ 4 of 5 models) is on track.
- **The warning does not help; for thinking-off models it hurts.** Warned minus unwarned
  accuracy is −5 to −9 points with thinking off and 0 to +7.5 with thinking on. H2
  predicted ≥ +15; the pilot says the sign is wrong for the models that override most.
  The likely reading: told "the usual answer may be wrong", a non-thinking model
  abandons the (now correct) literal reading too. This is a finding, not a bug.
- **The items are clean.** Unwarned accuracy is 75–95% and the `other` bucket is under
  7%, against v1's 20–43% and 29%. When a model is wrong it gives the *original*
  answer: the override is the failure mode, as designed.
- **Ceiling for thinking models.** Thinking-on rows sit at 92–95% accuracy and 0–7% COR
  with overlapping CIs; on 40 items they cannot be separated (one rank group). H1 needs
  the full item count and, if the ceiling holds at n=119, harder or more items. The
  thinking-off rows spread from 13% to 23% and will separate first.
- **Deterministic scoring works.** The exact-match and longest-match tie-breaks resolved
  the alias overlaps the gate found; the judge handled 1–9 rows per run.

## Operational lessons

- DeepSeek-V4-Flash-0731 reasons at ~10 tok/s here and the provider drops very long
  connections; run it alone with high concurrency, short retries, and expect wall-clock.
- GLM-5.3-Flash cannot switch thinking off on Jalapeno; it only gets a thinking-on row.
- The provider's per-tenant RPM limit bites on the tiny probe calls, not on thinking
  calls; `--rpm` handles it.
