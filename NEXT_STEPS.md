# Altered Riddles — remaining work and execution instructions

## Goal and current status

Make this a credible, reproducible, widely adopted diagnostic of whether models
follow altered premises instead of giving familiar answers. Do not manufacture
difficulty by retaining ambiguous or contradictory items.

**Not launch-ready.** Audit tooling works; the full dataset and Hard track are not
validated or frozen. Work directly in this repository; do not use subagents unless
the owner explicitly changes that instruction.

### Read first

- `CLAUDE.md`: repository conventions (primarily the older pipeline).
- `PLAN.md`: v2 design and construction history.
- `docs/CORE_HARD_PROTOCOL.md`: current statistical and release protocol.
- `results/audit/adjudication-v1/README.md` and `decisions.json`: latest flagged-item decisions.
- `docs/VALIDITY_AUDIT_INITIAL.md`: earlier AI findings, not human sign-off.
- `data/items/README.md`: item-authoring rules.

The current v2 code is in `altered_riddles/`; do not accidentally use the older
`scripts/` pipeline or mix its scores with v2 results.

## What has already been done

- Replaced misleading tie groups with descriptive point ranks and genuinely
  paired, jointly clustered comparisons on shared familiar items.
- Added scoring completeness and per-sample text-drift checks.
- Generated reproducible Core and exploratory hard-slice analyses:
  `results/audit/core-hard-v2/`.
- Created a 264-item queue, initially marked unreviewed:
  `results/audit/core-hard-v2/validity_queue.jsonl`.
- Recorded AI adjudication recommendations for ten flagged items:
  **3 keep, 6 revise, 1 exclude**. Human approval remains pending.
- Drafted six repairs in `data/revisions/core-hard-pilot.yaml`, outside the active
  benchmark. These have AI advisory reviews but no fresh benchmark scores.
- Fixed the Nous advisory runner's tag format; 17 offline tests passed at handoff.

Historical items, raw runs and leaderboard files have not been replaced by these
recommendations. Check `git status` before editing; prior work may be uncommitted.

## Non-negotiable execution rules

1. Preserve historical data and raw outputs. Use new IDs for revised items, new
   run directories, and versioned audit outputs. Never reuse old answers for new text.
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

## 1. Finish validity adjudication — highest priority

### Ten flagged items

Read the recorded reasons in `results/audit/adjudication-v1/decisions.json`.

| Recommendation | IDs |
|---|---|
| Keep | `bear-house-1`, `married-boat-1`, `yellow-hat-1` |
| Revise and rerun | `mustard-family-3`, `months-28-days-1`, `marys-father-1`, `johnnys-mother-1`, `hiccups-1`, `last-brick-2` |
| Exclude from prospective release | `parachute-1` |

- [ ] Obtain human review of disputed/high-error items; aim for two independent
      human reviews and an adjudicated resolution where they disagree.
- [ ] Record reviewer, date, exact item version/hash, rationale and disposition.
- [ ] Do not interpret the owner authorizing work as approval of each item decision.

### Remaining Core items

- [ ] Review the other 254 items, prioritizing the rest of the 35 thinking-on
      failure items, then minimal-insertion items, then routine items.
- [ ] Check the additional `rooster-egg-2` concern documented in the initial audit:
      a hen laying an egg on a roof does not establish that the egg rolls.
- [ ] For each item ask:
      1. Are its premises consistent?
      2. Is the proposed answer supported, not merely plausible?
      3. Is the familiar answer incorrect **as an answer to this question**?
      4. Could a reasonable reading make the apparent override defensible?
      5. Does the score match the actual final response?
- [ ] Keep disagreement and exclusion logs. A proposition can be true but irrelevant
      to the question; do not confuse that with a correct answer.

**Known judge failure:** Solar and Laguna both confused “exactly 28” with “at least
28”, including on the repaired common-year item. Their agreement is not evidence
that “all months” is correct. The Gregorian-calendar claim has a deterministic test.

**Exit condition:** item-by-item dispositions with genuine human sign-off where
required, no unresolved contradictions promoted into a release.

## 2. Validate and run the six repairs

Drafts: `data/revisions/core-hard-pilot.yaml`.
Advisory evidence: `results/audit/revision-review-v1/`.

- [ ] Independently check each draft's entailment, original-answer invalidation,
      aliases and source linkage.
- [ ] Keep each repair as a new version with its own ID; retain `replaces` provenance.
- [ ] Review aliases for overlap with original answers and over-broad matching.
- [ ] Run the appropriate solvability/invalidation checks without treating AI
      consensus as final adjudication.
- [ ] After approval, stage a candidate dataset and run fresh original/familiarity,
      unwarned altered and warned altered conditions with documented settings.
- [ ] Preserve raw answers, usage, prompts, configurations and item hashes.
- [ ] Score uncertain responses explicitly; never count pending/error labels as
      successes or silently discard them to improve COR.

Some repairs are likely easy Core controls. Do not call them Hard until difficulty
is measured; do not weaken validity to recover the old error rate.

**Exit condition:** approved repaired items have fresh, complete, traceable results.

## 3. Complete scoring and provenance safeguards

Known remaining engineering work:

- [ ] Fingerprint original text and scoring aliases in familiarity-score caches.
- [ ] Fingerprint altered text, accepted/original aliases, and judge configuration
      in scored outputs; invalidate stale scores after any relevant change.
