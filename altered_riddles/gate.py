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
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

from altered_riddles.llm import Client, gather_limited
from altered_riddles.match import extract_final_answer, label
from altered_riddles.probe import Cache, load_crawsome, load_sources, parse_model_spec

WARNED_PROMPT = (
    "This is a modified version of a well-known riddle or puzzle. The usual answer may be wrong "
    "here. Read every word and answer the question exactly as written.\n\n{text}\n\n"
    "End your reply with one line of the form:\nAnswer: <your answer in a few words>"
)
MAX_TOKENS = 16000  # 6000 truncated 45 of 440 replies inside the reasoning (2026-09-04)
TYPES = ("stated", "hard_constraint", "negated_premise", "trivialized", "question_swap")


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
                    "text": it["text"].strip(), "answer": str(it["answer"]).strip(),
                    "aliases": [str(a) for a in (it.get("aliases") or [])],
                    "why_original_fails": it["why_original_fails"].strip(),
                    "original_text": src["text"], "original_answer": src["answer"],
                    "original_aliases": src["aliases"], "note": it.get("note"), "file": path,
                }
            )
    ids = [i["id"] for i in items]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise SystemExit(f"duplicate item ids: {dupes}")
    return items


async def run(args: argparse.Namespace) -> None:
    sources = {s["id"]: s for s in load_sources(Path(args.sources))}
    if args.crawsome:
        sources.update({s["id"]: s for s in load_crawsome(Path(args.crawsome))})
    items = load_items(args.items, sources)
    if args.limit:
        items = items[: args.limit]
    specs = [parse_model_spec(m, args.provider) for m in args.models]
    clients = {p: Client(p, concurrency=args.concurrency, retries=8, rpm=args.rpm) for p in {p for p, _ in specs}}
    cache = Cache(Path(args.cache))

    def key_of(item, prov, model):
        # the text hash makes an edited item invalidate its cached verdicts
        h = hashlib.sha256(item["text"].encode()).hexdigest()[:8]
        return f"G|{item['id']}|{h}|{prov}:{model}"

    todo = [(it, p, m) for it in items for p, m in specs if cache.get_ok(key_of(it, p, m)) is None]
    print(f"items={len(items)} models={len(specs)} calls={len(items)*len(specs)} todo={len(todo)}", file=sys.stderr)

    async def one(job):
        it, prov, model = job
        msg = WARNED_PROMPT.format(text=it["text"])
        reply = await clients[prov].chat(model, [{"role": "user", "content": msg}], max_tokens=MAX_TOKENS, thinking=True)
        cache.put(key_of(it, prov, model), item=it["id"], model=f"{prov}:{model}", reply=reply.as_dict())
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
            no_thinking = not (rep.get("reasoning_tokens") or 0)
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
        passed = n_correct >= args.min_pass
        out_rows.append({**it, "gate": {"models": answers, "n_correct": n_correct, "passed": passed}})

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with Path(args.out).open("w") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---------------------------------------------------------------- report
    n_pass = sum(1 for r in out_rows if r["gate"]["passed"])
    print(f"\nitems={len(out_rows)} passed={n_pass} failed={len(out_rows)-n_pass} (rule: >= {args.min_pass} of {len(specs)} correct when warned)")
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
            print(f"- {r['id']} [{r['type']}] expected {r['answer']!r}")
            for m, a in r["gate"]["models"].items():
                print(f"    {m.split(':',1)[1][:28]:28s} {a.get('label','?'):9s} {a.get('final','')[:90]!r}")
    unmatched = [(r["id"], m, a["final"]) for r in out_rows if r["gate"]["passed"] for m, a in r["gate"]["models"].items() if a.get("label") == "unmatched"]
    if unmatched:
        print(f"\nunmatched answers on PASSED items ({len(unmatched)}), candidates for aliases:")
        for iid, m, fin in unmatched[:60]:
            print(f"    {iid:22s} {m.split(':',1)[1][:24]:24s} {fin[:80]!r}")
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
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cache", default="data/probe/gate_cache.jsonl")
    ap.add_argument("--out", default="data/gated.jsonl")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
