# Scoped Astra AI adjudication v1

**Development evidence, not a release.** Actual runtime model for assessment and
challenge: **openai-codex/gpt-6-astra**, subscription-backed native Pi subagents.
Not paid Nous Astra inference, human review or independent empirical validation.
This selected packet is not a representative sample of judge accuracy. The first
assessment did not inspect prior labels/aggregates; it did see supplied answers.
The challenge read that assessment and was not blinded. Available final review
artifacts are copied verbatim from managed paths, with hashes in `review_evidence.json`.
No full API transcript or additional human review is fabricated.

## Decisions and scope

15 resolved: **0 correct, 5 original, 10 other, 0 abstain, 0 unresolved**.
The supervisor approved the scoped commitment interpretation and the challenge's
historical-18 and historical-32 corrections to `other`. See `assessment.md`,
`challenge.md`, `approved_dispositions.json` and the
[policy amendment](../../../docs/CORE_RELEASE_POLICY_AMENDMENT_ASTRA_V1.md).
No generic scorer/matcher/rubric code changed. Remaining interpretation sensitivity
and item-validity concerns are retained per case, not silently turned into exclusions.

All **13 historical cases** have identical current item fields, final answers and
raw sample identities: **zero historical-only cases**. Each current sample's lineage
maps to its original raw run. Twelve current labels change, one is confirmed:

| Historical base judge → adjudicated | Count |
|---|---:|
| correct → other | 7 |
| correct → original | 2 |
| other → original | 3 |
| other → other (historical-32) | 1 |

Relative to the earlier mixed-provenance review labels: 11 agree, one other→original
and one correct→other. Historical sheets, scored files and input packets are not
rewritten. The two cap cases each change pending→other, separately. Thus **14 actual
label changes across 15 decisions**, not 15 changed labels or a fresh judge panel.

`decisions.json` binds every decision to the exact final answer and its SHA-256,
item fingerprint/full grading-field SHA-256, item-file hash, run/sample, raw-file
and raw-row hashes, scored-file and scored-row hashes, and current sample lineage.
Labels are never transferred to changed text. Preflight raises an exact case error
before writing any derivatives if any checked binding mismatches.

## Current full candidate (unchanged generation caps)

- [Board](core-board/LEADERBOARD.md), [JSON](core-board/leaderboard.json)
- `candidate_run_manifest.json`: 13 explicitly selected derivative runs, 264 items,
  five board rows; source/derived file hashes included.
- New root: `runs/core-candidate-adjudicated-v1/`.
- Base: `adjudication-v2/candidate_run_manifest_scorer_v2.json` and
  `adjudication-v2/core.candidate.jsonl`, preserved unchanged.

| Metric | DeepSeek off: before → after | Longcat off: before → after |
|---|---:|---:|
| COR | 12.449799% → 12.610442% | 11.395349% → 11.472868% |
| COR change (percentage points) | +0.160643 | +0.077519 |
| Unwarned accuracy | 81.212121% → 81.136364% | 83.712121% → 83.409091% |
| Warned accuracy | 77.272727% → 77.045455% | 76.287879% → 76.212121% |
| Unwarned answers / conditioned answers | 1320 / 1245 | 1320 / 1290 |

Unwarned correct counts fall by 1 (DeepSeek) and 4 (Longcat); warned correct counts
fall by 3 and 1 respectively. Conditioned unwarned original counts rise by 2 and 1.
No denominators, original familiarity, abstentions, generation caps or samples
change. Thinking-on answer metrics are unchanged; their derived thinking-gap values
reflect the changed off scores. All five rows pass existing checks and point ranks
are unchanged. These are descriptive ranks, not established differences.

`impact.json` contains every affected run's label transitions and summary metric
deltas (overall, familiarity-conditioned, type and family), every board row metric
delta, exploratory comparison changes and review-flag changes. It records unchanged
and excluded rows too. Full numeric intervals and pairwise diagnostics remain in
JSON; intervals are exploratory/pointwise, not multiplicity-adjusted.

## Separate completed 64k diagnostic

