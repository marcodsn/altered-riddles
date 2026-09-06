# Flagged-item adjudication — release recommendations

**Not a release approval.** Ten flagged items were adjudicated by the coding
assistant using direct textual analysis and independent advisory responses from
Solar Pro 4 and Laguna S 2.1 on Nous `:free` routes. These are AI reviews, not
human sign-offs. The remaining 254 Core items have not been adjudicated here.

| Recommendation | Items |
|---|---|
| Keep (3) | bear-house-1, married-boat-1, yellow-hat-1 |
| Revise and rerun (6) | mustard-family-3, months-28-days-1, marys-father-1, johnnys-mother-1, hiccups-1, last-brick-2 |
| Exclude from prospective release (1) | parachute-1 |

Full reasons and reviewer disagreements are in `decisions.json`. Existing items,
scores, and historical leaderboard files remain unchanged. No hypothetical
post-exclusion ranking is promoted as a benchmark result.

## Candidate repairs

`data/revisions/core-hard-pilot.yaml` contains six distinctly versioned draft
repairs, deliberately outside `data/items/` and the active gate dataset. They
remove naming/count contradictions, specify a common Gregorian year, pin an
explicit motive, and ask for the number of additional bricks. Some are likely
Core controls rather than Hard items. Their difficulty has not been measured.

Blinded advisory review of the repairs is preserved in
`results/audit/revision-review-v1/`. Solar returned six schema-valid reviews;
Laguna returned five, and its last-brick review was rejected because it changed
the item ID. No fuzzy ID correction or automatic voting was performed.

Neither model is a reliable oracle here:

- Both still confuse **exactly** 28 days with **at least** 28 days, even with the
  common Gregorian year explicitly stated. That rationale is rejected, not used
  to exclude the valid repair. The Gregorian month-length calculation is covered
  by a deterministic regression test.
- Several `original_excluded=false` fields contradict accompanying explanations
  that the familiar answer is irrelevant or incorrect for the revised question.
- Solar previously called the polar house impossible and rejected an explicit
  brown color. Its rationale is not accepted as a validity finding.

Thus this is evidence that automated validity gates also need calibration—not
permission to equate model agreement with ground truth. Human approval and fresh
runs are still required before any candidate replaces its historical item.

## Nous recovery

The working request metadata is **`{"tags": ["user=marcodsn"]}`**. A top-level
`user`, a bare string tag, and a `tags.user` object were unsuccessful; all probe
responses are preserved under `results/audit/nous-tag-probe-v1/`. The shape was
also corroborated by the community report:
https://github.com/HKUDS/nanobot/discussions/4970

Example:

```sh
.venv/bin/python -m altered_riddles.review_validity \
  --user-tag marcodsn --models upstage/solar-pro4:free poolside/laguna-s-2.1:free \
  --thinking off --items data/revisions/core-hard-pilot.yaml \
  --out-dir results/audit/NEW_REVIEW \
  --ids months-28-days-1-r1
```

Step 3.7 Flash rejects disabled reasoning. With reasoning enabled it used the
3,000-token limit without completing either batch, so those responses remain
unresolved. Solar and Laguna were explicitly selected for the subsequent free
review; no paid fallback occurred. Free-route usage is recorded, not independently
verified by a billing receipt.

## Ready?

- Engineering audit and bounded advisory runner: **yes, development tooling**.
- These ten items: **AI recommendations recorded, human sign-off pending**.
- Six repairs: **drafts reviewed by AI, no fresh benchmark scores**.
- Full Core: **not frozen/fully adjudicated**.
- Held-out Hard set: **not built or validated**.
- Public release: **not ready**.
