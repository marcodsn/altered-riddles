# Core + Hard development protocol

Status: development, not a frozen release. Existing benchmark data and historical
results remain unchanged. The immediate priority is validity, not higher error rates.

## Completed foundation

- `altered_riddles.board` uses descriptive point ranks, not equivalence groups.
  Pairwise comparisons use item-mean override rates on shared familiar items and
  jointly resample the existing source/answer clusters. Intervals are pointwise
  (not multiplicity-adjusted); no significance-based global ranking is claimed.
- Incomplete scoring, duplicate/missing samples, stale raw item text and failing
  pre-publish checks exclude a row. Incomplete warned scores do not produce a
  warned accuracy. Git commitment status is not asserted without verification.
- `altered_riddles.audit` produces Core, minimal-insertion development, and
  post-hoc failure slices, an input/code hash manifest, and a validity-review queue.
- Model-specific COR remains response-weighted. Shared-familiar sensitivity is
  reported separately; pairwise comparisons are item-balanced. Do not conflate
  these estimands when sample counts or familiarity denominators differ.

Run offline checks:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m altered_riddles.audit --out-dir results/audit/NEW_VERSION
```

The output directory must be new or empty. Old artifacts retain the code hashes
that produced them. No existing raw runs, item files or historical tables are
rewritten by the audit command.

## Validity before freeze

Every item needs separate answers to:

1. Is the original answer necessarily excluded by the altered question?
2. Is the accepted answer entailed, rather than merely plausible?
3. Are the premises mutually consistent?
4. Is a model's apparent override actually an incorrect answer under reasonable
   readings, and did the scorer label its final answer accurately?

The generated queue starts `unreviewed`; it does not import informal historical
claims of human review. Preserve independent reviews and an adjudication log.
AI advisory output must remain explicitly AI-labelled. Reviewer policy (latest owner instruction): explicitly labelled strong-model AI
adjudication is sufficient; no independent human validation is required. The earlier
one-human-reviewer policy is superseded. Do not invent reviewer identities or treat
agreement between models as human validation. Preserve disagreements and adjudication
reasons; see `docs/CORE_RELEASE_POLICY.md`. Standard (owner-approved 2026-09-06): strict entailment
under ordinary readings; plausible is not enough, and the original answer must
fail as an answer to the altered question.

Suggested dispositions: keep, revise-and-rerun, exclude-with-reason, unresolved.
No automated exclusion based solely on override frequency or model consensus.
Revised texts are new versions and invalidate prior answers.

## Core and Hard

**Core:** audit the current 264 items, publish an exclusion/change log, then freeze.
Maintain the prior snapshot for historical comparisons. Owner decision 2026-09-06:
Core is frozen and released first; Hard is a later, separate track.

**Hard development:** the current 16 minimal-insertion items and 35 observed
thinking-failure items are diagnostic development data. They are not a held-out
Hard test. The latter is selected using the same systems being compared and
unequal sample counts; its intervals ignore selection uncertainty.

**Hard test:** author source-family-disjoint candidates before unwarned testing.
Use a dedicated split manifest mapping sources and near-duplicate source families
to development/test. A new variant of a development source cannot enter test.
Use explicit lexical edits to quantifiers, exceptions, referents, timing and
physical constraints, while keeping premises consistent. Avoid impossible
situations that reward ignoring contradictions rather than following a change.

Start with 20–30 candidates, validate blindly for entailment and invalidation,
then test on model families not used for difficulty selection. Expansion toward
150–250 items / 100+ source families is conditional on validity and a prospective
precision analysis, not a quota to fill with weak items.

Include original, unwarned altered, warned altered, less-recognizable paraphrase,
and matched unfamiliar controls in a bounded pilot. Validate control difficulty
separately. Original familiarity does not establish that a particular error was
caused by memorization.

## Scoring provenance (since 2026-09-06)

- Matcher v2 (`altered_riddles.match.MATCHER_VERSION`): a reply that matches both
  the accepted and the original list goes to the judge unless it equals one alias
  exactly. The earlier longer-alias tie-break mislabelled correct replies that
  quoted an original justification phrase (`results/audit/rescore-v1/`).
- Every scored row carries the raw sample's `text_sha`; every `scored_summary.json`
  carries per-item fingerprints of text, answer, aliases, original answer and
  original aliases, the matcher version, code hashes, the judge spec and the
  judge-prompt hash; `scored.json` (familiarity) carries a fingerprint of the
  per-source original answers. The board excludes a row whose scores predate the
  current matcher or whose fingerprints differ from the current item file.
- Two run directories for one (model, thinking, condition) slot are an error;
  `board --manifest runs.json` names the runs to use, and the chosen run list is
  written into `leaderboard.json` as `run_manifest`.

### Scorer-v2 correction (2026-09-09)

Empty model answers deterministically abstain and are never sent to an LLM judge.
Reasoning-only replies stopped at the token cap have no committed answer; do not
extract quoted original answers or tentative answers from their unfinished traces.
A nontruncated reasoning fallback requires a standalone terminal `Answer:` line.
Visible answer content remains scorable even when subsequent output is truncated.

`scoring.scorer_version` is now required on both altered and familiarity scores;
the board rejects older scores. This is separate from matcher version 2. Historical
outputs remain archived unchanged. Current corrected candidate and explicit run
manifests were under `results/audit/adjudication-v2/` (`*-scorer-v2` boards/manifests).
The current scoped AI overlay board/manifests are in `results/audit/astra-adjudication-v1/`;
base scorer/judge provenance and the older boards are preserved unchanged.
The correction used no new inference. Report local truncation rates as well as
full-board aggregate checks; no response is resampled or silently dropped.

## Cost and run policy

- Current owner rule: subscription-backed Astra subagents are explicitly authorized,
  superseding the old no-subagents policy. Actual adjudication runtime is
  `openai-codex/gpt-6-astra`; this is not the paid Nous Astra API.
- Only verified free inference models are authorized. Nous routes must end in
  `:free` and have catalog-verified zero pricing. No paid Astra/Jalapeno, credit-funded
  paid routes or paid fallback. This scoped adjudication made zero inference API calls.
- `review_validity` is a bounded blinded AI review runner: one or two explicitly
  selected free models, at most 20 items, batches of five, at most eight inference
  requests, 3,000 output tokens/request, no SDK or application retries, explicit
  timeouts. No paid fallback. Use `--user-tag marcodsn` to send the live-verified
  Nous shape `{"tags": ["user=marcodsn"]}`. `--thinking` is explicit and recorded;
  provider default is the default because some routes require reasoning.
- Earlier Jalapeno price/budget allowances are superseded, not active permission.
  The hash-bound pre-inference `docs/CORE_RELEASE_POLICY.md` is historical evidence;
  current permissions and scoped rubric interpretation are recorded separately in
  `docs/CORE_RELEASE_POLICY_AMENDMENT_ASTRA_V1.md`.
- Preserve failed calls as unresolved; malformed/truncated reviews are not votes.
- Never substitute another provider/model silently after a failure.

## Known remaining work

- The 13 historical label disagreements are resolved by scoped AI adjudication:
  all match unchanged current samples, 12 labels changed and one confirmed; no
  historical-only cases. Two cap pending answers separately became `other`.
  Human validation is not required; AI is not independent empirical validation.
  Comparable unaudited responses were not reinterpreted; general scorer unchanged.
- Eight approved repairs and fresh Tier-0 evaluation are complete; current scores
  and manifests are in `astra-adjudication-v1/` and the two `*-adjudicated-v1` run
  roots. Fingerprints, raw lineage and all metric deltas are recorded there.
- Longcat's all-eight-repair 64k diagnostic completed 80 fresh responses with no
  errors or truncations (`results/audit/cap-sensitivity-v1/`, preserved baseline;
  completed labels in `astra-adjudication-v1/cap_comparison.json`). Each condition
  is 39/40 correct and 1/40 other, no pending. No high-cap samples enter the full
  candidate. This is not a paired-seed causal or full-panel cap estimate.
- Initial preview claims are descriptive only (`docs/CORE_RELEASE_POLICY.md`).
  Confirmatory multiplicity/power policy and broader standardized panel remain.
- Freeze with accurate per-item provenance and source permissions; licensing,
  submission validator, independent replication, inspect_ai and public packaging.
- Website schema support is implemented locally in the companion checkout;
  feed switching, versioned URLs and deployment have not happened.

No release, publication, model ranking claim, or human review is approved by this
engineering milestone alone.
