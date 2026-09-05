# Altered items

One YAML list per file, any grouping; every item names its `source` from
`data/sources.yaml`. The freeze step flattens these into the release.

```yaml
- id: candle-1            # <source>-<n>
  source: candle
  type: hard_constraint   # stated | hard_constraint | negated_premise | trivialized | question_swap
  text: "I'm tall when I'm young and short when I'm old, and you sharpen me to write. What am I?"
  answer: "a pencil"
  aliases: ["pencil"]
  why_original_fails: "A candle is never sharpened to write; the clause pins pencil."
  note: optional
  cluster: optional     # bootstrap cluster; default = normalized original answer (riddles) or source (puzzles)
```

## The rule that every item must satisfy

The altered answer is **entailed** by the text, and the original answer is
**excluded** by it. Not "suggested", not "more plausible": a careful reader
who has never heard the original arrives at the altered answer and nothing
else. If two answers fit, either pin it with another clause or drop it.

Types (PLAN.md D3, plus one):

| type | what changed | example |
|---|---|---|
| `stated` | the answer is written in the text | "the surgeon, who is the boy's grandfather, says 'he is my grandson'. Who is the surgeon?" |
| `hard_constraint` | a numeric or lexical constraint excludes the original and pins the new answer | "...and you sharpen me to write" |
| `negated_premise` | a premise the original answer depends on is flipped | "A mother and her son are in a car accident. The mother dies ... the surgeon says 'he is my son'" |
| `trivialized` | the famous complication is removed; the puzzle is now plain | "The bat costs $1.00. How much does the ball cost?" (total $1.10) |
| `question_swap` | same premises, a different question, so the memorized answer answers the wrong question | "...How much does the bat cost?" |

## Do not

- Reuse an alteration that is itself famous (the surgeon-who-is-the-father
  version, the "post office" envelope riddle). Those are memes, not tests.
- Write new metaphor riddles with an LLM-chosen answer. That was v1's 29%
  "neither" bucket.
- Author more than three items per source. Breadth across sources is what
  shrinks the confidence interval.

## Aliases

List every phrasing that a correct, careful answer could take. The warned
gate prints unmatched answers from models that passed; add the defensible
ones. `aliases` are matched deterministically first; only non-matches go to
the judge.

## What thinking models still fall for (pilot, 2026-09-05)

Thinking erases override on `trivialized`, `negated_premise`, `hard_constraint` and
`question_swap` (2–5%) but barely touches `stated` (23%). The traces show models
reading the correct answer and choosing the famous one anyway because "they might
think I don't get the joke". Items that keep the famous frame intact and put the
answer in plain sight are the ones with headroom. Prefer them, still entailed.

An item that thinking-on models override *more* than thinking-off models is listed
by `board` under "Items to review": reasoning found a defensible alternative, so
the item is probably ambiguous. Re-pin or drop; never auto-drop.

## The construction that survives thinking (n = 119, 2026-09-05)

Side by side, the items thinking models still override share one shape, and the
items they never miss lack it:

- the famous **question is kept word for word**;
- the joke answer stays **superficially available** (the model must actively reject it);
- **one small insertion** into the premises, reading like the asker's own slip, makes the
  plain-reading answer entailed and the joke answer wrong.

Catches: "...Nono, **and Nunu**. What is the name of the fifth daughter?"; "How many months
have **exactly** 28 days?"; "...**what colour is it** when you pull it out?".
Misses: changing the question ("How many daughters does Mary's father have?"), removing the
joke's trigger ("Moses" -> "Noah"), or making the joke answer correct ("Lucy's father").
Tag such items in `note:` with "minimal insertion" so they can be analysed as a group.

