# Altered Riddles — remaining work and execution instructions

## Goal and current status

Make this a credible, reproducible, widely adopted diagnostic of whether models
follow altered premises instead of giving familiar answers. Do not manufacture
difficulty by retaining ambiguous or contradictory items.

**Not launch-ready.** Audit tooling works, scoring provenance is in place, the Core
item set has been AI-reviewed in full, and the owner's human checks are pending.
Work directly in this repository; do not use subagents unless the owner explicitly
changes that instruction.

### Read first

- `CLAUDE.md`: repository conventions (primarily the older pipeline).
- `PLAN.md`: v2 design and construction history (dated entries at the end).
- `docs/CORE_HARD_PROTOCOL.md`: current statistical, provenance and release protocol.
- `results/audit/adjudication-v1/`: AI adjudication of ten flagged items and the
  owner's sheet `human_review.yaml`.
- `results/audit/validity-pass-v1/README.md`: AI pass over the other 253 items.
- `results/audit/rescore-v1/README.md`: the matcher fix and its effect.
- `data/items/README.md`: item-authoring rules.

The current v2 code is in `altered_riddles/`; do not use the older `scripts/`
pipeline or mix its scores with v2 results.

## Owner decisions (2026-09-06)

1. **Standard:** strict entailment under ordinary readings. Plausible is not enough;
   the original answer must fail as an answer to the altered question.
2. **Reviewers:** one human (the owner) plus explicitly labelled AI reviews. No second
   human reviewer. The human reviews disputed items and judge-decided rows only.
3. **Scope:** freeze and release Core first; Hard is a later, separate track.
4. **Budget:** Jalapeno envelope USD 1 for this phase; the PLAN section 6 allocation
   (~USD 75) stands for the launch panel.

## What has already been done

- Paired, jointly clustered board comparisons with point ranks; scoring completeness
  and text-drift checks; audit snapshots `results/audit/core-hard-v1..v3/`.
- Ten flagged items AI-adjudicated (3 keep, 6 revise, 1 exclude) with six draft
  repairs in `data/revisions/core-hard-pilot.yaml`; Nous request tag fixed.
- 2026-09-06: all of the above committed (`d61d616`); 11-item human sheet written
  (`adjudication-v1/human_review.yaml`, blind to the AI recommendation).
- 2026-09-06: AI validity pass over the remaining 253 Core items: 252 keep, `cat-fur-1`
  flagged (pun not excluded), minor notes on four items. Dispositions and an updated
  queue in `results/audit/validity-pass-v1/`.
- 2026-09-06: the pass exposed deterministic mislabels: the matcher's longer-alias
  tie-break counted correct replies that quote an original phrase ("Three apples (the
  two you took ...)") as overrides. Matcher v2 sends every mixed reply to the judge;
  `tests/test_match.py` holds the regression cases.
- 2026-09-06: provenance. Scored rows carry the raw sample's `text_sha`; summaries carry
  per-item fingerprints, matcher version, code hashes, judge spec and prompt hash; the
  board rejects stale or unfingerprinted scores; runs are selected by an explicit
  `--manifest`, never directory order. 29 offline tests pass.
- 2026-09-06: all Tier-0 runs re-scored: 161 judge calls, 0 errors, 45 labels changed
  (35 original→correct, 2 original→other, 7 correct→other, 1 correct→original).
  COR moved by at most 0.6 points, ranks unchanged. Board `results/v2/` rebuilt.
- 2026-09-06: routes verified read-only: 7 Nous `:free` routes with catalog price 0
  (`stepfun/step-3.7-flash:free` requires reasoning), Jalapeno 21 models, no pricing in
  its API (`results/audit/routes-2026-09-06/models.json`). PLAN section 6 prices
  (owner, 2026-09-04) remain the Jalapeno price evidence.

Historical raw outputs are untouched. Pre-fix scores are in git at `6c568ce`.

## Non-negotiable execution rules

1. Preserve historical data and raw outputs. Use new IDs for revised items, new run
   directories, and versioned audit outputs. Never reuse old answers for new text.
2. Do not label AI reviews as human reviews or invent approvals/reviewer identities.
3. Do not let model votes automatically include or exclude items. Inspect their
   reasoning against the actual wording.
4. Do not select a Hard test using the failures of the same models used to rank it.
5. Keep original-answer familiarity, altered accuracy, COR, abstentions, and other
   errors distinct. Document denominators and sample counts.
6. No publication, push, release tag, or external announcement without owner approval.
7. Use only Nous `:free` routes and verified cheap Jalapeno models for API work.
   No silent provider substitutions or paid fallback.
