# Altered Riddles — remaining work and execution instructions

## 2026-09-13: Core preview published on the website

Owner decision: move marcodsn.me/altered-riddles to the Core board now as a labelled
**development preview** (three models, five thinking configurations), keep the v1
board only as a JSON download (no v1 route), and drop the "released" label only at
freeze. `results/core/leaderboard.json` is the public feed (copy of the adjudicated
board; see `results/core/README.md` and `docs/WEBSITE_CONTRACT.md`). v2 was
fast-forwarded to `main`; the previous `main` is preserved as `snapshot-13-09-2026`.
This is a preview, not a freeze, license grant or launch; the freeze list below is
unchanged.

## Latest owner instruction and release preparation

AI adjudication is sufficient; **no independent human validation is required**.
The owner now explicitly authorizes **subscription-backed Astra subagents**,
superseding the earlier no-subagents policy. Actual review runtime was
`openai-codex/gpt-6-astra`, not the paid Nous Astra API. Future authorized inference
must use **verified free models only**: no paid Astra/Jalapeno, credit-funded paid
routes or paid fallback. This adjudication used **zero inference API calls**.
See `docs/CORE_RELEASE_POLICY_AMENDMENT_ASTRA_V1.md`; the hash-bound prospective
`docs/CORE_RELEASE_POLICY.md` remains unchanged as historical evidence.

- All 13 historical disagreements resolved through AI assessment plus consistency
  challenge and supervisor-approved interpretation. All match unchanged current
  samples: 12 candidate labels changed, one confirmed; zero historical-only cases.
- Two cap-run pending answers separately became `other`: 39/40 correct per condition,
  78/80 overall (97.5%), no pending/errors/truncations. This selected fresh repair
  slice is not a causal cap estimate or a full-board replacement.
- New scored directories: `runs/core-candidate-adjudicated-v1/` and
  `runs/cap-sensitivity-adjudicated-v1/`. Base judge provenance and all historical
  raw/scored artifacts retained. No generic scorer-rule changes or 64k splicing.
- Current board and manifests: `results/audit/astra-adjudication-v1/`. Five rows pass
  automated checks, point ranks unchanged. DeepSeek-off COR rises 0.160643 percentage
  points; Longcat-off COR rises 0.077519 points. All changes are in `impact.json`.
- 780 existing input/artifact files have unchanged SHA-256 evidence, including old
  boards, item files and pre-inference policy. AI review is not human or independent
  empirical validation and does not establish population judge accuracy.
- Validation: 51 offline tests pass (seven scoped-overlay/rendering regressions), 205
  source/derived manifest file hashes match, and a separate CLI board rebuild matches
  all rows/comparisons/flags. `git diff --check` passes; Git index remains empty.

Final AI implementation review found no P1 scoring issues. Its one P2 stale
human-review instruction was corrected in the audit-local renderer/current markdown;
`post_review_correction.json` records the change and successful 51-test recheck.

Next: resolve source permissions and per-item release provenance, then complete
offline packaging/submission and final release checks.
No freeze, license grant, launch, push/deploy/tag, website edit or broader panel was
performed in this adjudication. Hard, inspect_ai and independent replication remain
outstanding; no paid-model expansion is authorized.

## Goal and current status

Make this a credible, reproducible, widely adopted diagnostic of whether models
follow altered premises instead of giving familiar answers. Do not manufacture
difficulty by retaining ambiguous or contradictory items.

**Not launch-ready.** Audit tooling works, scoring provenance is in place, the Core
item set has been AI-reviewed in full, and owner adjudications are now consolidated.
All eight approved repairs have passed validation and fresh evaluation is complete.
The current development board is `results/audit/astra-adjudication-v1/core-board/`.
A newly discovered empty/truncated-answer bug was fixed and scored offline; older
boards (including results/v2) are historical, not current. The 45-row label sheet
has mixed owner/AI provenance; its 13 judge disagreements are resolved in the new
AI overlay, not rewritten in the historical sheet. It is not an independent human
agreement study. Subscription-backed Astra subagents are explicitly authorized.

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
2. **Reviewers (superseded):** originally one human plus labelled AI reviews.
   Latest instruction permits strong-model AI adjudication without human validation.
