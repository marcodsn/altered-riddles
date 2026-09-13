# Core release policy — prospective work after scorer v2

Status: local release preparation, not a freeze or publication. This policy is
written after observing the Tier-0 results; it is not a retrospective preregistration.
Earlier PLAN hypotheses and their failures remain part of the historical record.

## Owner instructions in the current session

- AI adjudication is sufficient; independent human validation is not a requirement.
  A strong model such as Astra is acceptable. AI identity, prompts, responses and
  rationales must still be recorded. Do not rename AI reviews as human reviews.
- Investigate a substantially higher output cap. Preserve the old experiment.
- Proceed with release preparation and consider more Jalapeno models.
- No push, deploy, release tag or external announcement is performed by this work.

The 45-row sheet has mixed provenance and was drawn from changed labels, not a
representative random sample of all judge decisions. Its agreement percentage
cannot establish overall judge accuracy. Resolve the 13 disagreements with
recorded reasons and quantify their actual effect on current scores. Rows for
superseded texts are historical audit cases, not labels to transfer to repairs.
Any adjudicator failure/truncation remains unresolved, not an automatic vote.

## Claims for the initial Core preview

- Descriptive model estimates, cluster intervals, sample counts and limitations.
- Point ranks are display order only. No significant global ordering, equivalence
  groups, or headline superiority claims based on the current pointwise intervals.
- Pairwise and thinking-gap analyses remain exploratory. A future confirmatory
  panel must name its comparison family and multiplicity procedure before it runs.
- No claim that warning necessarily improves accuracy, or that COR proves a
  memorization mechanism. Report negative findings and abstention/cap effects.
- More models improve scope but do not turn post-hoc hypotheses into preregistration.

## Higher-cap sensitivity specification (not yet executed)

Initial bounded diagnostic: all eight repaired items, Longcat thinking on,
**both unwarned and warned**, five samples per item per condition. This is 80
fresh responses, not only the 11 previously truncated warned responses.
Use the same item texts, prompts, temperature setting and model route; request
64,000 output tokens versus the historical 16,000, in separate run directories.
The route must remain catalog-priced zero (`meituan/longcat-2.0:free`). One attempt
per inference request, no paid fallback; record errors and unsupported-cap replies.
The provider's context window is not an output-limit guarantee.

Report for each condition: cap, attempts, errors, finish reasons, visible-answer
rate, abstain/other/correct/original counts, token usage and latency. Compare
item-level aggregates with the entire old eight-item slice. Replicates at the two
caps are fresh stochastic draws, not matched random seeds. This selected repair
slice is a development sensitivity diagnostic, not a full-board causal estimate.

Do not splice high-cap successes into low-cap results. A full-board high-cap
result requires a new predeclared full run and an explicit manifest. Do not raise
caps globally before measuring latency, failure rates and cost.

## Routes and spending

Read-only catalog check in this session: Jalapeno lists 21 models, including
Qwen3.5-35B-A3B, Qwen3-Next and the existing Tier-0 models; no live prices returned.
Nous lists Longcat's zero-price free route and paid `openai/gpt-6-astra`.
Astra's standard listed prices are USD 10/M input and USD 50/M output for the
short-context tier. Catalog presence does not prove inference availability.

The existing phase ledger is conservatively USD .565084178 of USD 1. Paid Nous
Astra is outside the prior free-Nous-only policy. Obtain an explicit paid-route
exception and dollar ceiling before calling it; no hidden substitution. The
owner's PLAN section 6 remains Jalapeno price evidence, not a current invoice.
Additional Jalapeno testing needs a bounded dispatch ledger and a saved panel
specification, not unbounded generic CLI retries.

## Freeze requirements

- Adjudication resolved and applied through versioned scored artifacts.
- Cap diagnostic executed/reported or explicitly deferred with no unconstrained
  warned-performance claim.
- Per-item review provenance, repair/exclusion log and source redistribution terms.
- Versioned snapshot and input/code/run hashes; do not stamp every item with one
  fabricated reviewer/date via the legacy freeze CLI.
- Offline reproduction, submission checks, documentation, secret/history review.
- Current board and website schema tested together; no v1 results relabelled v2.

Independent external replication is desirable and not yet performed. Hard and
inspect_ai integration remain separate outstanding work, not completed features.
