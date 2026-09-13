# Core v2 public feed

`results/core/leaderboard.json` is the board that marcodsn.me/altered-riddles reads,
published as a **development preview** (`release_status` "development candidate, not
frozen or publication-approved"). It is rebuilt from the adjudicated runs with one
command, and its rows, intervals and comparisons are identical to the audited board in
`results/audit/astra-adjudication-v1/core-board/`:

```sh
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m altered_riddles.board \
  --items results/audit/adjudication-v2/core.candidate.jsonl \
  --manifest results/audit/astra-adjudication-v1/candidate_run_manifest.json \
  --out-dir results/core
```

On top of the audited board it carries, per row, `rank_best`/`rank_worst` (from the
pairwise comparison intervals), `original_acc`, `mean_output_tokens` and a per-type
breakdown, plus a board-level `alteration_types` list; the website's charts and rank
spread read these.

Rules for this path:

- Only rebuild from a manifest whose runs pass scoring and pre-publish checks; never
  hand-edit the file. `release_status` is displayed on the website as the status tag
  (anything not marked frozen/released renders as a preview).
- The historical v1 feed `results/leaderboard.json` is never rewritten from Core data.
- At freeze: rebuild with `--status` naming the frozen release, and update the website
  citation metadata in the same change.