- [ ] Verify raw-to-scored sample correspondence, not merely raw text and counts.
- [ ] Replace directory-order selection of multiple historical runs with an
      explicit submission/run manifest.
- [ ] Audit deterministic and judge labels against a human-reviewed sample of both
      apparent successes and failures.
- [ ] Predeclare comparison families and multiplicity handling before making
      significance-based leaderboard claims.
- [ ] Run a prospective precision/power analysis using independent source clusters.

Current pairwise intervals are exploratory and pointwise, not multiplicity-adjusted.
Failure-selected subset intervals also do not account for selection uncertainty.
Do not describe point ranks as statistically established ranks or ties as equivalence.

## 4. Build a genuinely held-out Hard track

Current development material:

- 16 minimal-insertion items.
- 35 items with observed thinking-on overrides.

Neither is an independent Hard test. The latter was selected on current models'
failures with unequal sample counts.

- [ ] Create a source-family split manifest before further difficulty screening.
      Near-duplicate originals and variants of one source belong in the same split.
- [ ] Author an initial 20–30 candidates from held-out source families, using subtle
      but unambiguous changes to quantifiers, exceptions, referents, timing or constraints.
- [ ] Validate before unwarned testing. Include explicit reasons why the old answer
      fails and the new answer follows.
- [ ] Reserve model families not used for selection for final evaluation.
- [ ] Add validated controls: original, warned altered, less-recognizable paraphrase,
      and matched unfamiliar problems. Check control difficulty independently.
- [ ] Expand only if the pilot demonstrates valid residual failures and useful
      measurement precision. The tentative 150–250 item / 100+ source-family target
      is subordinate to validity and statistical power.

**Exit condition:** a frozen source-disjoint test protocol with defensible items,
not a retrospective list of current-model failures.

## 5. Broaden evaluation on a bounded budget

- [ ] Verify currently available free/cheap routes and save dated pricing evidence.
- [ ] Aim for 8–12 distinct model families for launch, budget permitting; keep
      model/configuration variants distinct from independent families.
- [ ] Standardize sample counts, prompts, token caps and thinking settings as far as
      providers permit. Record deviations rather than pretending equivalence.
- [ ] Pilot cheaply, freeze the protocol, then run the launch panel.
- [ ] Add samples according to a predeclared uncertainty rule, not favorable results.

### Nous: working request format

```json
{"tags": ["user=marcodsn"]}
```

Not a top-level `user` field, not `["marcodsn"]`, and not a `tags.user` object.
The advisory runner supports this with `--user-tag marcodsn`; check other pipeline
entry points before running them because they do not necessarily inject this tag.

A bounded advisory command (choose a NEW output directory):

```sh
.venv/bin/python -m altered_riddles.review_validity \
  --items data/revisions/core-hard-pilot.yaml \
  --out-dir results/audit/NEW_REVIEW_VERSION \
  --user-tag marcodsn \
  --models upstage/solar-pro4:free poolside/laguna-s-2.1:free \
  --thinking off \
  --ids months-28-days-1-r1
```

The runner allows at most two free models, 20 items, batches of five, eight
inference requests, 3,000 output tokens/request, and no application/SDK retries.
Malformed IDs, malformed JSON, errors and truncations remain unresolved.

Step 3.7 Flash requires reasoning. It exhausted the 3,000-token cap in the tested
batches; do not count those as reviews or silently increase budgets. Solar and
Laguna worked, but their validity judgments need scrutiny.

### Jalapeno

Before inference, record current input/output/reasoning pricing and enforce a
worst-case **initial envelope of USD 1**, including retries. This is the conservative
working cap adopted for this phase, not a claim that the owner set a permanent
lifetime budget. Escalate if more is needed. No price evidence means no paid run.

## 6. Package, replicate and launch

- [ ] Freeze audited Core and independently validated Hard as separate versioned tracks.
- [ ] Keep COR alongside altered accuracy, familiarity coverage, conditioned counts,
      other/abstain rates, cluster intervals and reasoning cost.
- [ ] Document intended use, limitations, contamination risks and correction policy.
- [ ] Review source provenance, redistribution rights and dataset/code licensing.
- [ ] Provide one-command execution, a smoke-test split, a submission validator and
      reproducible reference outputs; prioritize an `inspect_ai` integration.
- [ ] Prepare the public dataset/Hugging Face package and a sustainable hidden audit
      subset only if operating it is practical.
- [ ] Obtain independent reproduction from external evaluators.
- [ ] Prepare a technical report, clear leaderboard and actual-response failure gallery.
- [ ] Get explicit owner approval before publication or outreach.

Adoption is measured by independent runs, integrations, citations and model
reports—not merely stars or dramatic failure examples.

## Local validation and handoff

```sh
.venv/bin/python -m unittest discover -s tests -v
git diff --check
.venv/bin/python -m altered_riddles.audit --out-dir results/audit/NEW_AUDIT_VERSION
```

Use `.venv/bin/python` (the `python` shell command may not exist). Audit output
directories must be empty/new. Preserve prior snapshots and their input/code hashes.

After each milestone, update this file and `PLAN.md` with:

- completed work and changed paths;
- commands/tests and their actual results;
- API routes, attempts, token usage and cost evidence;
- unresolved validity/scoring questions;
- human approvals received versus still pending;
- the next concrete action.

**Next action now:** prepare and obtain human adjudication of the ten recorded
recommendations while continuing the remaining-item audit. Do not freeze the
benchmark, promote the repairs, or launch a large model sweep first.
