# Altered Riddles v2 — plan

*Status: draft for Marco's review · 2026-09-04 · branch `v2` (from `eval-fixes`) · target repo `nullsilver-labs/altered-riddles`, rendered on nullsilver.com.*

v2 keeps the metric idea and the plumbing, and rebuilds the dataset around two things v1 never proved: that the model actually **recalls** the original, and that the original answer is **provably wrong** for the altered version. Everything below is scoped to a **zero-money budget**; paid frontier rows come from credits or community runs, never from Marco's wallet.

---

## 0. Diagnosis (re-verified on this repo, not taken from the review)

| Signal | v1 value | Verified how |
|---|---|---|
| Altered items | 962 (662 public + 300 private fixed) | `data/benchmark*.jsonl` |
| Distinct source riddles / max variants per source | 219 / 9 | same |
| Altered items **never** answered correctly by any of 25 runs | **224 of 962 (23%)** | `results/judgments/*` (review said 243/1000; it counted duplicates) |
| Mean "neither correct nor original" answer share | **29%** | same, per run 19–54% |
| Validator `needs_review=true` | 0 items | `data/benchmark.jsonl` |
| Opus 4.7 "reasoning high" row (via Nous) | 39,862 output tokens / 1,220 responses = **33 tok/response** | eval file; thinking was silently not honored |
| Judge | local qwen3.5-27b, identity unrecorded, server now down; re-judge agreement 87.8% on `gave_original` | `results/judge_agreement.json` |
| Sources | crawsome list, 396 rows, mostly obscure verse riddles | `data/riddles_source.csv` |
| Raw model outputs | gitignored, gone; rows cannot be re-derived | `.gitignore`, B2 notes |
| Private fixed set in git history | **never committed** — history is safe to move to a public org | `git log --all` |
| CI95 on COR, 300-item fixed set | ±5 to ±7 points; 9 models share a plausible rank 1 | `results/LEADERBOARD.md` |

**Root cause in one line.** The conditioning event ("solved the original") measured *reasoning*, not *recall*, because the sources are obscure. So COR measured "solve a new metaphor riddle with an LLM-chosen answer", and the 23% unsolvable items and 29% "neither" bucket follow directly. The board could not rank because the signal was noise plus judge error.

**Where I adjust the review.** Its eight recommendations are right. Three cost-driven changes: (a) the "four strong reasoning models" warned gate becomes "three free/cheap models plus Marco"; (b) trick puzzles (bat-and-ball, Monty Hall) are a separate `family`, not mixed into riddles, so the per-family split is a finding rather than a confound; (c) the `inspect_ai` task is not a nicety, it is the mechanism by which frontier rows appear without us paying.

---

## 1. Goal and pre-registered findings

**Goal.** Measure recall override in a way where recall is proven per item and per model, the original answer is provably invalid, and every leaderboard row is re-derivable from committed raw outputs.

These are pre-registered here: the gates are frozen by the dated commit of this file, before any full run, and the writeup reports against them as written:

- **H1 — separation.** With n ≈ 350 items over ≥ 120 sources, CI95 half-width on COR ≤ ±4 points, and the pairwise-bootstrap rank groups contain ≥ 3 disjoint groups among ≥ 10 models. (v1: ±6–7, one group.)
- **H2 — override gap.** Warned accuracy minus unwarned accuracy ≥ 15 points, mean over models. If true, the failure is attention, not ability, which is the paper's claim.
- **H3 — thinking gap.** Thinking-on lowers COR versus thinking-off for the same model on ≥ 4 of 5 paired models, by a median ≥ 8 points.
- **H4 — scoring validity.** Deterministic alias matching resolves ≥ 70% of answers; judge-vs-Marco agreement on the remainder ≥ 95% on a 300-answer labeled sample.
- **H5 — clean items.** On gate models' *unwarned* answers, the "neither" share ≤ 10% (v1: 29%), 0 items are unsolved by every warned gate model (v1: 23%), and no released item's altered text is recalled by any probe model at release time (D7, layer 1).

The writeup leads with H2 and H3 and the per-type table, not with the leaderboard.

---

## 2. Constraints (the honest budget)

