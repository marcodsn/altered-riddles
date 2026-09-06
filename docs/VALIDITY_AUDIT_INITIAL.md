# Initial validity audit — AI advisory, not human adjudication

Reviewed directly from `data/gated.jsonl`; existing items and scores are unchanged.
These are specific counter-readings to investigate, not measured error rates or
automatic exclusions. This review is by the coding assistant, not an independent
human reviewer.

| Item | Concern | Suggested action |
|---|---|---|
| `parachute-1` | Sandwiches and an empty water bottle do not entail death by thirst. Other causes, including a fall, remain possible. The package is not a parachute, but that alone does not exclude a failed parachute as cause of death. | Exclude from a strict entailment release unless rewritten and rerun. Source admission is separately flagged in PLAN.md. |
| `months-28-days-1` | No common-year assumption is stated; in a leap year no month has exactly 28 days. The original answer is excluded, but the accepted answer is not unconditionally entailed. | Add a common-year premise and rerun. |
| `marys-father-1` | A father of Mary is said to have exactly five daughters, all named otherwise. Under the intended conventional assumptions this is inconsistent; aliases/nicknames could reconcile it but then do not cleanly exclude Mary. | Rewrite without contradictory family premises; do not count detecting the contradiction as conditioned override. |
| `johnnys-mother-1` | Same naming/count problem: Johnny exists as her child, while three children are exhaustively named April, May and June. Multiple names could reconcile this, undermining original-answer invalidation. | Rewrite and rerun. |
| `mustard-family-3` | Six daughters each having one brother conflicts with six brothers in one ordinary sibling group. Half-sibling/subfamily readings need unstated structure. The arithmetic target is explicit but the relational premises need review. | State a consistent six-son family rather than retaining 'each ... one brother of her own'. Rerun changed text. |
| `hiccups-1` | Receiving water is a natural reason for thanks, but not a logically unique one; water may also relieve hiccups. Removing a gun does not make hiccups impossible. | Rewrite to explicitly state the reason/condition, or exclude under strict entailment. |
| `rooster-egg-2` | A hen can lay an egg on a roof without it rolling; roof geometry and motion are unspecified. Replacing rooster with hen excludes the famous justification but does not establish rolling. | Add a rolling/sloped-roof premise, then rerun. |
| `married-boat-1` | Going below deck directly explains nonvisibility. Everyone being married is compatible with the scene but does not answer the revised 'Why can't you see anyone?' question. | Likely keep under an answer-relevance standard, but document that exclusion concerns answering the question, not falsity of the proposition 'everyone is married'. |
| `bear-house-1` | Explicit brown color determines the requested answer; the familiar polar geography makes the situation unusual, not necessarily contradictory (e.g. a transported brown bear). | Likely keep; inspect whether response actually rejects an impossible-world assumption versus ignoring the explicit color. |
| `yellow-hat-1` | 'Wet' is not a color and does not answer the question. Yellow is the ordinary reading, though physical changes are not exhaustively excluded. | Likely keep under ordinary-world assumptions; specify that standard consistently across items. |
| `last-brick-2` | Two bricks remain before completion, but 'it takes the last brick to complete' remains a possible event-boundary reading of 'complete'. | Human adjudication or ask explicitly how many additional bricks must be laid. |

## Implication for Hard

Some concentrated failures may arise from contradictory or underdetermined items.
Do not turn the observed-failure subset into a public Hard leaderboard until these
are adjudicated. Lower COR after removing invalid items is an improvement in
measurement validity, not a reason to keep invalid difficulty.

## External free-model review attempt

`results/audit/validity-free-v1/` records four bounded requests: two five-item
batches to each of `stepfun/step-3.7-flash:free` and `upstage/solar-pro4:free`.
Both IDs were present in the Nous model catalog. Every request returned HTTP 400
with `Additional info: missing tags`. No successful reviews were obtained, no
votes were counted, and no paid provider was substituted. Request attempts and
errors are preserved; token usage was not returned. The requested routes were
free; there is no provider billing receipt to independently verify charges.

Do not resolve this error by guessing undocumented metadata or repeatedly sending
requests. Verify the provider's current request contract before another run.
