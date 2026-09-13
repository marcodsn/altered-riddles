# marcodsn.me integration contract

Website checkout: `../../marcodsn.me` relative to this repository.

## Deployment (switched to Core preview on 2026-09-13)

Both `/altered-riddles` and `/altered-riddles/leaderboard-screenshot` fetch:

`https://raw.githubusercontent.com/marcodsn/altered-riddles/main/results/core/leaderboard.json`

The last-updated timestamp comes from the GitHub commits API on that same path.
`results/core/` is a copy of the current adjudicated board (see its README). The
historical v1 feed at `results/leaderboard.json` is untouched and linked from the
page as a JSON download only; there is no v1 route. The v1 board as published is on
the `snapshot-13-09-2026` branch.

## Reader

`src/lib/utils/leaderboard.ts` exposes a shared `parseLeaderboard` reader for
legacy arrays/NDJSON and the native v2 `{rows: [...]}` object. Both pages use it.

| Core field | Meaning/display |
|---|---|
| `model` | split provider at the first colon only; preserve model suffixes like `:free` |
| `thinking` | reasoning badge; do not invent an effort setting |
| `cor` | conditioned override rate, fraction, not percent |
| `cor_ci95` | two interval endpoints, not a symmetric plus/minus half-width |
| `alt_acc` | unwarned accuracy across all items |
| `original_rate` | unconditional original-answer rate |
| `familiar_share` | share of familiar item sources; NOT original accuracy |
| `n_conditioned` | response count in the COR denominator |
| `warned_acc` | warned accuracy at the recorded cap |
| `other_rate`, `abstain_rate` | unconditional unwarned rates |
| `median_reasoning_tokens` | median reasoning usage; NOT average output tokens |
| `release_status` | visible status; absent status defaults to development/unverified |

v2 does not fabricate original accuracy, mean completion tokens, or rank spread.
The page hides v1 charts/taxonomy/metric prose when receiving Core data. It displays
Core-specific denominator, AI-review and statistical caveats instead. Screenshot
cards carry Core release status and descriptive-rank warnings.

## Validation

From the website checkout:

```sh
node --experimental-strip-types scripts/test-leaderboard.mjs
npm run check
```

The reader tests cover both legacy formats, v2 provider/model handling, interval
formatting, missing/unavailable metrics and malformed rates/intervals. Also check
against the actual candidate board before switching feeds.

## Status tag and freeze

The page shows a status tag next to the date. `parseLeaderboard` maps
`release_status` to "development preview" unless the string says frozen/released
without a "not". The full string is the tag's tooltip and appears in the Core
caveat paragraph. Nothing on the page calls the preview a release.

At freeze: replace `results/core/leaderboard.json` with the frozen board (status
string marking it released), then update the website citation date/metadata and
dataset links in the same change. Never rewrite `results/leaderboard.json` from
Core data.
