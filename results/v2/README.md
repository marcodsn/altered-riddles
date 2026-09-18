# results/v2 — historical snapshot (2026-09-18), not reproducible

`leaderboard.json` and `LEADERBOARD.md` in this directory are a **point-in-time
artifact** and are deliberately left unchanged. Do not rebuild them, and do not
treat them as a current board.

They were generated on 2026-09-18 with `altered_riddles.board --items data/gated.jsonl`
over the plain `runs/<provider>_<model>/…` directories. Later the same day those run
directories were corrected to answer the **adjudicated Core item set**
(`results/audit/adjudication-v2/core.candidate.jsonl`), in which eight items are
replaced by repaired `-r1` versions:

    cat-fur-1 → cat-fur-1-r1            months-28-days-1 → months-28-days-1-r1
    hiccups-1 → hiccups-1-r1            mustard-family-3 → mustard-family-3-r1
    johnnys-mother-1 → johnnys-mother-1-r1   parachute-1 → parachute-1-r1
    marys-father-1 → marys-father-1-r1  rooster-egg-2 → rooster-egg-2-r1

Why it cannot be reproduced:

- Re-running the original command (`--items data/gated.jsonl`) against the current
  run directories yields no rows at all: every row now fails the item-set check with
  eight missing items, because those runs answer the `-r1` ids.
- Re-running with `--items results/audit/adjudication-v2/core.candidate.jsonl` produces
  a different board (the repaired wording, and a superset of models) — that board is
  `results/core/`, the published feed.

The raw evidence behind these numbers (the eight stale-wording replies per model and
sample) was pruned by `altered_riddles.run`'s resume logic when the runs were corrected
and is not recoverable; `runs/` is private and never committed. `run.py` now refuses to
prune replies for unit ids the item file does not know unless `--allow-prune` is passed,
so this cannot recur silently.

Current board: `results/core/` (see its README for the item-file rule).
