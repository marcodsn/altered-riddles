"""altered_riddles.gate — the warned solvability gate (PLAN.md, D4).

Every candidate item is given to the gate models with thinking ON and an
explicit warning that the riddle is a modified version of a famous one.
An item PASSES if at least --min-pass gate models give the altered answer.
Items that fail go back to the author: either a gate model found a
defensible alternative (add it to `aliases`) or the item is not entailed
(drop it). This is an empirical solvability filter, not a quality judge.

Calls are cached per (item, model). Thinking-on calls that report zero
reasoning tokens are flagged `no_thinking` (the D6 guardrail): the gate
still scores them, but the report says the model did not think.

Usage:
    .venv/bin/python -m altered_riddles.gate \\
        --models jalapeno:DeepSeek-V4-Flash-0731 jalapeno:GLM-5.3-Flash \\
                 jalapeno:Qwen3-Next-80B-A3B-Thinking jalapeno:Qwen3.5-35B-A3B
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from altered_riddles.llm import Client, effective_reasoning_tokens, gather_limited
from altered_riddles.match import extract_final_answer, label
from altered_riddles.probe import Cache, load_crawsome, load_sources, parse_model_spec

WARNED_PROMPT = (
    "This is a modified version of a well-known riddle or puzzle. The usual answer may be wrong "
    "here. Read every word and answer the question exactly as written.\n\n{text}\n\n"
    "End your reply with one line of the form:\nAnswer: <your answer in a few words>"
)
MAX_TOKENS = 16000  # 6000 truncated 45 of 440 replies inside the reasoning (2026-09-04)
# Original-answer invalidation probe (--invalidation): the mirror of the solvability gate.
# The same warned, thinking-on models are asked whether the ORIGINAL answer is still
# correct for the altered text. An item passes at >= --min-pass verdicts of "invalid".
# Report-only until the rule is adopted (PLAN.md D4).
INVALIDATION_PROMPT = (
    "This is a modified version of a well-known riddle or puzzle. Read every word of the text below. "
    "Then decide: is \"{original}\" a correct answer to this text, exactly as written? It counts as correct only "
    "if the text itself supports it; being the usual answer to the well-known version does not count.\n\n"
    "{text}\n\n"
    "End your reply with two lines:\nVerdict: valid   (or)   Verdict: invalid\nWhy: <one sentence>"
)


def parse_verdict(text: str) -> tuple[str, str]:
    """('valid' | 'invalid' | 'unknown', why-sentence) from a probe reply."""
    verdict, why = "unknown", ""
    for line in (text or "").splitlines():
        s = line.strip().strip("*").strip()
        low = s.lower()
        if low.startswith("verdict:"):
            v = low.split(":", 1)[1].strip()
            verdict = "invalid" if v.startswith("invalid") else ("valid" if v.startswith("valid") else "unknown")
        elif low.startswith("why:"):
            why = s.split(":", 1)[1].strip().strip("*").strip()
    if verdict == "unknown":
        low = (text or "").lower()
        if "verdict: invalid" in low or "verdict:** invalid" in low:
            verdict = "invalid"
        elif "verdict: valid" in low or "verdict:** valid" in low:
            verdict = "valid"
    return verdict, why
TYPES = ("stated", "hard_constraint", "negated_premise", "trivialized", "question_swap")


def answer_cluster(answer: str) -> str:
    """Cluster id for the clustered bootstrap: the memorized answer, not the wording.
    Two sources that share an original answer (the clock riddles, a crawsome
    duplicate of a hand riddle) are one recall target and one cluster."""
    a = answer.lower().strip().rstrip(".!?")
    a = re.sub(r"^(a|an|the|your|his|her|my|in the|it is|it's)\s+", "", a)
    return re.sub(r"[^a-z0-9]+", "-", a).strip("-")


def load_items(pattern: str, sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(glob.glob(pattern)):
        doc = yaml.safe_load(Path(path).read_text()) or []
        for it in doc:
            src = sources.get(it["source"])
            if src is None:
                raise SystemExit(f"{path}: item {it.get('id')} references unknown source {it['source']!r}")
            if it["type"] not in TYPES:
                raise SystemExit(f"{path}: item {it.get('id')} has unknown type {it['type']!r}")
            for key in ("id", "text", "answer", "why_original_fails"):
                if not it.get(key):
                    raise SystemExit(f"{path}: item {it.get('id')} is missing {key!r}")
            items.append(
                {
                    "id": it["id"], "source": it["source"], "family": src["family"], "type": it["type"],
                    # puzzles cluster by source (a shared number is not a shared memory); riddles by answer
                    "cluster": str(it.get("cluster") or (it["source"] if src["family"] == "puzzle" else answer_cluster(src["answer"]))),
                    "text": it["text"].strip(), "answer": str(it["answer"]).strip(),
                    "aliases": [str(a) for a in (it.get("aliases") or [])],
                    "why_original_fails": it["why_original_fails"].strip(),
                    "original_text": src["text"], "original_answer": src["answer"],
                    # an item may narrow the original aliases used to score it (a source alias that is a
                    # justification phrase, e.g. "buildings can't jump", would otherwise mark correct answers)
                    "original_aliases": [str(a) for a in (it.get("original_aliases") or src["aliases"])],
                    "note": it.get("note"), "file": path,
                }
            )
    ids = [i["id"] for i in items]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise SystemExit(f"duplicate item ids: {dupes}")
    # Hard rule: an accepted alias may never equal an alias of the original answer.
    # Such an item cannot exclude the original (scale-1 accepted "a map", which the
    # fish riddle also lists; swims-1 accepted "noon"; die-1 accepted the bare "dice").
    from altered_riddles.match import norm
    for it in items:
        acc = {norm(a) for a in [it["answer"], *it["aliases"]]}
        orig = {norm(a) for a in [it["original_answer"], *it["original_aliases"]]}
        clash = sorted(a for a in acc & orig if a)
        if clash:
            raise SystemExit(f"{it['file']}: item {it['id']} accepts {clash}, which is also an alias of the original answer; "
                             f"narrow `aliases` or `original_aliases`")
    return items


async def run(args: argparse.Namespace) -> None:
    sources = {s["id"]: s for s in load_sources(Path(args.sources))}
    if args.crawsome:
        sources.update({s["id"]: s for s in load_crawsome(Path(args.crawsome))})
    items = load_items(args.items, sources)
    if args.limit:
        items = items[: args.limit]
    specs = [parse_model_spec(m, args.provider) for m in args.models]
    clients = {p: Client(p, concurrency=args.concurrency, retries=8, rpm=args.rpm, timeout=args.timeout) for p in {p for p, _ in specs}}
    cache = Cache(Path(args.cache))

    def key_of(item, prov, model):
        # the text hash makes an edited item invalidate its cached verdicts
        h = hashlib.sha256(item["text"].encode()).hexdigest()[:8]
        return f"G|{item['id']}|{h}|{prov}:{model}"

    def ikey_of(item, prov, model):
        h = hashlib.sha256((item["text"] + "\x00" + item["original_answer"]).encode()).hexdigest()[:8]
        return f"I|{item['id']}|{h}|{prov}:{model}"

    todo = [(it, p, m, "G") for it in items for p, m in specs if cache.get_ok(key_of(it, p, m)) is None]
    if args.invalidation:
        todo += [(it, p, m, "I") for it in items for p, m in specs if cache.get_ok(ikey_of(it, p, m)) is None]
    if args.cached_only:
        print(f"--cached-only: {len(todo)} missing replies will count as errors", file=sys.stderr)
        todo = []
    n_calls = len(items) * len(specs) * (2 if args.invalidation else 1)
    print(f"items={len(items)} models={len(specs)} calls={n_calls} todo={len(todo)}", file=sys.stderr)

    async def one(job):
        it, prov, model, kind = job
        if kind == "G":
            msg = WARNED_PROMPT.format(text=it["text"])
            key = key_of(it, prov, model)
        else:
            msg = INVALIDATION_PROMPT.format(text=it["text"], original=it["original_answer"])
            key = ikey_of(it, prov, model)
        reply = await clients[prov].chat(model, [{"role": "user", "content": msg}], max_tokens=MAX_TOKENS, thinking=True)
        cache.put(key, item=it["id"], model=f"{prov}:{model}", reply=reply.as_dict())
        return reply

    t0 = time.monotonic()
    if todo:
        await gather_limited([one(j) for j in todo], progress_every=50, label="gate calls ")
    print(f"done in {time.monotonic()-t0:.0f}s", file=sys.stderr)

    # ---------------------------------------------------------------- score
    out_rows = []
    per_model: dict[str, Counter] = defaultdict(Counter)
    for it in items:
        answers: dict[str, Any] = {}
        n_correct = 0
        for prov, model in specs:
            mname = f"{prov}:{model}"
            row = cache.get_ok(key_of(it, prov, model))
            if row is None:
                answers[mname] = {"label": "error"}
                per_model[mname]["error"] += 1
                continue
            rep = row["reply"]
            final = extract_final_answer(rep["text"])
            lab = label(final, correct=[it["answer"], *it["aliases"]], original=[it["original_answer"], *it["original_aliases"]])
            no_thinking = not effective_reasoning_tokens(rep)
            answers[mname] = {
                "final": final, "label": lab, "reasoning_tokens": rep.get("reasoning_tokens"),
                "completion_tokens": rep.get("completion_tokens"), "no_thinking": no_thinking,
                "finish_reason": rep.get("finish_reason"),
            }
            per_model[mname][lab] += 1
            if no_thinking:
                per_model[mname]["no_thinking"] += 1
            if lab == "correct":
                n_correct += 1
        solvable = n_correct >= args.min_pass
        row_out = {**it, "gate": {"models": answers, "n_correct": n_correct, "passed": solvable, "solvable": solvable}}
        if args.invalidation:
            verdicts: dict[str, Any] = {}
            n_invalid = 0
            for prov, model in specs:
                mname = f"{prov}:{model}"
                irow = cache.get_ok(ikey_of(it, prov, model))
                if irow is None:
                    verdicts[mname] = {"verdict": "error", "why": ""}
                    continue
                v, why = parse_verdict(irow["reply"]["text"])
                verdicts[mname] = {"verdict": v, "why": why[:300], "reasoning_tokens": irow["reply"].get("reasoning_tokens")}
                n_invalid += int(v == "invalid")
            inv_ok = n_invalid >= args.min_pass
            row_out["invalidation"] = {"models": verdicts, "n_invalid": n_invalid, "passed": inv_ok}
            # D4 amendment (2026-09-05): with the probe on, an item passes only if it is BOTH
            # solvable when warned AND its original answer is judged invalid by >= min_pass models.
            row_out["gate"]["passed"] = solvable and inv_ok
        out_rows.append(row_out)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.out).open("w") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---------------------------------------------------------------- report
    n_pass = sum(1 for r in out_rows if r["gate"]["passed"])
    rule = f">= {args.min_pass} of {len(specs)} correct when warned" + (f" AND >= {args.min_pass} of {len(specs)} call the original invalid" if args.invalidation else "")
    print(f"\nitems={len(out_rows)} passed={n_pass} failed={len(out_rows)-n_pass} (rule: {rule})")
    by_type = Counter((r["type"], r["gate"]["passed"]) for r in out_rows)
    for t in TYPES:
        tot = by_type[(t, True)] + by_type[(t, False)]
        if tot:
            print(f"  {t:16s} {by_type[(t, True)]:3d}/{tot}")
    print("\nper model (warned, thinking on):")
    for m, c in per_model.items():
        print(f"  {m:45s} correct={c['correct']} original={c['original']} both={c['both']} unmatched={c['unmatched']} error={c['error']} no_thinking={c['no_thinking']}")
    failed = [r for r in out_rows if not r["gate"]["passed"]]
    if failed:
        print(f"\nFAILED items ({len(failed)}), each model's final answer:")
        for r in failed:
            why = "not solvable when warned" if not r["gate"].get("solvable", True) else "original answer still valid"
            print(f"- {r['id']} [{r['type']}] expected {r['answer']!r}  ({why})")
            for m, a in r["gate"]["models"].items():
                print(f"    {m.split(':',1)[1][:28]:28s} {a.get('label','?'):9s} {a.get('final','')[:90]!r}")
    unmatched = [(r["id"], m, a["final"]) for r in out_rows if r["gate"]["passed"] for m, a in r["gate"]["models"].items() if a.get("label") == "unmatched"]
    if unmatched:
        print(f"\nunmatched answers on PASSED items ({len(unmatched)}), candidates for aliases:")
        for iid, m, fin in unmatched[:60]:
            print(f"    {iid:22s} {m.split(':',1)[1][:24]:24s} {fin[:80]!r}")
    if args.invalidation:
        still_valid = [r for r in out_rows if not r["invalidation"]["passed"]]
        vc = Counter(v["verdict"] for r in out_rows for v in r["invalidation"]["models"].values())
        print(f"\ninvalidation probe: verdicts {dict(vc)}; items where the ORIGINAL is still valid per < {args.min_pass} of "
              f"{len(specs)} models: {len(still_valid)} of {len(out_rows)}")
        for r in still_valid:
            print(f"- {r['id']} [{r['type']}] original {r['original_answer']!r} vs answer {r['answer']!r}")
            for m, v in r["invalidation"]["models"].items():
                print(f"    {m.split(':',1)[1][:28]:28s} {v['verdict']:8s} {v.get('why','')[:110]!r}")
    print(f"\nwrote {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="jalapeno")
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--min-pass", type=int, default=3)
    ap.add_argument("--sources", default="data/sources.yaml")
    ap.add_argument("--crawsome", default="data/riddles_source.csv", help="crawsome CSV; item sources craw-NNNN resolve here")
    ap.add_argument("--items", default="data/items/*.yaml")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--rpm", type=int, default=None, help="cap requests per minute per provider")
    ap.add_argument("--timeout", type=float, default=600.0, help="seconds per request; slow reasoning models need 1800+")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cached-only", action="store_true", help="no API calls: report from the cache, missing replies count as errors")
    ap.add_argument("--invalidation", action="store_true", help="also run the original-answer invalidation probe; an item then passes only if it is solvable AND its original is judged invalid (PLAN.md D4, amended 2026-09-05)")
    ap.add_argument("--cache", default="data/probe/gate_cache.jsonl")
    ap.add_argument("--out", default="data/gated.jsonl")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