- **Zero money.** No paid API call without Marco's explicit go-ahead. The rule is stated in `README.md` and `CLAUDE.md`, and every credit-funded row on the board says where the credits came from.
- **Compute we have or can plausibly get, in order of certainty:**
  1. **Chinese API provider** (Marco has access; name and model list to fill in — see open decision 2). Presumably DeepSeek, Qwen, GLM, Kimi, MiniMax lines. This is the backbone of the roster.
  2. **Nous Portal free tier.** `poolside/laguna-s-2.1:free`, `tencent/hy3:free`, `stepfun/step-3.7-flash:free` responded in B2 and in other lab projects. Rate-limited; wall-clock cost, not money.
  3. **Local GPUs.** The RTX 3090 + RTX PRO used by remora/flint, when free: a ≤32B judge and the small open models (qwen3.6-27b, gemma-4-31b, gpt-oss-20b) under vLLM. The old `10.8.0.5:8083` box is down (duologue log), so `local` in `config.py` must be re-pointed.
  4. **Vendor free tiers, verify before counting on them:** Google AI Studio (Gemini Flash), GitHub Models, OpenRouter `:free` routes. Rate limits decide feasibility, not price.
  5. **Research-credit programs.** OpenAI Researcher Access, Anthropic academic credits, Google for Research. One afternoon of forms; the only realistic path to GPT-5.4 / Opus 4.7 / Gemini 3.1 Pro rows. Apply in M0 so credits land by M4.
  6. **Community runs.** `inspect_ai` task + a results PR contract. Anyone with credits adds a row; committed raw outputs make it verifiable.
- **Time.** Marco part-time. Human review of ~400 items is 1–2 days. Item authoring is the dominant human cost; LLM drafting helps, humans commit.

---

## 3. Design decisions

**D1 — Sources: hand-curated, two families, breadth over depth.**
- `riddle`: the famous ones (surgeon, candle, keys-without-locks, towel, footsteps, echo, map, coin, needle, ...).
- `puzzle`: famous trick puzzles (bat-and-ball, Monty Hall, river crossing, two doors, three switches, trolley variants, ...).
- Crawsome items are admitted only if they pass D2.
- Targets: ≥ 120 sources, ≤ 3 variants per source, 300–400 items + 50 canary. Breadth across sources is what shrinks the clustered CI.
- `data/sources.yaml`: text, canonical answer, aliases, family, provenance URL. Hand-written.

**D2 — Recall probe: memorization proven by construction, and per model.**
- Probe A (answer): thinking off, `max_tokens=8`, 5 samples. Pass at ≥ 4/5 canonical.
- Probe B (completion): prefix = first ~60% of the riddle, ask to continue; normalized token overlap ≥ 0.8. Recorded as evidence, not gated on.
- A source is **admitted** if Probe A passes on ≥ 3 of 4 probe models (Tier 0 roster).
- COR for a given model conditions on **that model's** Probe A pass for the source. This replaces v1's "solved the original" and is ~free (8 tokens, no thinking).
- The same two probes run on every candidate's **altered** text. An altered item that is itself recalled is already contaminated and is not released (D7, layer 1).

**D3 — Alteration types: entailed, not suggested. Four checkable types only.**

