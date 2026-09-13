## Review

**AI read-only implementation review**, not human review or independent empirical validation.

- **Correct — all 15 decisions are implemented.** Direct inspection of the packet, approved dispositions, exact-bound decisions and derivative scored rows confirms **5 original, 10 other**. Historical-18 and historical-32 incorporate the approved challenge corrections. There are **12 candidate label changes, one confirmation and two separate cap changes**.
- **Correct — scope and lineage protections.** `results/audit/astra-adjudication-v1/adjudicate.py:65–83,128–137` checks extracted final answers, item grading fields, raw sample identity and candidate origin before applying historical decisions. The candidate manifest selects the original 13 configurations; the cap manifest selects only the two separate 64k runs (`candidate_run_manifest.json:2–18`; `cap_run_manifest.json:2–9`, both under that audit directory).
- **Correct — summaries and provenance.** The script recalculates label-dependent summaries while retaining base judge/scorer provenance (`adjudicate.py:151–165,198–216`). Both cap scored files contain 39 `correct` and one `other`, all with `finish_reason: stop`; pending answers are resolved at unwarned `scored.jsonl:26` and warned `scored.jsonl:32` under `runs/cap-sensitivity-adjudicated-v1/nous_meituan_longcat-2.0_free/`. Board off-row metrics agree with the reported impacts (`results/audit/astra-adjudication-v1/core-board/leaderboard.json:132–203`).
- **Correct — offline execution and current authorization.** The audit script disables dotenv before importing pipeline modules and contains no inference/client invocation. The installed dotenv implementation honors that switch. Subscription Astra authorization, verified-free-only inference and the prohibition on paid fallback are accurately recorded in `docs/CORE_RELEASE_POLICY_AMENDMENT_ASTRA_V1.md:17–25`. AI provenance is explicit; no fabricated human validation was found.
- **Fixed:** None; review-only.

### Finding: P2 — new current leaderboard retains obsolete human-review requirement

`results/audit/astra-adjudication-v1/core-board/LEADERBOARD.md:32` says:

> “Human look before publishing…”

This contradicts the current amendment’s explicit statement that no human review is required (`docs/CORE_RELEASE_POLICY_AMENDMENT_ASTRA_V1.md:68`). The new audit construction reproduces this legacy instruction through its unqualified `board.render_md(result)` call (`results/audit/astra-adjudication-v1/adjudicate.py:250`).

**Smallest fix:** qualify or replace that sentence in the audit-local rendering with an explicitly labelled AI-review instruction. Preserve historical boards and the generic scorer. Add an assertion covering the current board’s review-policy wording. This is a documentation inconsistency, **not fabricated completed human review or a scoring defect**.

### Decision coverage checked

Within `runs/core-candidate-adjudicated-v1/`, the affected scored rows are:

| Model/configuration | Historical cases → final labels | `scored.jsonl` lines |
|---|---|---|
| DeepSeek unwarned/off | 1 original; 7 original; 10 other | 11, 1224, 1260 |
| Longcat unwarned/off | 17 other; 18 other; 19 original; 20 other | 209, 229, 233, 792 |
| DeepSeek warned/off | 24 original; 25 original; 32 other; 33 other; 34 other | 199, 233, 866, 926, 930 |
| Longcat warned/off | 41 other | 699 |

Both cap cases are `other` in the separate root cited above. An exhaustive overlay-field search found exactly these 13 candidate rows and two cap rows.

### Validation and residual limits

I inspected the six regression tests, preservation inventory, manifests and recorded validation output. `checks.log` records **50 passing tests**, 780 preserved-file checks, 205 manifest bindings, exact offline board reproduction and an empty Git index. The Jalapeno-looking test log entry comes from a mocked client (`tests/test_repair_workflow.py:63–73`), not evidence of paid inference.

I did **not** execute commands, recompute hashes, inspect Git history/index directly, or compare every raw-file byte. Preservation and empty-index conclusions therefore rely partly on recorded execution evidence. No secrets were read; no secret leakage was observed in inspected artifacts, but this was not an exhaustive repository/history secret scan. Mixed-answer interpretation remains scoped; release, licensing and broader empirical-validation limitations remain open.

**Merge verdict: OK with notes.** No P1 findings; one P2 documentation correction. This does not authorize release.