# Longcat 64k repair-slice sensitivity

Development diagnostic, not a replacement leaderboard. `specification.json`
was written before inference: all eight approved repairs, both thinking-on
conditions, five samples, same prompts and temperature setting, explicit 64,000
output cap. Exact Nous `meituan/longcat-2.0:free` route verified catalog-priced
zero immediately before dispatch. No paid fallback, one attempt per request.

| Condition | Old 16k truncated | New 64k truncated | New errors | New deterministic correct | Pending |
|---|---:|---:|---:|---:|---:|
| Unwarned | 1/40 | 0/40 | 0/40 | 39/40 | 1/40 |
| Warned | 11/40 | 0/40 | 0/40 | 39/40 | 1/40 |

Both runs pass the thinking/transport guardrails. All 80 new responses contain
a scorable answer (one unwarned answer uses the permitted terminal reasoning
Answer-line fallback). No empty reply was judged correct. The two unmatched
answers remain pending; 97.5% is deterministic correct coverage, not a completed
judge-scored accuracy estimate.

The higher cap removed observed truncations in this fresh repair-slice run.
Do not attribute the entire difference to the cap: samples were generated anew,
not paired random seeds, and the slice was selected for repairs. The result does
not establish the effect over all 264 items or other model families. Retain the
old full-board results and report the diagnostic separately. Full-board high-cap
results would require new runs selected by a new explicit manifest.

Artifacts:
- `specification.json`: prospective scope, item/code/policy hashes.
- `routes.json`, `budget.json`: public catalog evidence and per-call zero-dollar ledger.
- `execution.log`, `status.json`: execution outcomes.
- `run_manifest.json`: the two new run directories.
- `comparison.json`: baseline/new raw hashes, finish reasons, visible/scorable
  answers, partial labels, token totals and latency.

Successful inference: 80 free calls; charged/reserved API cost USD 0. No Astra,
Jalapeno or judge inference in this diagnostic. Historical files are untouched.
