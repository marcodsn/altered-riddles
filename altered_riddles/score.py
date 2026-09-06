"""altered_riddles.score — score one run directory (PLAN.md, D5).

Deterministic first: the final answer line is matched against the item's
`answer` + `aliases` (-> correct) and against the source's original answer
+ aliases (-> original). Only replies that match neither, or both, go to
the judge, a named thinking-off model with a four-way verdict:

  correct | original | other | abstain

`abstain` is the reply that refuses, says the riddle is a trick, or gives
no committed answer: not an override, not a solve. Judge verdicts are
cached next to the run. Without --judge, unmatched rows stay `pending`.

For the `original` condition the output is the model's familiarity per
source (fraction of samples giving the original answer); COR for this
model is computed over items whose source it is familiar with (>= 0.8).

Usage:
    .venv/bin/python -m altered_riddles.score --run runs/jalapeno_DeepSeek-V4-Flash-0731/unwarned-thinkon-k5 \\
        --items data/gated.jsonl --judge jalapeno:DeepSeek-V4-Flash-0731
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from altered_riddles.llm import Client, gather_limited
from altered_riddles.match import extract_final_answer, label as det_label, matches
from altered_riddles.probe import parse_model_spec

FAMILIAR_THRESHOLD = 0.8
JUDGE_LABELS = ("correct", "original", "other", "abstain")
JUDGE_PROMPT = """You are grading a model's answer to a riddle or puzzle. Decide what the ANSWER expresses.

RIDDLE: {text}
ACCEPTED answers (correct): {accepted}
ORIGINAL answers (the well-known answer to the unmodified riddle; wrong here): {original}
ANSWER to grade: {answer}

