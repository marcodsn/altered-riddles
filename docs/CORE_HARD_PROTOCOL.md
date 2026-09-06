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
AI advisory output must remain explicitly AI-labelled. Reviewer policy (owner
decision, 2026-09-06): one human reviewer, the owner, plus explicitly labelled AI
reviews; the human reviews only disputed items and judge-decided rows, not the
whole set. Do not invent reviewer identities or treat agreement between models
as human validation. Standard (owner-approved 2026-09-06): strict entailment
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

## Cost and run policy

- Nous inference must use model IDs ending in `:free`, verified in its catalog.
- `review_validity` is a bounded blinded AI review runner: one or two explicitly
  selected free models, at most 20 items, batches of five, at most eight inference
  requests, 3,000 output tokens/request, no SDK or application retries, explicit
  timeouts. No paid fallback. Use `--user-tag marcodsn` to send the live-verified
  Nous shape `{"tags": ["user=marcodsn"]}`. `--thinking` is explicit and recorded;
  provider default is the default because some routes require reasoning.
- Jalapeno inference is deferred until current prices are recorded and a
  worst-case initial envelope of <= USD 1 can be enforced, including retries and
  reasoning tokens. A cheap-sounding model name is not price evidence.
- Preserve failed calls as unresolved; malformed/truncated reviews are not votes.
- Never substitute another provider/model silently after a failure.

## Known remaining work

- Ten flagged items now have AI adjudication recommendations (3 keep, 6 revise,
  1 exclude) in `results/audit/adjudication-v1/`. Six separate candidate repairs
  are in `data/revisions/core-hard-pilot.yaml`; these are not active benchmark
  items, source-disjoint Hard test items, or human-approved replacements.
- Human validity adjudication, remaining-item audit, scoring-label audit, fresh
  runs of approved repairs, and source-disjoint Hard pilot authoring.
- Familiarity scoring provenance: original-score caches do not currently carry
  enough source/alias fingerprints to prove freshness. Do not claim complete
  end-to-end score provenance from raw text hashes alone.
- Selection of multiple historical runs per model/condition currently follows
  the existing directory-order rule. A future submission manifest should select
  runs explicitly rather than silently prefer a directory.
- Item/alias-to-score fingerprints and raw-to-score correspondence checks.
- Prospective multiplicity/power policy, more independent model families, and
  standardized repeated sampling.
- Packaging, license/provenance review, external replication, then public launch.

No release, publication, model ranking claim, or human review is approved by this
engineering milestone alone.