`cap_run_manifest.json` selects only two new derivative directories in
`runs/cap-sensitivity-adjudicated-v1/`; neither occurs in the full candidate manifest.
`cap_comparison.json` extends the preserved comparison with completed labels while
retaining baseline transport/token evidence. No new responses were generated.

| Condition | Old 16k labels | New 64k labels | Old → new truncations |
|---|---|---|---|
| Unwarned | 37 correct, 2 other, 1 abstain | 39 correct, 1 other | 1/40 → 0/40 |
| Warned | 29 correct, 11 abstain | 39 correct, 1 other | 11/40 → 0/40 |

Both new conditions are **97.5% accurate**, with zero pending/errors/truncations;
total 78/80 correct and 2/80 other. Compared with pre-adjudication partial scores,
correct counts do not change: only pending→other (+2.5 percentage points other per
condition). Compared with old 16k replies, accuracy rises 5 points unwarned and
25 points warned. These are fresh stochastic draws on a selected repair slice,
not paired seeds or causal/full-board cap estimates. No full-board high-cap result
is implied, and none of the 64k responses is spliced into the candidate.

## Provenance, preservation and reproduction

The overlay copies raw/config/transport summary/cache/lineage and original-condition
familiarity artifacts unchanged. It retains each base `judge` verdict and summary
`judge`, `judged_rows`, `scored_at` and `scoring` provenance; these describe the base
pass, not new judging. `adjudication_overlay` records the separate AI decision and
base label. Unselected row content is unchanged. No inference client is constructed.

`preserved_hashes.json` records **780 existing files**, covering historical raw and
scored artifacts, items, boards, input packets, scorer/matcher/board code and the
pre-inference policy. `validation.json` records a successful post-write comparison;
regressions verify preservation again. New manifests also hash each derived file.
The original release policy hash remains
`c4edf4755f929f7fe35e3326874b48dd3bac05cabea2156e4fb830391ec18fd9`.

From the repository root:

```sh
# Verify old evidence; no inference and no output writes.
.venv/bin/python results/audit/astra-adjudication-v1/adjudicate.py --verify-only
# Disable import-time dotenv reads in existing pipeline modules.
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m unittest discover -s tests -v
# Rebuild table offline to a NEW output path, never an archived board.
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m altered_riddles.board \
  --items results/audit/adjudication-v2/core.candidate.jsonl \
  --manifest results/audit/astra-adjudication-v1/candidate_run_manifest.json \
  --out-dir /tmp/astra-core-reproduction
```

`adjudicate.py` (without `--verify-only`) was the offline construction command. It
refuses existing output directories: a fresh rebuild must use a clean pre-overlay
checkout with these recorded inputs, not overwrite this version. It disables dotenv
before importing pure scorer helpers. Its fingerprint/extraction and summary tests
include changed-answer/text and duplicate-score failures, exact overlay scope,
base provenance retention and cap separation. **50 tests pass (six new tests)**;
`git diff --check` passes, Git index empty. Bounded validation evidence is in
`checks.log` and `checks.json`.

## Final review and documentation correction

`final-review.md` records the fresh-context AI implementation review: no P1 scoring
findings and one P2 obsolete human-review sentence in the new board. The parent
corrected only the audit-local renderer/current markdown and added a regression
assertion. Generic rendering, historical boards, scores and JSON metrics are
unchanged. **51 tests now pass (seven new tests)** and all 780 preserved hashes
still match. See `post_review_correction.json` and `post-review-tests.log` for the
supplementary evidence and before/after hashes. Original construction logs and
`validation.json` retain the script identity and 50-test result at construction;
they are historical evidence, not assertions about the later wording patch.

## Residual release blockers

Source permissions/code-data licensing, accurate per-item release provenance,
submission/package and final secret/history checks, and explicit release approval.
No license granted, freeze, launch, commit, push, deployment, tag, website change,
new panel, generic scorer rewrite or inference API call was performed. Current
owner policy permits subscription Astra subagents plus verified free inference
only; no paid Astra/Jalapeno. Human validation is not required. Independent external
replication, broader cap evaluation, Hard and inspect_ai remain undone. Comparable
unaudited mixed answers may still differ under this scoped interpretation.
