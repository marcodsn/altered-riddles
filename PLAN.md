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
- **Gate outcome (2026-09-04).** 132 items were authored over 103 admitted sources under the entailment rule; the warned gate (4 models, thinking on, pass at 3 of 4) plus review left **119 items over 92 sources** (41 riddle, 51 puzzle, 27 crawsome; 56 hard_constraint, 23 question_swap, 18 negated_premise, 14 trivialized, 8 stated). That is a third of the plan's 350-item target: riddles rarely admit an entailed alteration, puzzles do. Getting to 350 means more sources or a second author pass, not looser items. H1's CI target will be re-read against whatever n the release has.

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
- Accept only items solved when warned by ≥ 3 of 4 gate models (Tier 0), *and* reviewed by Marco.
- **Amendment, 2026-09-05 (Marco's question; evidence in the construction log):** an item must *also* pass the original-answer invalidation probe: the same four warned, thinking-on models are asked whether the original answer is still correct for the altered text exactly as written, and ≥ 3 of 4 must say it is not. On the full 269-item set the probe returned 1,059 "invalid" / 15 "valid" / 1 unknown verdicts and flagged 5 items, 4 of them real flaws the solvability gate had passed (dog-woods-1, monty-hall-1, promise-1, craw-0079-1); no strong-prior item was flagged (marys-father-1 and bear-house-1 pass). A second, deterministic rule: an accepted alias may never equal an original alias. If a gate model's warned answer is a defensible alternative, either add it to `aliases` or drop the item. Every item gets `reviewed_by`, `reviewed_at`.
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

### Construction log, 2026-09-05 (after the pilot; Marco's questions and decisions)

- **Is the benchmark too easy because the gate admits only what small models solve?** Checked, no. The 8 gate failures were ambiguity, not override: 31 of the 32 gate answers on them were "other", 1 was the original. Items that barely passed (3 of 4) override twice as often as 4-of-4 items with thinking off (29% vs 14%); they stay in. Solvable-by-a-careful-reader is the design (it is what makes "original" an unambiguous error); difficulty is prior strength, not reasoning demand.
- **Where thinking models still override.** Pilot per-type override, thinking off → on: stated 27.8 → 23.3, trivialized 25.0 → 2.5, negated_premise 20.8 → 5.0, hard_constraint 13.2 → 4.2, question_swap 11.5 → 2.5. Thinking erases four types and barely touches `stated`. The Mary's-father traces show why: Qwen3.5-35B writes "Truthful based on text: Nunu" then "if I write Nunu and they know the riddle, they might think I don't get the joke" and answers Mary. That is override by intent inference, and it survives reasoning. The second authoring pass leans toward items that keep the famous frame intact (`stated`, `question_swap`).
- **Validity flag the gate cannot give.** On craw-0007-1 thinking-on models overrode 6/10 while thinking-off overrode 2/12; their traces argue an anchor's flukes are hooks. That is a defensible alternative the warned gate missed because the warning steered the models. Rule, now in `board`: an item whose thinking-on override is ≥ 30% *and* above its thinking-off override is listed under "Items to review". Human look, never auto-drop. craw-0007-1 was re-pinned ("baited hook").
- **Second authoring pass.** 176 of the 264 admitted sources had no items (the first pass stopped at 103 sources); 54 of the unused crawsome sources are the same riddle as a hand source and were skipped. Drafted 141 items: 86 over 65 hand riddles (`batch5`), 36 over 5 puzzles and 31 unique crawsome sources (`batch6`), 19 over 17 new famous sources added to `sources.yaml` (`batch7`; admitted only if the probe passes them). 260 items before the gate. Still ≤ 3 per source.
- **Clusters.** The clustered bootstrap now clusters riddles by normalized original answer, puzzles by source (a shared number is not a shared memory); an explicit `cluster:` on an item overrides. Merges among existing items: clock-hands/clock-face/craw-0058, bottle/craw-0030, egg/craw-0091, needle/craw-0204. Effective n goes down slightly; CIs get honest.
- **Stale replies.** `run` rows carry a `text_sha`; on resume, rows whose item text changed are dropped and re-answered. The judge cache key includes a hash of the judge prompt (text, aliases, answer). Before this, a rephrased item silently kept its old replies and verdicts.
- **Metric (Marco, on recommendation).** COR stays the sort key and headline; altered accuracy is the second column on the same familiar-item set; other + abstain is the guard (a row above 10% has a flattered COR and the writeup says so). On the pilot the two orderings coincide for all 8 rows because items are built so that accuracy ≈ 1 − COR − other. No composite. Two stated weaknesses of COR go in the README: per-model denominators differ slightly (83–90 of 92 sources for the strong probe models, 65 for laguna-xs), and abstaining lowers it.
- **H4 labeling.** The 100-row sheet was a random draw of all answers, so 92 rows were alias matches; the judge decided only 61 answers in the whole pilot. H4's human sample is now judge-decided rows only, blind (machine labels in a separate key file), capped at 100: `results/pilot/labeling_sheet_judge_only.jsonl`. `original`, the label COR depends on, was resolved deterministically in 130 of 131 cases, so judge error barely touches COR.
- **Probe, second pass (2026-09-05).** 13 of the 17 new sources admitted (277 in all; the earlier 264 unchanged). Not admitted: `letter-v` and `black-dog` (no verbatim recall on any model), `parachute` (familiar on 8/8 but the wording varies too much to complete verbatim), `romeo-juliet` (familiar on 3/8). Their 4 items drop at freeze.
- **Matcher fix (found on the 119-item board).** The multi-word alias rule matched when the alias's words appeared anywhere in the reply, so the original alias "a wet hat" matched "Yellow — ... so the hat just gets wet" and the longer-alias tie-break labelled a correct answer an override (yellow-hat-1, 2 of 5 GLM answers). Multi-word aliases now match only contiguously, with a token-subset fallback only for replies at most 3 words longer than the alias. Re-scored everything: pilot rows unchanged to the decimal, gate verdicts on the 119 items unchanged.
- **Stall fix (14:30).** DeepSeek's warned thinking-on run and gate pass 3 stopped moving: warned prompts push DeepSeek to a median 3.2k and p90 7.2k reasoning tokens, over ten minutes at ~10 tok/s, and the provider drops long idle connections while the client waited for the 30-minute wall timeout and then retried into the same fate (1 row per 30–40 min; short calls answered in 1.5 s throughout). The client now streams every reply and abandons an attempt only after 300 s without a chunk; verified on all five families that reasoning text and usage still arrive. Row content is unchanged, only transport. The v2 board writes to `results/v2/`; `results/` keeps the v1 files until the v1-freeze decision.
- **Gate pass 3 (batch 8), 15:50.** 15 of 20 minimal-insertion items passed; the gate rule was kept as pre-registered even though four of the five failures were *overrides under warning* (two gate models answering "none, it was Noah" to "Moses's friend Noah", "once" to "subtract 5 from 25 until nothing is left"), not ambiguity. That is the rule's cost, stated here: items whose prior beats a warned small thinking model are excluded by construction, so measurable override at the gate models' level is capped. `two-coins-3` was a real flaw (US half dimes and 20-cent pieces existed). Two right-but-unmatched items got aliases; two were re-pinned.
- **Runaway thinking on the warned prompt.** DeepSeek-V4-Flash-0731 sometimes thinks to the 16k cap and never answers (finish=length, 50–60k characters of reasoning): 8 of the first 362 warned thinking-on rows, and the items it had errored on in pass 2. Scored as no answer; the board's truncation check watches the share.
- **Answers written inside the thinking.** DeepSeek occasionally puts its final "Answer: ..." line in the thinking block and sends nothing as content (1–2% of thinking-on rows, both transports; 3 of 40 in the pilot). The scorer now takes an "Answer:" line within the last 300 characters of the reasoning when the content is empty; earlier deliberation is never read. Pilot re-scored: the change is confined to DeepSeek thinking-on 'other' rows.
- **Tie-break experiment, reverted.** jump-building-1's correct answers ("A flea — buildings can't jump") were labelled original because the source alias "buildings can't jump" is a justification phrase and the longer-alias tie-break preferred it. A positional tie-break (earliest alias wins) was tried and checked against the judge on the 263 mixed replies it would have decided: it agreed only 155 times, mislabelling self-corrections ("Light? No, sound.") and restatements ("Queue is pronounced Q — the letter Q is left"). Reverted. Mixed replies stay with the judge (D5); items may narrow the original aliases used to score them (`original_aliases`), which is what jump-building-1 now does.
- **Original-answer invalidation (Marco's question, 17:00).** v1's validator asked for answer validity, distinctness and soundness but never made "the original answer is now wrong" a hard gate; v2's warned gate tests only that the altered answer is reachable. Two rules added. (1) Hard, deterministic: an accepted alias may never equal an original alias; the gate refuses to load such an item. It would have caught scale-1 ("a map"), swims-1 ("noon") and die-1 (bare "dice"). (2) The invalidation probe (`gate --invalidation`): the four warned thinking-on gate models are asked whether the original answer is still correct for the altered text, exactly as written; pass at 3 of 4 "invalid". Report-only pending the D4 decision. First 133 items: 516 invalid / 12 valid / 1 unknown verdicts; 5 items flagged, and 4 of them are real: dog-woods-1 ("how far into a two-mile wood": halfway is still right; its 4/10 thinking-off "overrides" were correct answers), monty-hall-1 (accepted "yes, switch to door 3" while "yes, switch" stayed true), promise-1 (a resolution is a promise), craw-0079-1 (a die is a cube with six square faces unless the faces are blank). The fifth, footsteps-1, is probe noise on a question_swap: "footsteps" identifies the object but the question asks for a number. Dropped dog-woods-1 and promise-1; re-pinned monty-hall-1 (both other doors shown to hold goats: "no") and craw-0079-1 (blank faces). Recommendation: adopt the probe as a hard gate next to solvability, reading question_swap flags by hand.
- **Full Tier-0 result, 2026-09-05 21:40, 264 items over 199 sources, every item passing both gates, all rows passing the pre-publish checks, raw outputs under `runs/`, board in `results/v2/`.**

  | model | thinking | COR | CI95 | alt acc | warned acc | override gap | other | group |
  |---|---|---:|---|---:|---:|---:|---:|---:|
  | DeepSeek-V4-Flash-0731 | on (k=3) | 2.0% | [0.8, 3.5] | 96.6% | 93.9% | −2.7 | 1.5% | 1 |
  | GLM-5.3-Flash | on (k=5) | 4.2% | [2.4, 6.1] | 94.9% | 98.6% | +3.6 | 0.9% | 1 |
  | longcat-2.0 (free) | on (k=5) | 4.7% | [2.7, 6.8] | 93.6% | 93.0% | −0.7 | 1.8% | 1 |
  | longcat-2.0 (free) | off (k=5) | 12.6% | [8.9, 16.4] | 82.4% | 75.3% | −7.1 | 5.3% | 2 |
  | DeepSeek-V4-Flash-0731 | off (k=5) | 13.3% | [9.1, 17.7] | 80.9% | 76.4% | −4.5 | 6.5% | 2 |

  Thinking gap: DeepSeek 11.2 points, longcat 7.9. Per-type unwarned override, thinking off → on: stated 29.0 → 17.6, trivialized 22.0 → 6.2, negated_premise 14.2 → 2.6, hard_constraint 11.3 → 3.0, question_swap 4.4 → 0.7. The 16 surviving minimal-insertion items (batch 8): 38.8% off, 20.7% on, the highest of any construction. 183 of 264 items (69%) never produce an override in any row; 35 items carry all thinking-on override, the top five 40% of it. Familiarity coverage 187–197 of 199 sources per model. DeepSeek's warned thinking-on run truncated 42 of 798 replies (5.3%) at the 16k cap; its unwarned run, the one COR uses, is under the 5% check.

  **Pre-registered verdicts at this size (3 models, 5 rows; Tier 1 not yet run):**
  - H1 (separation): sources 199 ≥ 120 ✓; CI half-width ±1.4–2.3 for thinking-on rows ✓, ±3.8–4.3 for thinking-off rows (borderline at the ±4 target); 2 rank groups among 5 rows — the "≥ 3 groups among ≥ 10 models" clause needs the Tier-1 runs.
  - H2 (warning gives ≥ +15 points): **fails as written.** Mean override gap −2.3; −4.5 and −7.1 for the thinking-off rows, −2.7 to +3.6 with thinking on. The warning hurts the models that override most.
  - H3 (thinking lowers COR by a median ≥ 8 on ≥ 4 of 5 pairs): holds on both pairs available (11.2, 7.9; median 9.6); three more paired models needed for the clause as written.
  - H4 (alias ≥ 70%; judge–human ≥ 95%): deterministic matching resolved 85–95% of answers per run ✓; judge–human agreement pending Marco's 61-row sheet.
  - H5 (other ≤ 10%; no item unsolved by every warned gate model): other 0.9–6.5% ✓; 0 items unsolved in any warned run ✓.

  **Items to review before freeze (all genuine overrides on reading the traces, none dropped):** mustard-family-3, bear-house-1, married-boat-1, months-28-days-1, marys-father-1, johnnys-mother-1, hiccups-1, parachute-1 (source not admitted; drops at freeze), yellow-hat-1, last-brick-2. Dropped at this review because the original answer was not excluded: cowboy-friday-2 (a horse named Friday is still consistent with a seven-day stay; the invalidation probe called it invalid, reading "unnecessary" as "invalid"), greenhouse-3 (the difference is a space).
- **Runs.** `full.sh` = gate every item, then Tier-0 pipelines (DeepSeek-V4-Flash-0731 off-full + on k=3/3, GLM-5.3-Flash on-full with familiarity in thinking mode, longcat-2.0 free on/off full), score, board. Resumable; re-run after each item batch.

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
| DeepSeek-V4-Flash | off | on: `reasoning: {"enabled": true}` or `chat_template_kwargs: {"thinking": true}` | `reasoning_effort` ignored; **Reasoning mode streams at ~10 tok/s on Jalapeno** (2–8k reasoning tokens per riddle, minutes per call): run it in its own process with high concurrency, or its long calls starve every model sharing the slots. Its cost is wall-clock, not money. |
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

**Measured in the pilot (2026-09-04, 40 items, mean completion tokens per call).** Unwarned thinking is far shorter than the 2,500 assumed; the warned prompt makes models think 2–4× longer; deterministic matching resolved 82–100% of answers so the judge is ~5% of rows.

| model | thinking on, unwarned | thinking on, warned | thinking off |
|---|---:|---:|---:|
| DeepSeek-V4-Flash-0731 | 680 | ~1,500 (one call dropped by the provider) | 8 |
| GLM-5.3-Flash | 160 | 330 | — |
| Qwen3.5-35B-A3B | 1,530 | 4,700 | 5 |
| meituan/longcat-2.0 (free) | 390 | 1,550 | 7 |

Re-priced `on-full` (1,750 unwarned + 1,750 warned calls): GLM-5.3-Flash ≈ $0.2, DeepSeek-Flash-0731 ≈ $1, Qwen3.5-35B-A3B ≈ $22, so the two discounted models are effectively free at any profile and the Qwen3.5 family is where the credit goes. The allocation table above stands; the k=1 warned condition in `on-lean` is what keeps verbose thinkers affordable. DeepSeek-Flash-0731's cost is wall-clock: ~10 tok/s and connections dropped on very long calls.

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

## Core + Hard follow-up: audit foundation

Implementation/protocol: `docs/CORE_HARD_PROTOCOL.md`. Initial AI validity
findings: `docs/VALIDITY_AUDIT_INITIAL.md`. Reproducible diagnostic outputs:
`results/audit/core-hard-v2/` (prior engineering snapshot retained as v1).

- Corrected the leaderboard's independently bootstrapped pseudo-paired comparisons.
  New comparisons jointly resample clusters on shared familiar items; point ranks
  replace misleading equivalence groups. Historical tables remain untouched.
- Core point estimates remain unchanged. Exploratory paired Core differences for
  DeepSeek thinking-on versus GLM and Longcat have pointwise intervals below zero;
  the earlier blanket claim that all thinking-on rows are tied is not supported
  by the corrected comparison. This is not a multiplicity-adjusted global ranking.
- Added complete-score/sample checks, per-sample text drift checks, diagnostic
  slices, shared-familiar sensitivity, and an explicit unreviewed validity queue.
- Initial direct AI review identified underdetermination/contradiction concerns
  in the error tail. No items are automatically dropped or silently rewritten.
- Four Nous `:free` advisory requests (Step and Solar) all failed with HTTP 400
  `missing tags`; artifacts retained under `results/audit/validity-free-v1/`.
  No model review votes or paid fallback calls. Jalapeno spending deferred until
  current pricing and a bounded envelope are established.
- The initial 14 offline regression tests passed. Remaining release work is
  explicitly listed in the protocol; no human adjudication, Hard test freeze,
  or public launch yet.

### Flagged-item adjudication follow-up

- User authorized proceeding directly and supplied the Nous user tag `marcodsn`.
  The live-verified wire format is `{"tags": ["user=marcodsn"]}`; it fixes the
  missing-tag blocker. Wrong-shape probes and unsuccessful requests are retained.
- Solar Pro 4 and Laguna S 2.1 free routes supplied advisory reviews. Step requires
  reasoning and exhausted the bounded 3,000-token limit, so no Step votes count.
- Direct AI adjudication of ten flagged items recommends 3 keep, 6 revise, 1
  exclude. Reasons, disagreements, and human-pending status are recorded under
  `results/audit/adjudication-v1/`; no changes to historical active items or scores.
- Six isolated candidate repairs are in `data/revisions/core-hard-pilot.yaml`.
  They received a further blinded AI review; no difficulty scores are transferred
  from old texts. Both reviewer models misread exactly 28 days as at least 28:
  their rationales are rejected, with a deterministic Gregorian-calendar check
  added to the tests. Model agreement is not ground truth.
- Full Core adjudication, human approval, fresh repair runs, a held-out Hard set,
  and public-release checks remain outstanding. The benchmark is not launch-ready.

### 2026-09-06: decisions, AI validity pass, matcher fix

- Owner decisions: strict-entailment standard; one human reviewer plus labelled AI
  reviews (no second human); Core frozen first, Hard later; Jalapeno envelope USD 1
  for this phase, the section 6 allocation stands for the launch panel.
- Human sheet for the 10 flagged items + rooster-egg-2:
  `results/audit/adjudication-v1/human_review.yaml` (pending). AI pass over the other
  253 items: `results/audit/validity-pass-v1/` (252 keep, cat-fur-1 flagged).
- The pass found deterministic mislabels: the longer-alias tie-break counted correct
  replies that quote an original phrase as overrides. Matcher v2 sends mixed replies
  to the judge; scores now carry provenance fingerprints and the board rejects stale
  scores; runs are selected by an explicit manifest, never directory order.
  Re-score: 161 judge calls, 45 labels changed, COR moved by ≤ 0.6 points, ranks
  unchanged (`results/audit/rescore-v1/`, board `results/v2/`, audit `core-hard-v3`).
- Routes checked 2026-09-06: 7 Nous `:free` routes with catalog pricing 0, Jalapeno
  21 models (`results/audit/routes-2026-09-06/`).
