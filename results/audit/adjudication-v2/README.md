# Owner adjudication + prospective Core repairs (2026-09-09)

**Steps 1–4 complete. Current board: `core-board-scorer-v2/LEADERBOARD.md`.**
Development artifacts, not a frozen release. Historical `data/gated.jsonl`, item
files, raw runs, and `results/v2` remain unchanged. `core-board/` and `repairs-board/`
are superseded intermediate outputs and must not be used for current claims.

## Decisions and provenance

- `decisions.json`: 12 disputed-item decisions: four keep, eight revise-and-rerun.
  The original 11-item sheet was owner-authored. Months, hiccups, parachute and
  rooster were amended following AI advice and explicit owner approval in chat.
  Cat was separately approved in chat. Approval does not imply an independent
  human validity study. Recording timestamps are not invented review dates.
- `data/revisions/core-approved-v1.yaml`: exactly the eight approved repairs,
  each with a new `-r1` ID and `replaces` link. Last brick stays unchanged per the
  owner decision. The six-item historical pilot remains byte-for-byte intact;
  cat's new standalone draft is `data/revisions/cat-fur-v1.yaml`.
- `label_audit.json`: the legacy field named `human_label` contains 43 AI blind
  judgments, one unchanged owner label (n=1), and one AI-recommended correction
  explicitly approved by the owner (n=0). Mixed-provenance agreement with the
  re-score judge is 32/45 (71.1%); 13 disagreements remain. This is NOT a 45-row
  independent human audit. No historical judge labels are silently overwritten.
- `offline_validation.json`: explicit AI validity review plus schema, source,
  ID-isolation and normalized alias-overlap checks. Model votes are advisory;
  gate reasoning must be inspected before fresh evaluation.

## Execution and budget

`routes.json` records a fresh read-only catalog check. Existing four Jalapeno
gate models and the three Tier-0 model routes are retained. Nous longcat is
catalog-priced zero for input and output. Jalapeno prices are the owner's
2026-09-04 prices in PLAN section 6; the current catalog has no live pricing.

`execute.py` reserves each dispatched call's conservative ceiling, including
reasoning, against USD 1. USD .05 is reserved for earlier phase work. Failed or
unknown usage retains the ceiling; reported usage is a conservative estimate,
not a receipt. One attempt per call; no fallback; unchanged inference prompts,
temperatures, caps, gate thresholds and Tier-0 sample counts. Concurrency 4,
RPM 60, Nous owner request tag included. Queued requests wait outside budget
reservation. Request and reservation evidence is persisted in `budget.json`.

The first gate attempt exposed a reservation bug: it reserved queued calls
before their dispatch semaphore. It stopped before any response completed.
`attempt1-*` preserves that attempt. Four potentially in-flight calls retain
their entire ceilings (USD .13100965). The other 27 reservations were provably
waiting behind the shared four-slot semaphore and never dispatched, so they
were released with an explicit ledger explanation. The fixed path reserves
only dispatch slots; an offline concurrency regression test covers this.
The retry uses the same four routes and preserves the failed attempt evidence.

## Commands and artifacts

Run from repository root with `.venv/bin/python`:

```sh
# Offline snapshot preparation: refuses to overwrite existing snapshots.
.venv/bin/python results/audit/adjudication-v2/prepare.py
.venv/bin/python results/audit/adjudication-v2/execute.py offline
.venv/bin/python -m unittest discover -s tests -v

# Versioned gate + original-answer invalidation probe.
.venv/bin/python -u results/audit/adjudication-v2/execute.py gate
# Inspect gate replies and record gate_reasoning_review.json (AI-labelled).
.venv/bin/python -u results/audit/adjudication-v2/execute.py evaluate

# Offline-only composition with explicit run lineage and a no-inference guard.
.venv/bin/python results/audit/adjudication-v2/rebuild.py
```

`execution_status.json` gives execution progress/blockers. Fresh outputs belong
under `runs/core-repairs-v1/`; composed candidate runs under
`runs/core-candidate-v1/`. Each composed raw sample points to its original or
fresh source run. Only unchanged item texts may use old outputs; repaired IDs
and familiarity for repaired sources require fresh outputs. Explicit manifests
select inputs; no directory-order selection. Candidate boards, if built, stay
under this audit directory and include the open label-audit warning.

## Outcome and scoring correction

- Eight repairs passed all 64 gate/probe replies. Fresh Tier-0 evaluation completed
  488 responses across 13 configurations, with zero API errors. There were 14
  token-cap stops, including 11/40 Longcat warned thinking-on repair responses;
  all are retained without resampling. See `truncations.json`.
- Final audit found 12 empty fresh answers labelled correct by the judge, plus
  a truncated reasoning passage treated as an original answer. Scorer v2 now
  deterministically labels empty replies abstain, rejects reasoning-only truncated
  replies, and allows nontruncated reasoning fallback only for a standalone
  terminal Answer line. Boards require the new scorer version for altered and
  familiarity scores, so stale outputs fail closed. Matcher remains v2.
- `rescore_empty_v1.py` corrected fresh and composed scores with an explicit
  no-inference client. New directories are `runs/core-repairs-scored-v2/` and
  `runs/core-candidate-scored-v2/`. Every copied raw file has its source hash.
  The fresh slice has 13 label corrections. The composed candidate has 202 label
  corrections (179 correct, 19 other and 4 original to abstain), plus one
  answer-text-only correction. Familiarity rates did not change in this rescoring.
  Full detail: `scorer_v2_correction.json`.
- Current explicit manifests: `fresh_run_manifest_scorer_v2.json` and
  `candidate_run_manifest_scorer_v2.json`. The 264-item full candidate has five
  rows passing existing aggregate checks; no exclusions. The repair-only board
  excludes both DeepSeek rows for other+abstain rates above its 10% guardrail.
  Aggregate checks do not erase the Longcat warned truncation concern.
- Successful calls: 64 gate/probe + 488 evaluation + 34 judge = 586.
  Final conservative ledger: USD .565084178, including USD .05 prior-work reserve
  and USD .13100965 retained for interrupted calls. Not a billing receipt.
  The scorer correction used **zero additional API calls**.
- 39 offline tests pass; `git diff --check` passes. All 84 historical-file hashes
  match the pre-execution snapshot. Raw runs and historical boards are untouched.

Do not freeze Core, publish, infer established ranks, or claim the label audit
is resolved merely because the gates or candidate board pass. Next: resolve the
13 mixed-provenance label disagreements, assess cap sensitivity, predeclare the
comparison policy, and perform final release checks. No release is authorized.
