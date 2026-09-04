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
- **H5 — clean items.** On gate models' *unwarned* answers, the "neither" share ≤ 10% (v1: 29%), and 0 items are unsolved by every warned gate model (v1: 23%).

The writeup leads with H2 and H3 and the per-type table, not with the leaderboard.

---

## 2. Constraints (the honest budget)

- **Money: about $90 of credit on Jalapeno Cloud (`api.jalapeno-cloud.ai`), and Marco can ask for more.** Nothing else is paid for. Any spend beyond that credit is Marco's explicit decision, and every credit-funded row on the board says where the credits came from.
- **Jalapeno Cloud, verified 2026-09-04 with one-riddle smoke calls** (provider `jalapeno` in `config.py`; `JALAPENO_API_KEY` in `.env`):
  - 21 models listed, `MiniMax-M3` returns 404, so 20 usable. Prices are in section 6 (pasted by Marco from the marketplace). **The provider is in beta and Marco is beta-testing it:** some listed models error, and availability changes. Every run checkpoints per item, retries with backoff, records its error rate, and a row with > 5% unrecoverable errors is not scored (v1's Opus row had 92 errors and was).
  - Thinking switches differ per family and none of them is OpenAI's `reasoning_effort` (DeepSeek ignores it). Table in section 5. The D6 guardrail is what makes this safe: a row is scored only if the reasoning-token count in `usage` matches the requested mode.
  - Terms of service (MAGIK COMPUTE PTE. LTD., Singapore) do not say whether API inputs are used for training. Assume they may be.
- **Other compute, in order of certainty:** Nous Portal free tier, six models on 2026-09-04 (`poolside/laguna-s-2.1`, `poolside/laguna-xs-2.1`, `inclusionai/ling-3.0-flash-fin`, `meituan/longcat-2.0`, `stepfun/step-3.7-flash`, `upstage/solar-pro4`, all `:free`; rate limits unpublished); local GPUs (the RTX 3090 + RTX PRO used by remora/flint, when free) for a judge and the small open models under vLLM, since the old `10.8.0.5:8083` box is down; vendor free tiers (Google AI Studio, GitHub Models, OpenRouter `:free`), to verify before counting on them; research-credit programs (OpenAI, Anthropic, Google), applied for in M0; community runs through the `inspect_ai` task for anything we cannot fund.
- **Time.** Marco part-time. Human review of ~400 items is 1–2 days. Item authoring is the dominant human cost; LLM drafting helps, humans commit.

---

## 3. Design decisions

**D1 — Sources: hand-curated, two families, breadth over depth.**
- `riddle`: the famous ones (surgeon, candle, keys-without-locks, towel, footsteps, echo, map, coin, needle, ...).
- `puzzle`: famous trick puzzles (bat-and-ball, Monty Hall, river crossing, two doors, three switches, trolley variants, ...).
- Crawsome items are admitted only if they pass D2.
- Targets: ≥ 120 sources, ≤ 3 variants per source, 300–400 items + 50 canary. Breadth across sources is what shrinks the clustered CI.
- `data/sources.yaml`: text, canonical answer, aliases, family, provenance URL. Hand-written.

**D2 — Recall probe: familiarity per model, verbatim recall per source.**
- Probe A (familiarity): thinking off, `max_tokens=8`, 5 samples on the *original* riddle. Pass at ≥ 4/5 canonical. This does not prove recall, since a model can reason its way to a famous answer in a few tokens, and that is fine: what COR needs is that the model produces the original answer when asked the original riddle, and Probe A is exactly that, cheaply.
- Probe B (verbatim recall): prefix = the first ~60% of the original text, ask the model to continue; pass at normalized token overlap ≥ 0.8. Completing the exact wording cannot come from reasoning, so this is the memorization evidence. Recorded per source and per model.
- A source is **admitted** if Probe A passes on at least three quarters of the probe models and Probe B passes on at least one. Hand-picked famous riddles should pass trivially; the gate exists for crawsome items and the trick puzzles.
- Probe models, fixed 2026-09-04 before the first full run: DeepSeek-V4-Flash-0731, Qwen3-Next-80B-A3B-Instruct, Qwen3.5-35B-A3B, Kimi-K2.5 on Jalapeno, and the four Nous free models whose thinking switches off cleanly (`poolside/laguna-s-2.1`, `poolside/laguna-xs-2.1`, `inclusionai/ling-3.0-flash-fin`, `meituan/longcat-2.0`). Eight models, so admission is 6 of 8. GLM-5.3 is excluded because it talks past a 16-token budget; `stepfun/step-3.7-flash:free` and `upstage/solar-pro4:free` reject thinking-off requests.
- COR for a given model conditions on **that model's** Probe A pass for the source. This replaces v1's "solved the original" and is ~free (8 tokens, no thinking).
- **Construction log, 2026-09-04.** First full probe over 148 hand sources and 395 crawsome riddles: only 38 crawsome riddles are familiar to models at all (282 of 395 pass on zero probe models), which is v1's source problem measured. 32 hand sources failed admission; inspecting their verbatim continuations showed two kinds: sources where models recite a *different* riddle from the same opening (table → the Sphinx riddle, shoe → the towel riddle), which the criterion is right to reject, and sources the models clearly recite but the scorer under-counted ("twelve" vs "12", an appended answer, a dropped "What am I?"). The scorer was fixed for the second kind (number words, formulaic tail, prediction cut to remainder length); the thresholds were not touched.
- **Construction log, continued.** Three more things came out of inspecting admissions. (1) A rule amendment: for *puzzles*, Probe A conflates familiarity with instant computability (mustard-family is recited word for word by all 8 models but two small ones cannot produce "nine" in 16 tokens), so near-unanimous recitation is now an alternative sufficient condition: admitted if (A on ≥ 6/8 and B on ≥ 1) **or** B on ≥ 6/8. (2) A scorer flaw: comparing the model's output against the *full* riddle credited it for repeating the prefix it was given; the remainder is now matched against the best-aligned window of the continuation only. (3) A data bug: v1's crawsome CSV is unquoted and 284 of 395 riddles contain commas; v1's loader split on the last comma, the v2 loader split on the first, so those 284 were probed as fragments with garbage answers. The loader now mirrors v1 and the affected sources were re-probed. Every one of these is a construction-time decision, taken before any benchmark run and logged here. **Final admissions (2026-09-04, 8 probe models, 0 error calls):** riddles 105 of 126, puzzles 32 of 38, crawsome 127 of 395, 264 sources in all; 17 of the 264 came in through the verbatim-only path. The crawsome half of v1's source list is still two thirds unfamiliar to every model.

**D3 — Alteration types: entailed, not suggested. Five checkable types only** (a fifth, `question_swap`, was added while authoring batch 1 on 2026-09-04: it is the cleanest type for numeric puzzles and was missing from the review's four).

| type | definition | example |
|---|---|---|
| `stated` | the answer is written in the text (includes v1's bias probes) | "The surgeon, who is the boy's father, ..." |
| `hard_constraint` | a numeric or lexical constraint excludes the original | "What five-letter word ... and is a fruit" |
| `negated_premise` | a premise the original answer needs is negated | "What has keys but does not open locks, and has no music" |
| `trivialized` | the famous complication is removed | bat-and-ball where the bat is stated to cost $1.00 |
| `question_swap` | same premises, a different question, so the memorized answer answers the wrong question | "...How much does the bat cost?" |

Every item carries `why_original_fails` (one checkable sentence) and `aliases`. `meaning_shift` and `context_swap` are dropped: they generate new metaphor riddles with LLM-chosen answers, which is the 29% bucket.

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

**D7 — Release and contamination: the cheap, standard things only.**

Contamination of the *originals* is the premise, not a problem. The risk is the altered items being looked up by a model trained after release. Almost no benchmark does more than the following, and neither will we:

- **Everything public except ~50 canary items**, same distribution, kept out of git. The board carries one column, public-minus-canary COR. With 50 items that column detects only gross contamination (the canary's own CI is around ±15 points on COR), and the README says so. The canary runs through Jalapeno like everything else; if a canary leaks, the next release rotates it into the public set and draws a new one.
- **At authoring, do not use alterations that are themselves famous.** The surgeon-who-is-the-father version has been quoted in blogs and papers since 2023. This is a human judgment while writing, helped by Probe B on the altered text: if a model completes the altered wording verbatim, it is a meme, not a test item. Answering it correctly in a few tokens proves nothing, so that is not a criterion.
- **A release date on the benchmark and a release date on every model row.** Rows for models released after the data went public are marked. Free.
- **A BIG-bench-style canary GUID** in every data file and the README, so decontamination pipelines that honor it can filter the data out. A norm, not enforcement.

Not doing: parametric items, per-model contamination flags, a private answer set, a submission server. If a later release shows a real public-versus-canary gap, that is the moment to revisit.

Versioned `v2.0-<date>`; HF mirror; `inspect_ai` task so the whole thing runs in one command.

**D8 — Reported metrics.** COR (primary, clustered bootstrap by source, pairwise-bootstrap rank groups); override gap; thinking gap; per-type and per-family COR; abstain rate; public-minus-canary. Ranks are shown as groups, not integers.

**D9 — Repo shape: plain repository, no lab template.** (Marco's call, 2026-09-04.)
- A normal benchmark repo under `nullsilver-labs`: `README.md`, `code/`, `data/`, `runs/`, `results/`, `inspect/`. H1–H5 are pre-registered by the dated commit of this file, and the writeup reports verdicts against them as written.
- The zero-money rule lives in `CLAUDE.md` and `README.md` as a project rule.
- On nullsilver.com the project is a hand-authored entry in `entries.ts` with the writeup as a Markdown piece and the leaderboard table embedded at release time. A live table that reads `results/leaderboard.json` from the repo is site work, out of scope until v2.0 ships.
- Licenses: MIT for code (matches the sibling repos), CC BY 4.0 for data. v1 had no LICENSE file.

---

## 4. Pipeline v2 — keep / drop / new

**Keep (from `scripts/`, moved to `code/`):** `core/llm_client.py` (retry, reasoning plumbing), `core/config.py` provider registry (`jalapeno` added 2026-09-04; add OpenRouter, GitHub Models, a re-pointed `local`), `core/io_utils.py`, `core/reasoning.py` (+ the D6 guardrail), the clustered bootstrap and pairwise rank-group code in `leaderboard.py`.

**Drop:** `sanity_check.py` (→ recall probe), `generate.py` on crawsome (→ hand authoring, LLM-drafted at most), `validate.py` (→ warned gate), `promote.py` split logic (→ canary sampling), `human_review.py` auto-promote path. `judge.j2` is rewritten for four labels.

**Stages (as built, 2026-09-04; every module is `python -m altered_riddles.<stage>` from the repo root, `.venv/bin/python`):**

| # | stage | in → out | note |
|---|---|---|---|
| 1 | hand-edit | `data/sources.yaml` | 148 famous riddles and trick puzzles with canonical answers and aliases |
| 2 | `probe` | sources (+ crawsome CSV) → `data/recall_probe.json` | Probe A familiarity (thinking off, 16 tokens, k=5), Probe B verbatim continuation; admission = A on ≥ 3/4 of 8 probe models and B on ≥ 1; cached per call |
| 3 | hand-edit | `data/items/*.yaml` | authored items, ≤ 3 per source, five types; rules in `data/items/README.md`; LLM may draft, a human commits |
| 4 | `gate` | items → `data/gated.jsonl` | warned prompt, thinking on, 4 gate models, pass = ≥ 3 correct; prints failures and alias candidates |
| 5 | review | edit YAML, re-run `gate` | add defensible aliases or drop; stamps come at freeze |
| 6 | freeze | → `data/release/v2.0/` | public items + `recall_probe.json` + `CANARY.txt`; canary out of git |
| 7 | `run` | model × thinking × condition × k → `runs/<model>/<config>/{config,summary}.json`, `raw.jsonl` | conditions `original` (familiarity), `unwarned`, `warned`; guardrails in `summary.json`; resumable |
| 8 | `score` | run dir → `scored.jsonl`, `scored_summary.json` | alias match first; four-way judge (`correct/original/other/abstain`) on the rest, cached; COR conditioned on the model's own familiarity ≥ 0.8 |
| 9 | `board` | all runs → `results/leaderboard.json`, `LEADERBOARD.md` | clustered bootstrap CI95 (clusters = source), pairwise-bootstrap rank groups, override gap, thinking gap; a row needs passed guardrails and committed raw outputs |
| 10 | `inspect/` | `inspect_ai` task + `CONTRIBUTING.md` PR contract | community rows (not built yet) |

**Item schema v2:**
```json
{
  "id": "ar2-0001",
  "source_id": "surgeon", "family": "riddle", "type": "stated",
  "original": "...", "original_answer": "the mother", "original_aliases": ["his mother", "mother"],
  "altered": "...", "answer": "the father", "aliases": ["his father", "the boy's father", "father"],
  "why_original_fails": "The text states the surgeon is the boy's father.",
  "recall_probe": {"<model>": {"familiar": 1.0, "verbatim": true}, "<model>": {"familiar": 0.8, "verbatim": false}},
  "warned_gate": {"passed": true, "solvers": 4, "models": ["..."]},
  "reviewed_by": "marco", "reviewed_at": "2026-09-..",
  "split": "public"
}
```

---

## 5. Model roster

**Jalapeno Cloud thinking switches, verified 2026-09-04** (one riddle each; reasoning tokens read from `usage.completion_tokens_details.reasoning_tokens`):

| model | thinks by default | switch that worked | note |
|---|---|---|---|
| DeepSeek-V4-Flash | off | on: `reasoning: {"enabled": true}` or `chat_template_kwargs: {"thinking": true}` | `reasoning_effort` ignored |
| DeepSeek-V4-Pro | on | off: `chat_template_kwargs: {"enable_thinking": false}` | |
| GLM-5.3 | on | off: `thinking: {"type": "disabled"}` | docs list `enable_thinking`; GLM-5.3-Flash gave a 400 on the off-switch once, retry |
| Kimi-K3 | on | off: `thinking: {"type": "disabled"}` | `chat_template_kwargs` did not switch it off |
| Qwen3.5-397B-A17B, 122B-A10B, 35B-A3B, 27B | on | off: `chat_template_kwargs: {"enable_thinking": false}` | |
| Hy4 | on | untested | needs `max_tokens` ≥ ~1000 or `content` comes back null |
| Kimi-K2.5, GLM-5.1 / 5.2 / 5.3-Flash, Hy3, Qwen3-Next, Qwen3-VL | untested | | |
| MiniMax-M3 | listed, 404 | | not actually served |

`core/reasoning.py` grows one dispatch entry per family above, and the D6 guardrail checks every run against `usage`.

| tier | models | cost | role |
|---|---|---|---|
| 0 — free or near-free | Nous free (laguna-s-2.1, laguna-xs-2.1, ling-3.0-flash-fin, longcat-2.0, step-3.7-flash, solar-pro4); local vLLM (qwen3.6-27b, gemma-4-31b, gpt-oss-20b) if the GPUs are free; Gemini Flash free tier if it answers; DeepSeek-V4-Flash-0731 and GLM-5.3-Flash at cents per pass | ≈ 0 | probe and gate models, judge, drafting |
| 1 — the $90 | thinking off: every Jalapeno model that answers; thinking on: DeepSeek-V4-Flash-0731, GLM-5.3-Flash, Qwen3-Next-80B-Thinking, Qwen3.5-35B-A3B, Qwen3.5-397B-A17B, DeepSeek-V4-Pro, GLM-5.3 (allocation in section 6) | credits | the board's core |
| 2 — credits or community | GPT-5.4, Opus 4.7 (Anthropic API direct), Gemini 3.1 Pro, Grok 4.20 | not ours | the rows readers look for; each must pass the D6 guardrail |

Rule: **v1 rows are not carried over.** Different dataset, no raw outputs, unverifiable settings.

---

## 6. Cost model and the $90

Assumptions: 350 items; ~150 input tokens per call; ~2,500 output tokens per thinking response (v1 measured 1.6k–5k across models); ~30 without thinking. Three run profiles:

| profile | what | calls | ≈ M tokens in / out |
|---|---|---:|---:|
| `off-full` | thinking off, k=5, unwarned + warned | 3,500 | 0.53 / 0.10 |
| `on-lean` | thinking on, k=3 unwarned + k=1 warned | 1,400 | 0.21 / 3.50 |
| `on-full` | thinking on, k=5, unwarned + warned | 3,500 | 0.53 / 8.75 |

The whole cost is thinking output. **Thinking-off rows are nearly free for every model, Kimi-K3 included**, so the thinking-off board can be complete; the credit goes to thinking-on rows. Jalapeno prices (2026-09-04, from Marco; the two discounted models are the workhorses for probes, gate, judge and drafting):

| model | $/M in | $/M out | off-full | on-lean | on-full | note |
|---|---:|---:|---:|---:|---:|---|
| DeepSeek-V4-Flash-0731 | 0.088 | 0.264 | $0.07 | $0.9 | $2.4 |  |
| GLM-5.3-Flash | 0.075 | 0.250 | $0.07 | $0.9 | $2.2 |  |
| DeepSeek-V4-Flash | 0.140 | 0.280 | $0.10 | $1.0 | $2.5 | same family as 0731, skip |
| Qwen3-Next-80B-A3B-Thinking | 0.150 | 1.500 | $0.24 | $5.3 | $13.2 |  |
| Qwen3-Next-80B-A3B-Instruct | 0.150 | 1.500 | $0.24 | $5.3 | $13.2 | no thinking mode |
| Qwen3-VL-235B-A22B-Instruct | 0.300 | 1.500 | $0.32 | $5.3 | $13.3 | VL, skip |
| Qwen3.5-35B-A3B | 0.250 | 2.000 | $0.34 | $7.1 | $17.6 |  |
| Qwen3.5-27B | 0.300 | 2.400 | $0.41 | $8.5 | $21.2 |  |
| Qwen3.5-122B-A10B | 0.400 | 3.200 | $0.55 | $11.3 | $28.2 |  |
| Qwen3.5-397B-A17B | 0.600 | 3.600 | $0.69 | $12.7 | $31.8 |  |
| MiniMax-M3 | 0.300 | 1.200 | $0.28 | $4.3 | $10.7 | 404 today |
| Kimi-K2.5 | 0.600 | 3.000 | $0.63 | $10.6 | $26.6 |  |
| Kimi-K2.7-Code | 0.950 | 4.000 | $0.92 | $14.2 | $35.5 | code model, skip |
| Hy4 | 0.834 | 2.501 | $0.70 | $8.9 | $22.3 | content null unless max_tokens large |
| DeepSeek-V4-Pro | 1.600 | 3.380 | $1.19 | $12.2 | $30.4 |  |
| GLM-5.1 | 1.380 | 4.400 | $1.19 | $15.7 | $39.2 |  |
| GLM-5.2 | 1.400 | 4.400 | $1.20 | $15.7 | $39.2 |  |
| GLM-5.3 | 1.400 | 4.400 | $1.20 | $15.7 | $39.2 |  |
| Qwen3-VL-235B-A22B-Thinking | 0.980 | 3.950 | $0.93 | $14.0 | $35.1 | VL, skip |
| Kimi-K3 | 3.000 | 15.000 | $3.15 | $53.1 | $132.8 |  |

**Provisional allocation of the $90** (re-done after the M3 pilot measures each model's real thinking length on 40 items):

| what | profile | ≈ $ | note |
|---|---|---:|---|
| every model that answers (≈15) | off-full | 12.0 | sum of the off-full column, skipping VL and code models |
| DeepSeek-V4-Flash-0731 | on-full | 2.4 |  |
| GLM-5.3-Flash | on-full | 2.2 |  |
| Qwen3-Next-80B-A3B-Thinking | on-lean | 5.3 |  |
| Qwen3.5-35B-A3B | on-lean | 7.1 |  |
| Qwen3.5-397B-A17B | on-lean | 12.7 |  |
| DeepSeek-V4-Pro | on-lean | 12.2 |  |
| GLM-5.3 | on-lean | 15.7 |  |
| authoring: warned gate, probes, judge | — | 5.0 | gate = 4 models × 400 candidates with thinking; judge on non-matches only, on Flash-0731 |
| **total** | | **75** | reserve ≈ $15 for retries on a beta provider |

Waiting list, in order, if the pilot comes in cheap or Marco gets more credit:

| model | profile | ≈ $ |
|---|---|---:|
| Hy4 | on-lean | 8.9 |
| Kimi-K2.5 | on-lean | 10.6 |
| Qwen3.5-122B-A10B | on-lean | 11.3 |
| Qwen3-Next-80B-A3B-Thinking | on-full | 13.2 |
| MiniMax-M3 | on-lean | 4.3 |
| Kimi-K3 | on, k=1, unwarned only | 13.3 |

Judge cost is ~30% of answers × ~350 tokens on Flash-0731, well under $1 in total. Free and local models run `on-full` regardless. Every row prints its profile.

---

## 7. Milestones and acceptance checks

| # | milestone | acceptance | est. |
|---|---|---|---|
| M0 | Branch, PLAN, open decisions taken; provider inventory verified (which free routes actually answer; local GPU availability); the $90 allocation confirmed; credit applications sent | inventory table in `NOTES.md` | this week |
| M1 | `sources.yaml` ≥ 150 candidates; recall probe on Tier 0 | ≥ 100 sources admitted, else widen candidates | 1 week |
| M2 | ≥ 400 candidate items; famous-variant check; warned gate; human review | ≥ 350 public + ~50 canary; H5 holds on gate models | 2 weeks (authoring-bound) |
| M3 | 40-item pilot on 4 Tier-0 models | alias coverage ≥ 70%; guardrail trips on a thinking-off run labeled "on"; judge–human agreement ≥ 95% on 100 answers | 3 days |
| M4 | Full runs: Tier 0 `full`; Tier 1 `lean` as credits land | every row has raw outputs + passing guardrail | 2 weeks, rate-limit-bound |
| M5 | H1–H5 verdicts; writeup with 2–3 findings; canary GUID in every file; `entries.ts` entry + piece on nullsilver.com; HF mirror; `inspect_ai` task; tag `v2.0` | piece live, every row re-derivable from `runs/` | 1 week |

---

## 8. Open decisions (Marco)

Decided 2026-09-04: no lab template (D9); contamination stays at the D7 minimum; the provider is Jalapeno Cloud with ~$90 of credit.

1. **Allocation**: OK with section 6's split (Kimi-K3 thinking-on and Hy4 wait for more credit)?
2. **Local GPU**: is the 3090 / RTX PRO box available for a judge and small models during M3–M4?
3. **Credits**: which programs to apply to; I can draft the applications from this plan.
4. **Licenses**: MIT code + CC BY 4.0 data?
5. **v1 in the new repo**: recommendation is `git tag v1-final eval-fixes`, keep `results/` frozen under `v1/` with a short README for the "what changed" section, and delete nothing.
6. **Naming**: keep `altered-riddles` as repo name and site slug?

---

## 9. Target layout

```
altered_riddles/          # v2 pipeline package (`code/` would shadow the stdlib module); v1 stays in scripts/ until the freeze
data/sources.yaml         # hand-curated sources
data/items/*.yaml         # authored items, any grouping, ≤ 3 per source; README.md holds the rules
data/release/v2.0/        # public.jsonl, recall_probe.json, CANARY.txt (GUID)
data/canary/              # ~50 held-out items, out of git
runs/<model>/<config>/    # raw.jsonl, scored.jsonl, config.json — committed
results/                  # leaderboard.json, LEADERBOARD.md, judge_agreement.json
inspect/                  # inspect_ai task
v1/                       # frozen v1 results + README, for the record
```
