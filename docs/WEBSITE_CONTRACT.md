# marcodsn.me integration contract

Website checkout: `../../marcodsn.me` relative to this repository.

## Existing deployment

Both `/altered-riddles` and `/altered-riddles/leaderboard-screenshot` fetch:

`https://raw.githubusercontent.com/marcodsn/altered-riddles/main/results/leaderboard.json`

The main page also fetches v1 alteration aggregates and a last-updated timestamp
from that repository. It does not fetch the current Core candidate automatically.
The old website CLAUDE.md description of a local static asset is stale.

## Local compatibility changes (not deployed)

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

## Deployment still required

The local reader is compatible; the deployed site has not changed. Do not overwrite
the old feed or push a development board as a release. After freeze, decide the
public repository/branch and versioned feed path, update both fetch URLs, timestamp
lookup, download links, dataset links and citation metadata together. Historical
v1 must stay accessible. This work does not switch URLs or publish either repo.