Reply with exactly one word:
correct  - the ANSWER means the same as one of the ACCEPTED answers
original - the ANSWER means the same as one of the ORIGINAL answers
abstain  - the ANSWER refuses, says the riddle is a trick or modified, asks a question back, or gives no committed answer
other    - anything else, including a different wrong answer or several answers at once"""


def load_items(path: Path) -> dict[str, dict[str, Any]]:
    return {i["id"]: i for i in (json.loads(l) for l in path.read_text().splitlines() if l.strip())}


def latest_rows(raw_path: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for line in raw_path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            key = (r["unit_id"], r["sample"])
            if key not in latest or not r["reply"].get("error"):
                latest[key] = r
    return list(latest.values())


def score_original(run_dir: Path, items: dict[str, dict[str, Any]], items_path: Path) -> None:
    by_source: dict[str, dict[str, Any]] = {}
    for it in items.values():
        by_source.setdefault(it["source"], {"answers": [it["original_answer"], *it.get("original_aliases", [])]})
    hits: dict[str, list[int]] = defaultdict(list)
    for r in latest_rows(run_dir / "raw.jsonl"):
        rep = r["reply"]
        if rep.get("error"):
            continue
        src = r["unit_id"]
        if src not in by_source:
            continue
        hits[src].append(int(matches(answer_text(rep), by_source[src]["answers"])))
    familiar = {s: round(sum(v) / len(v), 3) for s, v in hits.items() if v}
    out = {"familiar": familiar, "n_sources": len(familiar),
           "familiar_sources": sum(1 for v in familiar.values() if v >= FAMILIAR_THRESHOLD),
           "threshold": FAMILIAR_THRESHOLD,
           "scoring": {**scoring_provenance(items_path, None), "familiarity_fingerprint": familiarity_fingerprint(items),
                       "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}
    (run_dir / "scored.json").write_text(json.dumps(out, indent=1))
    print(f"familiar with {out['familiar_sources']}/{out['n_sources']} sources (>= {FAMILIAR_THRESHOLD})")


async def judge_rows(rows: list[dict[str, Any]], items: dict[str, dict[str, Any]], spec: str, cache_path: Path, concurrency: int) -> dict[str, str]:
    provider, model = parse_model_spec(spec, "jalapeno")
    client = Client(provider, concurrency=concurrency, retries=8)
    cache: dict[str, dict[str, Any]] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            if line.strip():
                c = json.loads(line)
                cache[c["key"]] = c
    fh = cache_path.open("a")
    def judge_prompt(r: dict[str, Any]) -> str:
        it = items[r["unit_id"]]
        return JUDGE_PROMPT.format(
            text=it["text"], accepted=json.dumps([it["answer"], *it.get("aliases", [])]),
            original=json.dumps([it["original_answer"], *it.get("original_aliases", [])]), answer=r["final"],
        )

    def cache_key(r: dict[str, Any]) -> str:  # a rephrased item or alias edit invalidates the cached verdict
        return f"{r['unit_id']}|{r['sample']}|{hashlib.sha256(judge_prompt(r).encode()).hexdigest()[:16]}"

    todo = [r for r in rows if cache_key(r) not in cache]
    print(f"judge {provider}:{model}: {len(rows)} rows, {len(todo)} to call", file=sys.stderr)

    async def one(r):
        prompt = judge_prompt(r)
        reply = await client.chat(model, [{"role": "user", "content": prompt}], max_tokens=8, thinking=False, temperature=0.0)
        word = (reply.text or "").strip().lower().strip(".").split()
        verdict = word[0] if word and word[0] in JUDGE_LABELS else ("error" if reply.error else "other")
        row = {"key": cache_key(r), "verdict": verdict, "raw": reply.text, "error": reply.error, "judge": f"{provider}:{model}"}
        cache[row["key"]] = row
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()

    if todo:
        await gather_limited([one(r) for r in todo], progress_every=100, label="judge ")
    fh.close()
    return {f"{r['unit_id']}|{r['sample']}": cache[cache_key(r)]["verdict"] for r in rows if cache_key(r) in cache}


ITEM_FIELDS = ("text", "answer", "aliases", "original_answer", "original_aliases")  # everything a label depends on


def _sha16(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def item_fingerprints(items: dict[str, dict[str, Any]], unit_ids) -> dict[str, str]:
    """Per-item hash of the fields a label depends on; the board compares these with the
    current item file so a text or alias edit invalidates old scores."""
    return {u: _sha16({k: items[u].get(k) for k in ITEM_FIELDS}) for u in sorted(unit_ids) if u in items}


def familiarity_fingerprint(items: dict[str, dict[str, Any]]) -> str:
    """Hash of the per-source original answer + aliases the familiarity score matched against."""
    by_source: dict[str, list[str]] = {}
    for it in items.values():
        by_source.setdefault(it["source"], [it["original_answer"], *it.get("original_aliases", [])])
    return _sha16(by_source)


def scoring_provenance(items_path: Path, judge_spec: str | None) -> dict[str, Any]:
    import altered_riddles.match as m
    return {
        "items_file": str(items_path), "items_sha256": hashlib.sha256(items_path.read_bytes()).hexdigest(),
        "matcher_version": m.MATCHER_VERSION,
        "matcher_sha256": hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()[:16],
        "score_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16],
        "judge": judge_spec, "judge_prompt_sha256": hashlib.sha256(JUDGE_PROMPT.encode()).hexdigest()[:16] if judge_spec else None,
    }


REASONING_TAIL = 300  # chars: an "Answer:" line this close to the end of the thinking is the committed answer


def answer_text(rep: dict[str, Any]) -> str:
    """The text to score. DeepSeek sometimes writes its final "Answer: ..." line
    inside the thinking block and sends nothing on the content channel (about
    1–2% of thinking-on replies; the completion count exceeds the reasoning count
    by one token). When the content is empty and the reasoning ends with an
    "Answer:" line, that line is the answer. Deliberation earlier in the
    reasoning is never used."""
    text = (rep.get("text") or "").strip()
    if text:
        return text
    tail = (rep.get("reasoning") or "")[-REASONING_TAIL:]
    if "answer:" in tail.lower():
        return extract_final_answer(tail)
    return ""


def score_altered(run_dir: Path, items: dict[str, dict[str, Any]], judge_spec: str | None, concurrency: int, items_path: Path) -> None:
    rows = latest_rows(run_dir / "raw.jsonl")
    scored = []
    for r in rows:
        rep = r["reply"]
        it = items.get(r["unit_id"])
        if it is None:
            continue
        if rep.get("error"):
            scored.append({"unit_id": r["unit_id"], "sample": r["sample"], "final": "", "det": "error", "label": "error",
                           "text_sha": r.get("text_sha")})
            continue
        final = extract_final_answer(answer_text(rep))
        det = det_label(final, correct=[it["answer"], *it.get("aliases", [])], original=[it["original_answer"], *it.get("original_aliases", [])])
        scored.append({"unit_id": r["unit_id"], "sample": r["sample"], "final": final, "det": det,
                       "label": det if det in ("correct", "original") else "pending",
                       "reasoning_tokens": rep.get("reasoning_tokens"), "finish_reason": rep.get("finish_reason"),
                       "text_sha": r.get("text_sha")})  # ties the scored row to the raw sample it came from
    pending = [s for s in scored if s["label"] == "pending"]
    judge_name = None
    if judge_spec and pending:
        verdicts = asyncio.run(judge_rows(pending, items, judge_spec, run_dir / "judge_cache.jsonl", concurrency))
        judge_name = judge_spec
        for s in pending:
            v = verdicts.get(f"{s['unit_id']}|{s['sample']}", "pending")
            s["label"] = v if v in JUDGE_LABELS else "pending"
            s["judge"] = v
    with (run_dir / "scored.jsonl").open("w") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------ metrics
    familiar: dict[str, float] = {}
    fam_candidates = sorted(run_dir.parent.glob("original-think*-k*/scored.json"),
                            key=lambda p: ("thinkoff" in p.parent.name, int(p.parent.name.rsplit("k", 1)[1])))
    if fam_candidates:
        familiar = json.load(fam_candidates[-1].open())["familiar"]
    counts = Counter(s["label"] for s in scored)
    n = sum(v for k, v in counts.items() if k != "error")
    cond = [s for s in scored if s["label"] != "error" and familiar.get(items[s["unit_id"]]["source"], 0) >= FAMILIAR_THRESHOLD]
    cond_counts = Counter(s["label"] for s in cond)
    by_type: dict[str, Counter] = defaultdict(Counter)
    by_family: dict[str, Counter] = defaultdict(Counter)
    for s in scored:
        it = items[s["unit_id"]]
        by_type[it["type"]][s["label"]] += 1
        by_family[it.get("family", "?")][s["label"]] += 1

    def rates(c: Counter) -> dict[str, Any]:
        tot = sum(v for k, v in c.items() if k != "error")
        return {"n": tot, **{k: round(c[k] / tot, 4) if tot else None for k in ("correct", "original", "other", "abstain", "pending")}}

    summary = {
        "deterministic_resolved": round(sum(1 for s in scored if s["det"] in ("correct", "original")) / max(1, len(scored)), 4),
        "judge": judge_name, "judged_rows": len(pending) if judge_name else 0,
        "overall": rates(counts),
        "conditioned_on_familiar": {**rates(cond_counts), "familiar_sources_known": bool(familiar),
                                    "cor": round(cond_counts["original"] / sum(v for k, v in cond_counts.items() if k != "error"), 4) if cond else None},
        "by_type": {t: rates(c) for t, c in by_type.items()},
        "by_family": {f: rates(c) for f, c in by_family.items()},
        "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "scoring": {**scoring_provenance(items_path, judge_spec),
                    "item_fingerprints": item_fingerprints(items, {s["unit_id"] for s in scored})},
    }
    (run_dir / "scored_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="run directory (contains config.json and raw.jsonl)")
    ap.add_argument("--items", default="data/gated.jsonl")
    ap.add_argument("--judge", default=None, help="provider:model for unmatched rows; omit to leave them pending")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()
    run_dir = Path(args.run)
    config = json.load((run_dir / "config.json").open())
    items = load_items(Path(args.items))
    if config["condition"] == "original":
        score_original(run_dir, items, Path(args.items))
    else:
        score_altered(run_dir, items, args.judge, args.concurrency, Path(args.items))


if __name__ == "__main__":
    main()
