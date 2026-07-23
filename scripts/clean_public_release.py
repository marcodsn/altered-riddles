#!/usr/bin/env python3
"""clean_public_release.py — close the fixed->public ANSWER-leak (B3, corrected).

Marco/Fable review: the altered TEST ITEMS never overlap fixed<->auxiliary
(0 shared altered texts, 0 shared (riddle,answer) pairs). The only real leak is
answer transfer: auxiliary rows built from the SAME famous original that land on
an answer-EQUIVALENT altered answer expose the private fixed item's answer.

This drops exactly those auxiliary rows (reproducible criterion: same original
riddle text AND intersecting normalized answer sets). It NEVER touches the
private fixed set. Result: ~700 -> ~662 public rows (~5.4%), 0 residual answer
leaks. Also regenerates the 12-column public HF copy.

Usage:
    python -m scripts.clean_public_release            # dry-run report
    python -m scripts.clean_public_release --apply    # rewrite benchmark.jsonl + hf copy
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from scripts.core.config import DEFAULT_BENCHMARK, DEFAULT_BENCHMARK_FIXED

HF_KEEP = {"id", "original_riddle", "original_answer", "original_accepted_answers",
           "original_reasoning", "altered_riddle", "altered_answer",
           "altered_accepted_answers", "altered_competing_answers",
           "altered_reasoning", "type", "source"}


def _norm(s: str) -> str:
    return " ".join((s or "").lower().replace('"', "").split()).strip(".!?")


def _answers(r: dict) -> set[str]:
    xs = {_norm(r.get("altered_answer", ""))}
    xs |= {_norm(a) for a in (r.get("altered_accepted_answers") or [])}
    return {a for a in xs if a}


def _load(path: str) -> list[dict]:
    return [json.loads(l) for l in open(path) if l.strip()]


def leak_rows(fixed: list[dict], aux: list[dict]) -> tuple[list[str], set[str]]:
    """Aux ids that expose a fixed answer; and the set of exposed fixed ids."""
    fixed_by_orig: dict[str, list[dict]] = defaultdict(list)
    for r in fixed:
        fixed_by_orig[_norm(r["original_riddle"])].append(r)
    drop, exposed = [], set()
    for r in aux:
        aset = _answers(r)
        for fr in fixed_by_orig.get(_norm(r["original_riddle"]), []):
            if aset & _answers(fr):
                drop.append(r["id"])
                exposed.add(fr["id"])
                break
    return sorted(set(drop)), exposed


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--benchmark", default=DEFAULT_BENCHMARK)
    ap.add_argument("--hf-out", default="hf/benchmark.jsonl")
    args = ap.parse_args()

    fixed = _load(DEFAULT_BENCHMARK_FIXED)
    fixed_sha = hashlib.sha256(Path(DEFAULT_BENCHMARK_FIXED).read_bytes()).hexdigest()
    aux = _load(args.benchmark)
    drop, exposed = leak_rows(fixed, aux)
    print(f"auxiliary rows: {len(aux)}  fixed rows: {len(fixed)}")
    print(f"answer-leak aux rows to drop: {len(drop)}  (exposing {len(exposed)} fixed answers)")
    print("drop ids:", ",".join(drop))

    kept = [r for r in aux if r["id"] not in set(drop)]
    # residual-leak check on the kept set
    resid, _ = leak_rows(fixed, kept)
    assert not resid, f"residual leaks remain: {resid}"
    print(f"kept auxiliary rows: {len(kept)}  residual answer-leaks: {len(resid)}")

    if not args.apply:
        print("\n(dry run — pass --apply to rewrite benchmark.jsonl + the HF copy)")
        return

    # write cleaned auxiliary (git-tracked -> reversible)
    with open(args.benchmark, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # preserve the dropped rows PRIVATELY (gitignored): the leaderboard needs
    # their original-riddle TEXT to cluster-map the eval details (which were
    # scored on all 1000 aux ids), but they must NOT be published.
    dropped_rows = [r for r in aux if r["id"] in set(drop)]
    with open(Path(args.benchmark).with_name("benchmark_dropped.jsonl"), "w", encoding="utf-8") as f:
        for r in dropped_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # regenerate 12-column public HF copy
    Path(args.hf_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.hf_out, "w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps({k: v for k, v in r.items() if k in HF_KEEP}, ensure_ascii=False) + "\n")
    # the private fixed set must be byte-identical
    assert hashlib.sha256(Path(DEFAULT_BENCHMARK_FIXED).read_bytes()).hexdigest() == fixed_sha, \
        "fixed set changed — aborting"
    # write a screening report
    report = {"aux_before": len(aux), "aux_after": len(kept), "dropped": drop,
              "exposed_fixed_items": sorted(exposed), "residual_leaks": resid,
              "criterion": "same original_riddle text AND intersecting normalized answer sets"}
    Path("results/public_release_screening.json").write_text(json.dumps(report, indent=2))
    print(f"applied: benchmark.jsonl {len(aux)}->{len(kept)}, hf copy regenerated, "
          f"fixed set unchanged, report -> results/public_release_screening.json")


if __name__ == "__main__":
    main()