| type | definition | example |
|---|---|---|
| `stated` | the answer is written in the text (includes v1's bias probes) | "The surgeon, who is the boy's father, ..." |
| `hard_constraint` | a numeric or lexical constraint excludes the original | "What five-letter word ... and is a fruit" |
| `negated_premise` | a premise the original answer needs is negated | "What has keys but does not open locks, and has no music" |
| `trivialized` | the famous complication is removed | bat-and-ball where the ball is stated to cost $0.10 |

Every item carries `why_original_fails` (one checkable sentence) and `aliases`. `meaning_shift` and `context_swap` are dropped: they generate new metaphor riddles with LLM-chosen answers, which is the 29% bucket.

**Items are templates where the alteration has a natural slot.** The stated relation (father / uncle / grandfather), the numeric constraint, the letter count, the amounts in a trivialized puzzle. A template carries a validated pool per slot; every value must keep `why_original_fails` true, and the warned gate runs on the canonical instance plus two random ones. Verse riddles mostly stay fixed; `stated` and `trivialized` items mostly become templates. Expected coverage: half to two thirds of items. This is the prevention half of the contamination story (D7, layer 2).

**D4 — Validation: warned gate, then a human, every item.**
- Warned prompt: "This is a modified version of a well-known riddle. Read every word; the usual answer may be wrong."
- Accept only items solved when warned by ≥ 3 of 4 gate models (Tier 0), *and* reviewed by Marco. If a gate model's warned answer is a defensible alternative, either add it to `aliases` or drop the item. Every item gets `reviewed_by`, `reviewed_at`.
- The warned condition is kept in the benchmark as a second run condition, which is where the **override gap** (H2) comes from.

**D5 — Scoring: deterministic first, judge second, four labels.**
- Normalize (lowercase, strip articles/punctuation, lemmatize lightly) → alias match → only non-matches go to a named, versioned judge.
- Labels: `correct` / `original` / `other` / `abstain_or_flags_trick`. The last is new: good models increasingly say "this looks like the surgeon riddle but the text says father"; that is not an override.
- Publish `results/judge_agreement.json` from a 300-answer sample Marco labels blind (H4).

**D6 — Run protocol.**
- Temperature = provider default. 5 samples for free/local models, 3 for paid or rate-limited, recorded per row.
- Thinking on **and** off for every model that supports both.
- **Guardrail:** a run fails and is not scored if reasoning is enabled and the median reasoning-token count is < 50 or the API reports none. This is the rule that would have caught the Opus 4.7 row. Frontier rows go through the vendor's own API, never a router that may strip thinking.
- Raw outputs are committed under `runs/`; a row without raw outputs is not on the board.

**D7 — Release and contamination: prevent where we can, detect everywhere, and never pretend.**

Contamination of the *originals* is the premise, not a problem. The risk is the *altered* items: once public, a model trained after release can answer them by lookup, and its low COR means nothing. Two facts shape the answer. Fifty held-out items give a CI of roughly ±10 points on COR, so a small canary catches only gross contamination. And some famous alterations are already memes (the surgeon-who-is-the-father version has been quoted in blogs and papers since 2023), so an item can be contaminated *before* release. Layers, cheapest and strongest first:

1. **Fresh-at-release filter (prevention, free).** The D2 probes run on every candidate's altered text. An item whose altered text a probe model completes verbatim, or answers correctly with thinking off in 8 tokens at ≥ 4/5, is already memorized and is not released. It is tagged `famous_variant` and kept for a separate table, because those items are interesting in their own right. This is what makes "the altered version is not recalled" true by construction on day one.
2. **Parametric items (prevention, authoring cost).** Templates per D3. A run renders instances from a seed; the release publishes the templates plus the canonical instance; a suspected-contamination re-run uses a fresh seed and reports the gap. Verbatim lookup of a published instance buys nothing. Generalizing across slot values *is* the skill being measured, so that kind of "contamination" is not a threat.
3. **Held-out canary (detection).** 80–100 fixed items, not 50, from the same distribution, kept out of git, run only through providers whose terms say they do not train on API inputs. The board reports public-minus-canary COR per model with its own CI. Each release refreshes the canary and retires the old one into the public set.
4. **Altered-recall on the board (detection, free).** The probe rates on the *released* altered items, re-run for every new model. A model whose altered-recall rate sits well above its peers gets a contamination flag on its row instead of a rank. The same number, tracked release over release, shows when the public set has gone stale and needs a refresh.
5. **Temporal tag and canary string (hygiene, free).** Every row records the model's release date against the benchmark's release date; rows for models released after the data went public are marked as such. Every data file and the README carry a BIG-bench-style canary GUID so that decontamination pipelines that honor it can filter the data out of training corpora. That is a norm, not enforcement, and the plan says so.

What we do not do: keep the answers private, or run a submission server. Both kill reproducibility, and neither is affordable.

Versioned `v2.0-<date>`; HF mirror; `inspect_ai` task so the whole thing runs in one command.

**D8 — Reported metrics.** COR (primary, clustered bootstrap by source, pairwise-bootstrap rank groups); override gap; thinking gap; per-type and per-family COR; abstain rate; public-minus-canary. Ranks are shown as groups, not integers.

**D9 — Repo shape: plain repository, no lab template.** (Marco's call, 2026-09-04.)
- A normal benchmark repo under `nullsilver-labs`: `README.md`, `code/`, `data/`, `runs/`, `results/`, `inspect/`. H1–H5 are pre-registered by the dated commit of this file, and the writeup reports verdicts against them as written.
- The zero-money rule lives in `CLAUDE.md` and `README.md` as a project rule.
- On nullsilver.com the project is a hand-authored entry in `entries.ts` with the writeup as a Markdown piece and the leaderboard table embedded at release time. A live table that reads `results/leaderboard.json` from the repo is site work, out of scope until v2.0 ships.
- Licenses: MIT for code (matches the sibling repos), CC BY 4.0 for data. v1 had no LICENSE file.

---

## 4. Pipeline v2 — keep / drop / new

**Keep (from `scripts/`, moved to `code/`):** `core/llm_client.py` (retry, reasoning plumbing), `core/config.py` provider registry (add the Chinese provider, OpenRouter, GitHub Models, a re-pointed `local`), `core/io_utils.py`, `core/reasoning.py` (+ the D6 guardrail), the clustered bootstrap and pairwise rank-group code in `leaderboard.py`.

**Drop:** `sanity_check.py` (→ recall probe), `generate.py` on crawsome (→ hand authoring, LLM-drafted at most), `validate.py` (→ warned gate), `promote.py` split logic (→ canary sampling), `human_review.py` auto-promote path. `judge.j2` is rewritten for four labels.

**Stages:**

| # | command | in → out | note |
|---|---|---|---|
| 1 | hand-edit | `data/sources.yaml` | ≥ 150 candidates |
| 2 | `probe recall` | sources → `data/recall_probe.json` | admits sources (D2) |
| 3 | `author` | one YAML per source in `data/items/` | LLM may draft; a human commits; ≤ 3 variants |
| 4 | `gate warned` | items → `data/gated.jsonl` | 3-of-4 (D4) |
| 5 | `review` | TUI; approve / edit aliases / drop | stamps reviewer + date |
| 6 | `freeze` | → `data/release/v2.0/{public.jsonl, canary.jsonl(private), recall_probe.json}` | tag |
| 7 | `run` | model × {think on/off} × {unwarned, warned} × k → `runs/<model>/<config>/raw.jsonl` | committed |
| 8 | `score` | raw → `scored.jsonl` | alias match → judge remainder (D5) |
| 9 | `board` | → `results/leaderboard.json`, `LEADERBOARD.md`, per-type/family | rank groups |
| 10 | `inspect/` | `inspect_ai` task + `CONTRIBUTING.md` PR contract | community rows |

**Item schema v2:**
```json
{
  "id": "ar2-0001",
  "source_id": "surgeon", "family": "riddle", "type": "stated",
  "original": "...", "original_answer": "the mother", "original_aliases": ["his mother", "mother"],
  "altered": "...", "answer": "the father", "aliases": ["his father", "the boy's father", "father"],
  "template": "The surgeon, who is the boy's {relation}, says ...", "slots": {"relation": ["father", "uncle", "grandfather"]},
  "why_original_fails": "The text states the surgeon is the boy's {relation}.",
  "recall_probe": {"<model>": 1.0, "<model>": 0.8},
  "altered_recall": {"<model>": 0.0, "<model>": 0.2},
  "warned_gate": {"passed": true, "solvers": 4, "models": ["..."]},
  "reviewed_by": "marco", "reviewed_at": "2026-09-..",
  "split": "public"
}
```

---

## 5. Model roster by cost tier

| tier | models | cost | role |
|---|---|---|---|
| 0 — free, run first | Chinese provider (fill in), Nous free (laguna-s-2.1, hy3, step-3.7-flash), local vLLM (qwen3.6-27b, gemma-4-31b, gpt-oss-20b/120b if VRAM allows), Gemini Flash free tier | 0 | probe models, gate models, judge, first 8–12 board rows |
| 1 — credits or community | GPT-5.4, Opus 4.7 (real thinking, Anthropic API direct), Gemini 3.1 Pro, Grok 4.20, DeepSeek/Qwen/Kimi large if not on the Chinese provider | credits | the rows readers look for; each must pass the D6 guardrail |

Rule: **v1 rows are not carried over.** Different dataset, no raw outputs, unverifiable settings.

---

## 6. Cost model (multiply by the provider's price yourself)

Per model, 350 items. Recall probe is negligible (120 sources × 5 × 8 tokens, no thinking). v1 measured ~1.6k–5k output tokens per thinking response; assume 2,500. Input ≈ 150 tokens per call.

| profile | calls | thinking calls | ≈ output tokens |
|---|---|---|---|
| **full** (k=5, think on+off, unwarned+warned) | 7,000 | 3,500 | ~9M |
| **lean** (k=3 unwarned think on+off; k=1 warned think on) | 2,450 | 1,400 | ~3.6M |
| **minimal** (k=3, unwarned, think on only) | 1,050 | 1,050 | ~2.6M |

Free and local models run `full`. Credit-funded models run `lean` and the profile is printed on their row. Judge cost is ~30% of answers × ~100 tokens, and zero on the local judge.

---

## 7. Milestones and acceptance checks

| # | milestone | acceptance | est. |
|---|---|---|---|
| M0 | Branch, PLAN, open decisions taken; provider inventory verified (which free routes actually answer; which providers train on inputs; local GPU availability); credit applications sent | inventory table in `NOTES.md` | this week |
| M1 | `sources.yaml` ≥ 150 candidates; recall probe on Tier 0 | ≥ 100 sources admitted, else widen candidates | 1 week |
| M2 | ≥ 450 candidate items, templates where possible; altered-recall filter; warned gate; human review | ≥ 350 public + 80–100 canary; H5 holds on gate models | 2 weeks (authoring-bound) |
| M3 | 40-item pilot on 4 Tier-0 models | alias coverage ≥ 70%; guardrail trips on a thinking-off run labeled "on"; judge–human agreement ≥ 95% on 100 answers | 3 days |
| M4 | Full runs: Tier 0 `full`; Tier 1 `lean` as credits land | every row has raw outputs + passing guardrail | 2 weeks, rate-limit-bound |
| M5 | H1–H5 verdicts; writeup with 2–3 findings; canary GUID in every file; `entries.ts` entry + piece on nullsilver.com; HF mirror; `inspect_ai` task; tag `v2.0` | piece live, every row re-derivable from `runs/` | 1 week |

---

## 8. Open decisions (Marco)

Decided 2026-09-04: no lab template (D9).

1. **Chinese provider**: which one, which models, rate limits, whether thinking can be toggled per call, and whether its terms allow training on API inputs (decides if the canary can go through it).
2. **Local GPU**: is the 3090 / RTX PRO box available for a judge and small models during M3–M4?
3. **Credits**: which programs to apply to; I can draft the applications from this plan.
4. **Licenses**: MIT code + CC BY 4.0 data?
5. **v1 in the new repo**: recommendation is `git tag v1-final eval-fixes`, keep `results/` frozen under `v1/` with a short README for the "what changed" section, and delete nothing.
6. **Naming**: keep `altered-riddles` as repo name and site slug?
7. **Canary size**: 80–100 held-out items means ~350 public out of ~450 authored. Fine, or push authoring to 500?
8. **Parametric items**: worth the extra authoring? My take: yes for `stated` and `trivialized`, where the slot is obvious; not for verse riddles.

---

## 9. Target layout

```
code/                     # pipeline (from scripts/), one module per stage
data/sources.yaml         # hand-curated sources
data/items/<source>.yaml  # ≤ 3 variants each, reviewed
data/release/v2.0/        # public.jsonl, templates.jsonl, recall_probe.json, CANARY.txt (GUID)
data/canary/              # 80–100 held-out items, out of git
runs/<model>/<config>/    # raw.jsonl, scored.jsonl, config.json — committed
results/                  # leaderboard.json, LEADERBOARD.md, judge_agreement.json
inspect/                  # inspect_ai task
v1/                       # frozen v1 results + README, for the record
```
