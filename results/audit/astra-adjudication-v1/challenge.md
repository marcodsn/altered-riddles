## Review

**AI read-only consistency challenge**, not human review, blinded adjudication, or independent empirical validation. I read all 15 packet cases, the first assessment, current scorer/matcher, provenance manifest, candidate-item references, and both pending cap scored rows.

- **Correct:** The first assessment generally distinguishes answer commitments from incidental alias mentions and keeps item validity separate from answer labels.
- **Finding: P1 — historical-32 incorrectly accepted a constraint-violating answer.** `assessment.md:122–129` labels “glue stick” correct despite the question specifying bottled adhesive (`results/audit/astra-adjudication-v1/review_packet.json:226–250`; `data/gated.jsonl:181`). The selected product, not just its explanation, violates the distinguishing constraint. **Recommended correction: `other`. Supervisor approved.**
- **Finding: P2 — historical-18’s hypothetical reading is insufficiently supported.** `assessment.md:72–79` treats “so the stairs would be yellow too” as hypothetical. The response supplies no counterfactual condition; “so” instead introduces an inferred answer, conflicting with “There are no stairs” (`review_packet.json:108–126`). **Recommended correction: `other`, medium confidence. Supervisor approved; interpretive sensitivity remains.**
- **Fixed:** No files or historical labels changed.
- **Merge verdict: OK with notes** for these read-only recommendations. Do not adopt the first assessment unchanged.

Here, `assessment.md` denotes the supplied first-assessment artifact under the session’s `adjudication/` output directory.

### Rubric and approved clarification

The current rubric defines semantic `correct`/`original`, `abstain`, and `other`, including “several answers at once” (`altered_riddles/score.py:51–54`). Mixed alias matches ordinarily require judging rather than first-answer or longest-alias precedence (`altered_riddles/match.py:78–107`).

The supervisor confirmed the first assessment’s six-point `astra-answer-interpretation-v1` for this scoped challenge:

1. Grade substantive commitments, not incidental mentions.
2. Unresolved incompatible answers are `other`; explicit withdrawal or clear final recommitment can resolve them.
3. Hypothetical alternatives do not displace unconditional answers.
4. Incidental “trick” wording does not erase a substantive answer.
5. Bad supporting explanation alone need not invalidate an identifiable answer.
6. Keep answer labels separate from item-validity concerns.

**Explicit qualification to point 5, approved during this challenge:** bad explanation may be ignored only when it does not change the selected object or violate a distinguishing constraint. Thus a glue stick does not qualify merely because it is a glue subtype.

These are scoped adjudication interpretations, **not changes to repository code or a claim that unaudited scores already comply**.

### Final recommended dispositions

Packet references below are to `results/audit/astra-adjudication-v1/review_packet.json`.

