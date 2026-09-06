# AI validity pass over the 253 Core items not on the human sheet (2026-09-06)

**AI review, not a human sign-off.** The coding assistant read every item in
`results/audit/core-hard-v3/validity_queue.jsonl` except the 11 on the owner's sheet
(`adjudication-v1/human_review.yaml`) and answered, per item: are the premises
consistent; is the accepted answer entailed rather than plausible; is the original
answer wrong *as an answer to this question*; is there a defensible reading of the
override; and do the recorded override labels match the actual replies.
Standard: strict entailment under ordinary readings (owner-approved 2026-09-06).

Output: `dispositions.jsonl` (id, disposition, concern, scoring note, text hash) and
`validity_queue.jsonl` (the v3 queue with status `ai_reviewed` on these 253 and
`human_sheet_pending` on the 11).

## Result

| disposition | items |
|---|---:|
| keep | 252 |
| flag for the owner | 1 |

**Flagged: `cat-fur-1`.** "A cat's left side has been shaved for surgery and its right
side has not. Which side of the cat has the most fur?" The alteration sets up a
left/right contrast, but the pun answer "the outside" is not made false: the outside
still has more fur than the inside. Under the strict standard the original answer is
not excluded. Only one override was observed, so the decision barely moves any row.
Options: keep as a Core control, rewrite to "which side, left or right", or exclude.

**Minor notes, no action proposed:** `keyboard-1` carries computer-keyboard clues
("space", "enter") into a piano answer, pinned by "88 keys"; `stamp-1` (top-right
corner) and `widows-sister-2` (legality) rest on conventions or law rather than
entailment, both true in ordinary settings; `bucket-hole-1` aliases omit snow/hail.

## Scoring findings (the reason for the matcher fix)

Fourteen items had override examples whose final reply was in fact correct or a
different wrong answer, e.g. `surgeon-1` "His grandfather (the surgeon is the boy's
mother's father)", `three-apples-3` "Three apples (the two you took plus the one in
your pocket)", `cowboy-friday-1` "Thursday (his horse is named Friday)",
`months-28-days-3` "... So the answer is 0.", `monty-hall-1` "No, you should not
switch" (token-subset match on "you should switch"), `letter-e-3` wrong counts that
name the letter. All were deterministic labels from the longer-alias tie-break, not
judge errors. See `../rescore-v1/README.md` for the fix and its effect.
