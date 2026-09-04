"""altered_riddles.probe — the recall probe (PLAN.md, D2).

Two cheap probes on every candidate source, thinking off:

  A  familiarity   "answer in a few words", max_tokens=16, k samples.
                   Pass at >= 4/5 canonical (answer or alias).
  B  verbatim      given the first ~60% of the text, continue it word for
                   word. Pass at normalized similarity >= 0.8 with the true
                   remainder. Reasoning cannot produce this, so it is the
                   memorization evidence.

A source is ADMITTED if A passes on >= --min-models models and B passes on
>= 1 model. Per-model A rates are kept: COR later conditions on each
model's own familiarity with the source.

Every call is cached in --cache keyed by (probe, source, model, sample), so
re-running after provider errors only fills the gaps. Calls whose reply
reports reasoning tokens > 0 are "leaks" (thinking was not off); they are
excluded and counted per model.

Usage:
    .venv/bin/python -m altered_riddles.probe \\
        --models jalapeno:DeepSeek-V4-Flash-0731 jalapeno:Qwen3-Next-80B-A3B-Instruct \\
                 jalapeno:Qwen3.5-35B-A3B jalapeno:GLM-5.3 nous:poolside/laguna-s-2.1:free \\
        --sources data/sources.yaml --crawsome data/riddles_source.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import difflib
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from altered_riddles.llm import PROVIDERS, Client, Reply, gather_limited

A_PROMPT = "Solve this riddle. Reply with only the answer, in a few words, and nothing else.\n\n{text}"
B_PROMPT = (
    "Below is the beginning of a well-known riddle. Write the rest of it exactly as it is "
    "usually worded, word for word, and nothing else. Do not answer it.\n\n{prefix}"
)
A_MAX_TOKENS = 16
B_MAX_TOKENS = 80
A_THRESHOLD = 0.8
B_THRESHOLD = 0.8
PREFIX_FRACTION = 0.6

# ----------------------------------------------------------------- text utils

_PUNCT = re.compile(r"[^\w\s$.]", re.UNICODE)
_SPACES = re.compile(r"\s+")
_DOT = re.compile(r"(?<!\d)\.|\.(?!\d)")


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("'s ", " ").replace("'", "")
    s = _PUNCT.sub(" ", s)
    s = _DOT.sub(" ", s)  # drop periods except decimal points (1.05)
    s = _SPACES.sub(" ", s).strip()
    for art in ("a ", "an ", "the "):
        if s.startswith(art):
            s = s[len(art):]
    return s


def norm_words(s: str) -> list[str]:
    return norm(s).split()


def answer_matches(reply: str, answers: list[str]) -> bool:
    r = norm(reply)
    if not r:
        return False
    r_tokens = set(r.split())
    for a in answers:
        n = norm(a)
        if not n:
            continue
        toks = n.split()
        if len(toks) == 1:
            if re.search(rf"\b{re.escape(n)}\b", r):
                return True
        else:
            if n in r or set(toks) <= r_tokens:
                return True
    return False


def split_prefix(text: str) -> tuple[str, str]:
    words = text.split()
    n = max(3, round(PREFIX_FRACTION * len(words)))
    n = min(n, len(words) - 1)
    return " ".join(words[:n]), " ".join(words[n:])


_NUM_WORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
              "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
              "thirteen": "13", "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
              "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
              "fifty": "50", "hundred": "100", "thousand": "1000"}
# Formulaic question tails carry no memorization signal and are often omitted.
_TAILS = (["what", "am", "i"], ["what", "is", "it"], ["what", "is", "this"], ["who", "am", "i"],
          ["what", "are", "we"], ["what", "are", "they"], ["what", "is", "he"], ["who", "is", "he"])


def _words_num(s: str) -> list[str]:
    return [_NUM_WORDS.get(w, w) for w in norm_words(s)]


def _strip_tail(words: list[str]) -> list[str]:
    for t in _TAILS:
        if len(words) > len(t) and words[-len(t):] == t:
            return words[: -len(t)]
    return words


def verbatim_score(text: str, prefix: str, continuation: str) -> float:
    """Similarity between the true remainder and the model's continuation.

    Number words are mapped to digits, a formulaic "What am I?" tail is
    ignored, a restated prefix is dropped, and the prediction is cut to the
    remainder's length plus one so an appended answer does not count against
    a verbatim recitation. (Scorer fix 2026-09-04 after inspecting failures;
    thresholds unchanged.)
    """
    true_rem = _strip_tail(_words_num(text[len(prefix):]))
    pred = _words_num(continuation)
    if not true_rem or not pred:
        return 0.0
    prefix_w = _words_num(prefix)
    pred_rem = pred[len(prefix_w):] if pred[: len(prefix_w)] == prefix_w else pred
    full = _strip_tail(_words_num(text))
    r1 = difflib.SequenceMatcher(None, true_rem, pred_rem[: len(true_rem) + 1]).ratio()
    r2 = difflib.SequenceMatcher(None, full, pred[: len(full) + 1]).ratio()
    return max(r1, r2)


# ----------------------------------------------------------------- sources


def load_sources(path: Path) -> list[dict[str, Any]]:
    entries = yaml.safe_load(path.read_text())
    out = []
    for e in entries:
        out.append(
            {
                "id": e["id"],
                "family": e.get("family", "riddle"),
                "text": e["text"].strip(),
                "answer": str(e["answer"]).strip(),
                "aliases": [str(a) for a in (e.get("aliases") or [])],
                "note": e.get("note"),
            }
        )
    ids = [e["id"] for e in out]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SystemExit(f"duplicate source ids: {sorted(dupes)}")
    return out


def load_crawsome(path: Path) -> list[dict[str, Any]]:
    out = []
    with path.open(newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            text = (row.get("riddles") or "").strip()
            ans = (row.get("answers") or "").strip()
            if not text or not ans:
                continue
            out.append({"id": f"craw-{i:04d}", "family": "crawsome", "text": text, "answer": ans, "aliases": [], "note": None})
    return out


# ----------------------------------------------------------------- cache


class Cache:
    def __init__(self, path: Path):
        self.path = path
        self.rows: dict[str, dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["key"]] = row
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a")

    def get_ok(self, key: str) -> dict[str, Any] | None:
        row = self.rows.get(key)
        if row and not row["reply"].get("error"):
            return row
        return None

    def put(self, key: str, **fields: Any) -> None:
        row = {"key": key, **fields}
        self.rows[key] = row
        self._fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._fh.flush()


# ----------------------------------------------------------------- run


def parse_model_spec(spec: str, default_provider: str) -> tuple[str, str]:
    head, sep, rest = spec.partition(":")
    if sep and head in PROVIDERS:
        return head, rest
    return default_provider, spec


async def run(args: argparse.Namespace) -> None:
    sources = load_sources(Path(args.sources))
    if args.crawsome:
        sources += load_crawsome(Path(args.crawsome))
    if args.limit:
        sources = sources[: args.limit]
    specs = [parse_model_spec(m, args.provider) for m in args.models]
    clients = {p: Client(p, concurrency=args.concurrency, retries=8, rpm=args.rpm) for p in {p for p, _ in specs}}
    if args.min_models is None:
        # Pre-registered rule: familiar on at least three quarters of the probe models.
        args.min_models = max(3, -(-3 * len(specs) // 4))
    cache = Cache(Path(args.cache))

    jobs: list[tuple[str, dict[str, Any], str, str, int]] = []  # (probe, source, provider, model, sample)
    for src in sources:
        for prov, model in specs:
            for i in range(args.samples):
                jobs.append(("A", src, prov, model, i))
            jobs.append(("B", src, prov, model, 0))

    def key_of(probe: str, src: dict, prov: str, model: str, i: int) -> str:
        return f"{probe}|{src['id']}|{prov}:{model}|{i}"

    todo = [j for j in jobs if cache.get_ok(key_of(*j[:1], j[1], *j[2:])) is None]
    print(f"sources={len(sources)} models={len(specs)} calls={len(jobs)} cached_ok={len(jobs)-len(todo)} todo={len(todo)}", file=sys.stderr)

    async def one(job):
        probe, src, prov, model, i = job
        client = clients[prov]
        if probe == "A":
            msg = A_PROMPT.format(text=src["text"])
            reply = await client.chat(model, [{"role": "user", "content": msg}], max_tokens=A_MAX_TOKENS, thinking=False)
        else:
            prefix, _ = split_prefix(src["text"])
            msg = B_PROMPT.format(prefix=prefix)
            reply = await client.chat(model, [{"role": "user", "content": msg}], max_tokens=B_MAX_TOKENS, thinking=False, temperature=0.0)
        cache.put(key_of(probe, src, prov, model, i), probe=probe, source=src["id"], model=f"{prov}:{model}", sample=i, reply=reply.as_dict())
        return reply

    t0 = time.monotonic()
    if todo:
        await gather_limited([one(j) for j in todo], progress_every=200, label="calls ")
    print(f"done in {time.monotonic()-t0:.0f}s", file=sys.stderr)

    # ------------------------------------------------------------- score
    model_names = [f"{p}:{m}" for p, m in specs]
    per_source: dict[str, dict[str, Any]] = {}
    model_stats: dict[str, dict[str, float]] = {m: defaultdict(float) for m in model_names}
    for src in sources:
        answers = [src["answer"], *src["aliases"]]
        per_model: dict[str, Any] = {}
        for prov, model in specs:
            mname = f"{prov}:{model}"
            hits = valid = leaks = errors = 0
            for i in range(args.samples):
                row = cache.get_ok(key_of("A", src, prov, model, i))
                if row is None:
                    errors += 1
                    continue
                rep = row["reply"]
                if (rep.get("reasoning_tokens") or 0) > 0:
                    leaks += 1
                    continue
                valid += 1
                if answer_matches(rep.get("text", ""), answers):
                    hits += 1
            familiar = hits / valid if valid else None
            brow = cache.get_ok(key_of("B", src, prov, model, 0))
            if brow is None:
                errors += 1
                vscore, vpass, vleak = None, False, False
            else:
                brep = brow["reply"]
                vleak = (brep.get("reasoning_tokens") or 0) > 0
                prefix, _ = split_prefix(src["text"])
                vscore = round(verbatim_score(src["text"], prefix, brep.get("text", "")), 3)
                vpass = (vscore >= B_THRESHOLD) and not vleak
            per_model[mname] = {
                "familiar": None if familiar is None else round(familiar, 2),
                "n": valid, "leaks": leaks, "errors": errors,
                "verbatim": vscore, "verbatim_pass": vpass,
            }
            st = model_stats[mname]
            st["sources"] += 1
            st["leaks"] += leaks + (1 if (brow is not None and vleak) else 0)
            st["errors"] += errors
            if familiar is not None:
                st["familiar_sum"] += familiar
                st["familiar_n"] += 1
                st["a_pass"] += 1 if familiar >= A_THRESHOLD else 0
            st["b_pass"] += 1 if vpass else 0
        a_pass = sum(1 for v in per_model.values() if v["familiar"] is not None and v["familiar"] >= A_THRESHOLD)
        b_pass = sum(1 for v in per_model.values() if v["verbatim_pass"])
        per_source[src["id"]] = {
            "family": src["family"], "text": src["text"], "answer": src["answer"],
            "per_model": per_model, "a_pass_models": a_pass, "b_pass_models": b_pass,
            "admitted": a_pass >= args.min_models and b_pass >= 1,
        }

    by_family: dict[str, dict[str, int]] = defaultdict(lambda: {"candidates": 0, "admitted": 0, "a_only": 0})
    for s in per_source.values():
        f = by_family[s["family"]]
        f["candidates"] += 1
        f["admitted"] += int(s["admitted"])
        f["a_only"] += int(s["a_pass_models"] >= args.min_models and s["b_pass_models"] == 0)
    per_model_summary = {}
    for m, st in model_stats.items():
        n = st["sources"] or 1
        per_model_summary[m] = {
            "mean_familiar": round(st["familiar_sum"] / st["familiar_n"], 3) if st["familiar_n"] else None,
            "a_pass_rate": round(st["a_pass"] / n, 3),
            "b_pass_rate": round(st["b_pass"] / n, 3),
            "leak_calls": int(st["leaks"]), "error_calls": int(st["errors"]),
        }
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "params": {"samples": args.samples, "min_models": args.min_models, "a_threshold": A_THRESHOLD,
                   "b_threshold": B_THRESHOLD, "prefix_fraction": PREFIX_FRACTION, "models": model_names,
                   "a_max_tokens": A_MAX_TOKENS, "b_max_tokens": B_MAX_TOKENS},
        "summary": {"by_family": dict(by_family), "per_model": per_model_summary},
        "sources": per_source,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))

    # ------------------------------------------------------------- report
    print("\nby family:")
    for fam, c in by_family.items():
        print(f"  {fam:9s} candidates={c['candidates']:4d} admitted={c['admitted']:4d} familiar-but-no-verbatim={c['a_only']}")
    print("\nper model:")
    for m, s in per_model_summary.items():
        print(f"  {m:45s} familiar={s['mean_familiar']} A-pass={s['a_pass_rate']} B-pass={s['b_pass_rate']} leaks={s['leak_calls']} errors={s['error_calls']}")
    rejected = [(sid, s) for sid, s in per_source.items() if s["family"] != "crawsome" and not s["admitted"]]
    if rejected:
        print(f"\nhand-curated sources NOT admitted ({len(rejected)}):")
        for sid, s in rejected:
            fam = " ".join(f"{v['familiar']}" for v in s["per_model"].values())
            vb = " ".join(f"{v['verbatim']}" for v in s["per_model"].values())
            print(f"  {sid:24s} A=[{fam}] B=[{vb}]")
    print(f"\nwrote {args.out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="jalapeno", help="default provider for --models without a prefix")
    ap.add_argument("--models", nargs="+", required=True, help="model specs, optionally 'provider:model'")
    ap.add_argument("--sources", default="data/sources.yaml")
    ap.add_argument("--crawsome", default=None, help="also probe this crawsome-style CSV (riddles,answers)")
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--min-models", type=int, default=None, help="default: ceil(3/4 of the probe models), at least 3")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--rpm", type=int, default=None, help="cap requests per minute per provider")
    ap.add_argument("--limit", type=int, default=0, help="only the first N sources (smoke test)")
    ap.add_argument("--cache", default="data/probe/cache.jsonl")
    ap.add_argument("--out", default="data/recall_probe.json")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