| Case | First assessment → recommendation | Rationale |
|---|---|---|
| **historical-1** | original → **original** | “His mother” is the committed relationship. “Other uncle’s spouse” does not identify the surgeon as an uncle; an incidental alias occurrence cannot supply that answer. High confidence. Packet:5–30. |
| **historical-7** | original → **original** | The repeated-subtraction answer is offered under an alternative interpretation, followed by explicit recommitment: “So the classic answer is: once.” The answer remains once under the approved commitment rule. High confidence; interpretation-sensitive. Packet:32–56. |
| **historical-10** | other → **other** | “Yellow” and “there are no stairs down to a basement” are incompatible substantive answers, with neither clearly withdrawn. The item explicitly states yellow basement stairs. Medium confidence. Packet:58–78. |
| **historical-17** | other → **other** | “The smoke blows west” conflicts with “there is no smoke.” Both refer to smoke; “but” alone does not clearly retract the first answer. Medium confidence. Packet:80–106. |
| **historical-18** | original → **other** | “There are no stairs” conflicts with the inferred conclusion “so the stairs would be yellow too.” Unlike an explicit counterfactual, “would” alone does not establish an uncommitted alternative. **Disagreement; supervisor-approved disposition.** Medium confidence. Packet:108–126. |
| **historical-19** | original → **original** | “There are no stairs” is categorical; the yellow alternative is introduced conditionally: “if everything is yellow, the stairs would also be yellow.” Retain the hypothetical reading under the approved interpretation, although it is not as explicit as historical-25. “Trick” does not erase the committed answer. Medium confidence; alternative inferential reading could yield `other`. Packet:128–146. |
| **historical-20** | other → **other** | “A garbage truck (or a plane that carries waste)” offers two live alternatives. Neither is withdrawn; the correct plane alternative does not rescue the mixture. High confidence. Packet:148–176. |
| **historical-24** | original → **original** | “There is no smoke” answers the question. West describes **steam**, explicitly distinguished from smoke, so this is not the same contradiction as historical-17. Its physical explanation is wrong, but its commitment is identifiable. High confidence. Packet:178–204. |
| **historical-25** | original → **original** | The answer categorically denies stairs. “If stairs existed, they’d be yellow” is explicitly counterfactual and does not replace that answer. “Not necessarily” does not justify the categorical denial. High confidence. Packet:206–224. |
| **historical-32** | correct → **other** | The proposed object is a **glue stick**, not bottled adhesive. Calling that product bottled does not satisfy the constraint. The brown-stick clause repeats background, so `original` is not the appropriate replacement. **Disagreement; supervisor-approved disposition.** High confidence under the clarified constraint rule. Packet:226–250. |
| **historical-33** | other → **other** | “None” conflicts with “breakfast is the only morning meal” and “you eat breakfast in the morning.” No clear replacement cue withdraws “none”; incidental trick wording does not make this an abstention. Medium confidence. Packet:252–273. |
| **historical-34** | other → **other** | “None” conflicts with “breakfast is the morning meal.” It neither consistently selects breakfast nor expresses the original lunch-and-dinner answer. High confidence in `other`, regardless of whether the explanation is treated as a second commitment. Packet:275–296. |
| **historical-41** | other → **other** | “Your word (a cold)” presents different answer objects without a correction cue. Parentheses alone do not select the cold over the original answer. High confidence. Packet:298–323. |
| **cap-unwarned-thinkon-k5-cap64000-3** | other → **other** | “He didn’t open the sandwiches” identifies neither dehydration nor parachute failure. Sharing the unopened-package motif is insufficient for `original`. High confidence. Packet:325–354. |
| **cap-warned-thinkon-k5-cap64000-1** | other → **other** | “Nothing, they are not alive” commits to an unsupported answer rather than refusing or withholding one. It identifies neither dehydration nor parachute failure. High confidence. Packet:356 onward. |

**Recommended totals:** **0 correct, 5 original, 10 other, 0 abstain, 0 unresolved.**

Two disagreements with the first assessment: **historical-18 and historical-32**. These totals describe only this selected packet, not population-level judge accuracy.

### Item-validity concerns, separate from dispositions

- **Two-story-house wording:** `data/gated.jsonl:50` says “A two-story house has stairs” in its justification. Two stories alone do not logically guarantee stairs. The question nevertheless presupposes stairs and supplies their color through “everything is yellow.” This is a justification/presupposition weakness, not sufficient grounds here to accept an unsupported categorical “no stairs.” Applies to historical-18, historical-19, and historical-25.
- **Steam-train direction:** `data/gated.jsonl:41` permits west and southwest variants. Precise plume direction depends on physical/frame assumptions not fully specified. This does not rescue either response’s denial of smoke. Applies to historical-17 and historical-24.
- **Repeated subtraction:** “From 25” retains the familiar wordplay, but “until nothing is left” specifies the repeated process ending at zero (`data/gated.jsonl:252`). This is minor wording sensitivity, not grounds to change historical-7 to correct.
- **No corresponding defect found** in the bottled-glue constraint or repaired dehydration question. The problematic claims in historical-32 and the two cap answers belong to the responses.

No item exclusion or historical item rewrite is recommended by this challenge.

### Provenance and validation limits

- `input_manifest.json` maps all 15 cases to item/run/sample identities. Its recorded hashes were read, **not independently recomputed**.
- Both cap answers match their pending scored rows:
  - `runs/cap-sensitivity-v1/nous_meituan_longcat-2.0_free/unwarned-thinkon-k5-cap64000/scored.jsonl:26`
  - `runs/cap-sensitivity-v1/nous_meituan_longcat-2.0_free/warned-thinkon-k5-cap64000/scored.jsonl:32`
  
  Both record `finish_reason: "stop"`, not length truncation.
- The repaired dehydration item is at `results/audit/adjudication-v2/repairs.gated.jsonl:6` and `core.candidate.jsonl:262`.
- The full-board manifest identifies scorer-v2 candidate runs. The cap README explicitly treats the new runs as a separate repair-slice diagnostic. These recommendations do not replace that board or justify attributing differences solely to the cap.
- No inference calls, external requests, secret reads, edits, tests, shell commands, staging, or child launches were performed by this reviewer. Raw and historical scored artifacts were untouched.
- The supervisor separately verified an empty Git index; that is parent-provided evidence, not a reviewer-executed check.