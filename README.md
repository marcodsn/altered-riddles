# Altered Riddles — Core v2

A diagnostic of whether language models follow altered premises or repeat a
familiar riddle's now-wrong answer.

**Status: development candidate, not a frozen release.** Current results cover
264 items and three model families (five thinking configurations). Do not combine
these scores with v1. The historical README and leaderboard are preserved in
[docs/README_V1.md](docs/README_V1.md) and `results/` respectively.

## Current evidence

- [Candidate leaderboard](results/audit/astra-adjudication-v1/core-board/LEADERBOARD.md)
- [Native JSON board](results/audit/astra-adjudication-v1/core-board/leaderboard.json)
- [Scoped AI adjudication and exact impacts](results/audit/astra-adjudication-v1/README.md)
- [Execution, review provenance and scoring corrections](results/audit/adjudication-v2/README.md)
- [Protocol](docs/CORE_HARD_PROTOCOL.md), [preserved release policy](docs/CORE_RELEASE_POLICY.md),
  [current policy amendment](docs/CORE_RELEASE_POLICY_AMENDMENT_ASTRA_V1.md)
- [Remaining work](NEXT_STEPS.md)

Eight approved repairs passed the warned solvability and original-answer
invalidation gates and were freshly evaluated. Empty answers and truncated
reasoning without final content score as abstentions. Historical raw outputs are
retained; explicit manifests select the current scores.

**Adjudicated:** 13 historical review/judge disagreements resolved by subscription
Astra AI review: 12 current candidate labels changed and one confirmed, with exact
unchanged item/answer/raw bindings. No general scorer rules changed. Two pending
Longcat 64k repair-slice answers separately became `other`: 78/80 correct (97.5%),
zero pending/errors/truncations. This diagnostic does not replace the full-board
16k results or establish a causal cap effect. [Evidence and limitations](results/audit/astra-adjudication-v1/README.md).
AI review is sufficient, but is not human or independent empirical validation.
Source permissions, release provenance and packaging remain open; no freeze approved.

## Metrics and scope

**Conditioned Override Rate (COR, lower is better):** among unwarned responses
whose source the model answered correctly in at least 80% of original samples,
the fraction giving the original, now-invalid answer.

Always read COR alongside altered accuracy, familiarity coverage, conditioned
response counts, other errors and abstentions. In the current board, altered
accuracy/other/abstain rates cover **all** unwarned responses, while COR covers
only familiar sources. Familiarity coverage is not original-answer accuracy.
Abstaining can lower COR; different models can have different COR denominators.

Intervals use source/answer-cluster bootstrap resampling. Ranks are descriptive
point estimates, not established differences or equivalence groups. Pairwise
intervals are exploratory and pointwise, not multiplicity-adjusted.

Core uses five alteration types: `stated`, `hard_constraint`, `negated_premise`,
`trivialized`, and `question_swap`. Accepted answers must be entailed and original
answers excluded under ordinary readings. AI model votes alone are not proof of
validity. Familiarity and continuation probes do not prove that a particular
error was caused by memorization. Gate-model selection, a small evaluation panel,
unequal sample counts and token caps limit generalization. Hard is a separate,
future track; development failure slices are not a held-out Hard test.

## Setup

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # add credentials only for routes you intend to use
.venv/bin/python -m unittest discover -s tests -v
```

## Reproduce the candidate board offline

From the repository root, using the accompanying raw/scored run directories:

```sh
.venv/bin/python -m altered_riddles.board \
  --items results/audit/adjudication-v2/core.candidate.jsonl \
  --manifest results/audit/astra-adjudication-v1/candidate_run_manifest.json \
  --out-dir results/local-core-check
```

This makes no inference calls. The generated table's automated checks are not
release approval; retain the open-issue warnings above when sharing it.

## Running models

Use the `altered_riddles` package, not the historical `scripts` pipeline.
`run --help` describes original, unwarned and warned conditions; `score --help`
describes deterministic matching and optional judge calls. **Current owner rule:**
subscription-backed Astra subagents are authorized; inference is restricted to
verified free models. No paid Astra/Jalapeno calls or paid fallback. This adjudication
made no inference API calls. The generic CLI can spend credits and does not enforce
this policy; do not treat historical paid-route examples as authorization.

An explicit `run --max-tokens 64000` creates a separate `-cap64000` configuration.
It does not replace existing default-cap samples. Use a new `--runs-dir` for a
new experiment, predeclare the whole evaluation slice, and retain failures.
Do not rerun only truncated answers and splice successful retries into a board.
Provider context length does not guarantee support for an output-token cap.

## Website compatibility

The existing public website uses the v1 feed in `results/leaderboard.json`.
Core JSON is an object with `rows`, not that legacy array/NDJSON schema. The
companion website has local support for both schemas, including native interval
endpoints and correctly labelled familiarity coverage. No feed switch or website
deployment has been performed. See [the integration contract](docs/WEBSITE_CONTRACT.md).

## Release, contamination and corrections

The dataset is not yet frozen. Public altered items may enter future training
corpora; record release dates and model versions and do not claim previously
exposed items are private canaries. Do not infer contamination from individual
answers. Corrections will have a versioned change log, new item IDs when wording
changes, fresh responses for new text, and preserved prior snapshots. Changes to
scoring require new score artifacts and provenance, not rewritten raw answers.

Code/data licensing and upstream source permissions are still under review.
No new blanket data license is asserted here. See `data/sources.yaml` for recorded
source provenance. A public release remains blocked until redistribution terms
are settled.