8. Keep API keys out of source files, logs, manifests, and chat.

## 1. Owner's checks — blocking

- [ ] Fill `results/audit/adjudication-v1/human_review.yaml` (11 items: disposition +
      one-line reason). Then the assistant folds it into `adjudication-v2/decisions.json`
      with reviewer, date, text hash and disposition.
- [ ] Decide `cat-fur-1`: keep as a Core control, rewrite to "left or right", or exclude.
- [ ] Label `results/audit/rescore-v1/label_changes_sheet.yaml` (45 judge-decided rows,
      blind). The assistant then records judge–human agreement on these rows.
- The remaining 252 items are AI-reviewed `keep`; no human pass is planned (decision 2).

**Exit condition:** every item has a disposition with the reviewer named; no unresolved
contradictions promoted into a release.

## 2. Validate and run the approved repairs

Drafts: `data/revisions/core-hard-pilot.yaml`. Advisory: `results/audit/revision-review-v1/`.

- [ ] After the sheet: stage approved `-r1` items as new IDs in a candidate item file,
      keeping `replaces`; run the warned gate and the invalidation probe on them.
- [ ] Review aliases for overlap with original answers and over-broad matching.
- [ ] Fresh original/familiarity, unwarned and warned runs on the Tier-0 rows with the
      documented settings; new run directories; score with matcher v2.
- [ ] Never count pending/error labels as successes or discard them to improve COR.

Repairs are likely Core controls; do not call them Hard until difficulty is measured.

## 3. Scoring and statistics safeguards

- [x] Fingerprints on familiarity scores and altered scores; stale scores rejected.
- [x] Raw-to-scored sample correspondence (`text_sha` on every scored row).
- [x] Explicit run manifest instead of directory order.
- [ ] Judge-label audit against the owner's 45-row sheet (and, if wanted, the pilot's
      61-row judge sheet in `results/pilot/`, still unlabelled).
- [ ] Predeclare comparison families and multiplicity handling before any
      significance-based leaderboard claim.
- [ ] Prospective precision/power analysis using independent source clusters.

Current pairwise intervals are exploratory and pointwise. Do not describe point ranks
as statistically established ranks or ties as equivalence.

## 4. Hard track — after the Core freeze (decision 3)

Development material: 16 minimal-insertion items and 35 thinking-on failure items;
neither is a held-out test. When started: source-family split manifest first, then
20–30 candidates from held-out families, blind validation, evaluation on model
families not used for selection, matched controls. Unchanged from the protocol.

## 5. Broaden evaluation on a bounded budget

- [x] Routes verified 2026-09-06 (see above). Re-check before the launch panel.
- [ ] 8–12 distinct model families for launch, budget permitting; standardize samples,
      prompts, token caps and thinking settings; record deviations.
- [ ] Pilot cheaply, freeze the protocol, then run the launch panel. Add samples by a
      predeclared uncertainty rule only.

Nous request metadata: `{"tags": ["user=marcodsn"]}` (`--user-tag marcodsn` in
`review_validity`; other entry points do not inject it). `review_validity` is bounded:
two free models, 20 items, batches of five, eight requests, 3,000 output tokens, no
retries. Jalapeno: record prices before inference; USD 1 envelope this phase.

## 6. Package, replicate and launch

- [ ] Freeze audited Core as a versioned track with an exclusion/change log.
- [ ] Keep COR alongside altered accuracy, familiarity coverage, conditioned counts,
      other/abstain rates, cluster intervals and reasoning cost.
- [ ] Document intended use, limitations, contamination risks and correction policy.
- [ ] Licenses and source provenance (owner: MIT code + CC BY 4.0 data?).
- [ ] One-command execution, smoke-test split, submission validator, reference
      outputs; `inspect_ai` integration.
- [ ] Public dataset / Hugging Face package; independent reproduction; technical
      report, leaderboard and failure gallery. Owner approval before publication.

## Local validation and handoff

```sh
.venv/bin/python -m unittest discover -s tests -v
git diff --check
.venv/bin/python -m altered_riddles.audit --out-dir results/audit/NEW_AUDIT_VERSION
```

Use `.venv/bin/python`. Audit output directories must be new or empty. After each
milestone update this file and `PLAN.md` with the work done, commands and results, API
usage and cost evidence, open questions, approvals received versus pending, and the
next action.

**Next action now:** owner fills the 11-item sheet, decides `cat-fur-1`, labels the
45-row sheet. Assistant then folds the decisions into `adjudication-v2`, stages and
runs the approved repairs, records judge agreement, and drafts the predeclared
comparison policy. Do not freeze Core or run the launch panel before that.
