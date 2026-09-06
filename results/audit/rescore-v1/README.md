# Re-score of the Tier-0 runs after the matcher fix (2026-09-06)

**Why.** The deterministic matcher's "longer matched alias wins" tie-break (matcher v1,
2026-09-05) labelled correct replies as overrides whenever the reply quoted an original
justification phrase, e.g. "Three apples (the two you took plus the one in your pocket)"
(the original alias "the two you took" is longer than "three apples"). Simulated over the
ten altered Tier-0 runs (12,236 scored rows) the tie-break decided 164 rows: 39 labelled
`original`, 125 labelled `correct`. Matcher v2 sends every mixed reply to the judge; the
exact-match tie-break ("$1.05" vs ".05") stays. Regression tests: `tests/test_match.py`.

**What changes on disk.** `scored.jsonl` and `scored_summary.json` in every run directory
are rewritten from the unchanged `raw.jsonl`. Raw outputs, configs, judge caches and the
pre-fix scores (git `6c568ce`) are preserved. Scored rows now carry the raw sample's
`text_sha`; summaries carry per-item fingerprints (text, answer, aliases, original
answer/aliases), the matcher version, code hashes, the judge spec and judge-prompt hash.

**Judge calls.** Only rows without a cached verdict are sent: the newly mixed rows
(≤ 164) on `jalapeno:DeepSeek-V4-Flash-0731`, thinking off, temperature 0, max 8 output
tokens, ~300 input tokens each.

Price evidence: PLAN.md section 6, Jalapeno marketplace prices pasted by the owner on
2026-09-04: DeepSeek-V4-Flash-0731 USD 0.088 / M input, 0.264 / M output. Worst case
164 × 400 tokens ≈ 66k tokens ≈ USD 0.006 including retries (8 retries max per call:
≤ USD 0.05). Envelope for this phase: USD 1. No other provider is called.

Actual calls and outcomes are appended below after the run.

## Outcome (run 2026-09-06)

- Judge calls made: **161** (rows without a cached verdict), 0 errors, on
  `jalapeno:DeepSeek-V4-Flash-0731`. Estimated cost ≈ USD 0.006 (no receipt; the
  provider API exposes no per-call cost).
- Rows compared old vs new on the 264 current items: **45 labels changed**:
  35 `original → correct`, 2 `original → other`, 7 `correct → other`,
  1 `correct → original`. Per-row detail: `label_changes.jsonl`.
- Blind check sheet for the owner: `label_changes_sheet.yaml` (45 rows, all judge-decided,
  machine labels withheld). These are the rows to hand-label; nothing else in this
  re-score needs a human pass.
- Board rebuilt (`results/v2/`), audit snapshot `results/audit/core-hard-v3/`. All five
  Tier-0 rows pass the new provenance checks (matcher version, per-item fingerprints,
  familiarity fingerprint). COR before → after:

| row | COR before | COR after | alt acc before | after |
|---|---:|---:|---:|---:|
| DeepSeek-V4-Flash-0731, thinking on | 2.0 | 2.0 | 96.6 | 96.6 |
| GLM-5.3-Flash, thinking on | 4.2 | 3.8 | 94.9 | 95.3 |
| longcat-2.0 (free), thinking on | 4.7 | 4.7 | 93.6 | 93.6 |
| longcat-2.0 (free), thinking off | 12.6 | 12.0 | 82.4 | 83.0 |
| DeepSeek-V4-Flash-0731, thinking off | 13.3 | 12.8 | 80.9 | 81.1 |

Point ranks are unchanged. The direction of the correction is the expected one: the
dropped tie-break mostly inflated overrides on thinking-off rows.