3. **Scope:** freeze and release Core first; Hard is a later, separate track.
4. **Budget (superseded):** the former Jalapeno USD 1 envelope and PLAN launch
   allocation are historical. Current permission is verified free inference only.

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
7. Only verified free inference models; subscription-backed Astra subagents are
   authorized separately. No paid Astra/Jalapeno, silent substitutions or paid fallback.
8. Keep API keys out of source files, logs, manifests, and chat.

## 1. Owner's checks — blocking

- [x] Consolidate the 11-item sheet plus cat into `adjudication-v2/decisions.json`,
      recording owner-authored versus owner-approved AI amendments, text hashes,
      and recording timestamps (original review dates are not invented).
- [x] Decide `cat-fur-1`: owner approved the explicit "left or right" rewrite in chat;
      staged as `cat-fur-1-r1` in `data/revisions/cat-fur-v1.yaml` and the consolidated
      `data/revisions/core-approved-v1.yaml` (historical pilot snapshot preserved).
      Validation and fresh model runs remain pending; historical text and scores are unchanged.
- [x] Complete the 45-row label sheet and record provenance in
      `adjudication-v2/label_audit.json`: 43 AI blind labels, one unchanged owner label,
      one owner-approved AI correction. Mixed-provenance agreement: 32/45 (71.1%).
- [x] Resolve the 13 review/judge disagreements in `astra-adjudication-v1/` with
      exact bindings and AI provenance; no judge–human accuracy claim.
- The remaining 252 items are AI-reviewed `keep`; no human pass is planned (decision 2).

**Exit condition:** every item has a disposition with the reviewer named; no unresolved
contradictions promoted into a release.

## 2. Validate and run the approved repairs

Drafts: `data/revisions/core-hard-pilot.yaml`. Advisory: `results/audit/revision-review-v1/`.

- [x] Stage eight approved `-r1` items with `replaces` in
      `data/revisions/core-approved-v1.yaml`; all eight pass the unchanged four-model
      warned gate and invalidation probe (32/32 correct; 32/32 invalid).
- [x] Review aliases for overlap and final-answer coverage; offline checks and
      AI gate-explanation review recorded in `adjudication-v2/`.
- [x] Fresh original/familiarity, unwarned and warned Tier-0 runs completed:
      488 responses across 13 configurations, 0 API errors, 14 token-cap stops.
      Original prompts, sample counts and token caps retained; no resampling.
- [x] Empty answers deterministically abstain; truncated reasoning is not a final
      answer. Scorer v2 corrects 202 labels in the composed candidate, plus one
      answer-text-only change, without new inference. Matcher remains v2.
- [x] Rebuilt 264-item Core candidate with explicit manifests and per-sample lineage;
      five full-board rows pass existing checks. Historical raw files are unchanged.
- [x] Initial token-cap sensitivity: Longcat all eight repairs, both thinking-on
      conditions at 64k, 80 replies with no truncation. Both pending labels are now `other`;
      full-board high-cap evaluation is not done. See latest status above.

Repairs are likely Core controls; do not call them Hard until difficulty is measured.

## 3. Scoring and statistics safeguards

- [x] Fingerprints on familiarity scores and altered scores; stale scores rejected.
- [x] Raw-to-scored sample correspondence (`text_sha` on every scored row).
- [x] Explicit run manifest instead of directory order.
- [x] Resolve the 13 selected disagreements from the 45-row mixed-provenance sheet.
      No representative judge-accuracy audit or pilot 61-row adjudication is claimed.
- [x] Initial preview explicitly excludes significance-based ranking claims.
      Future confirmatory comparisons need their own prospective family/correction.
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
retries. Earlier Jalapeno envelopes are superseded: verified free inference only.

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

**Historical handoff before the latest instructions above:** steps 1–4 are complete; use the scorer-v2 board and manifests
under `results/audit/adjudication-v2/`, not the superseded intermediate boards.
Resolve the 13 mixed-provenance label disagreements, review token-cap sensitivity,
and predeclare the comparison policy before final audit/freeze. The successful
sequence made 64 gate/probe calls, 488 evaluation calls and 34 judge calls; offline
scorer repair made no calls. Final conservative ledger: USD .565084178, including
prior-work and interrupted-call reserves. 39 tests pass. No publication authorized.
