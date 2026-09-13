# Core v2 public feed

`results/core/leaderboard.json` is the board that marcodsn.me/altered-riddles reads.
It is a byte-for-byte copy of the current adjudicated candidate board,
`results/audit/astra-adjudication-v1/core-board/leaderboard.json`, published as a
**development preview**: three model families, five thinking configurations, 264
items, `release_status` "development candidate, not frozen or publication-approved".

Rules for this path:

- Only copy a board here after its scoring and pre-publish checks pass; never
  hand-edit it. The `release_status` string is displayed verbatim on the website
  and drives the status tag (anything not marked frozen/released renders as a
  development preview).
- The historical v1 feed stays at `results/leaderboard.json` and is never rewritten
  from Core data. The v1 board as originally published is on the
  `snapshot-13-09-2026` branch.
- When the Core board is frozen, replace this file with the frozen board, set its
  `release_status` accordingly, and update the website citation metadata in the
  same change.
