"""Offline, reproducible diagnostic slices and a human validity-review queue.

Usage: python -m altered_riddles.audit --out-dir results/audit
Existing benchmark items, scores and leaderboards are never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

from altered_riddles.board import build, cluster_bootstrap, collect_runs, load_jsonl, mean
from altered_riddles.statistics import pairwise_comparisons


def analyze(items, records, selected, *, n_boot=2000, seed=0):
    rows, rates = [], {}
    common_sources = {items[u]["source"] for u in selected}
    for _, _, fam in records:
        common_sources &= {s for s, p in fam.items() if p >= .8}
    for row, scored, fam in records:
        ss = [s for s in scored if s["unit_id"] in selected]
        cond = [s for s in ss if fam.get(items[s["unit_id"]]["source"], 0) >= .8]
        grouped, by_item = defaultdict(list), defaultdict(list)
        for s in cond:
            uid = s["unit_id"]
            grouped[items[uid].get("cluster", items[uid]["source"])].append(int(s["label"] == "original"))
            by_item[uid].append(int(s["label"] == "original"))
        boots = sorted(cluster_bootstrap(grouped, mean, n_boot, random.Random(seed))) if grouped else []
        shared = [s for s in ss if items[s["unit_id"]]["source"] in common_sources]
        rates[row["id"]] = {u: mean(v) for u, v in by_item.items()}
        rows.append({"id": row["id"], "model": row["model"], "thinking": row["thinking"],
                     "n_items": len({s["unit_id"] for s in ss}), "n_conditioned": len(cond),
                     "cor": mean([s["label"] == "original" for s in cond]),
                     "ci95": [boots[int(.025*n_boot)], boots[max(0, int(.975*n_boot)-1)]] if boots else [None, None],
                     "alt_acc": mean([s["label"] == "correct" for s in ss]),
                     "shared_familiar_cor": mean([s["label"] == "original" for s in shared]),
                     "shared_familiar_n": len(shared)})
    rows.sort(key=lambda r: (r["cor"] is None, r["cor"] or 0, r["id"]))
    return {"item_ids": sorted(selected), "n_sources": len({items[u]["source"] for u in selected}),
            "n_shared_familiar_sources": len(common_sources), "rows": rows,
            "comparisons": pairwise_comparisons(rates, {u: it.get("cluster", it["source"]) for u, it in items.items()},
                                               n_boot=n_boot, seed=seed)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", default="data/gated.jsonl")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    if args.n_boot < 1:
        ap.error("--n-boot must be positive")
    out = Path(args.out_dir)
    # Refuse accidental replacement of historical outputs or a prior audit.
    if out.exists() and any(out.iterdir()):
        ap.error("output directory must be empty/new; preserve previous audit artifacts")
    items = {i["id"]: i for i in load_jsonl(Path(args.items)) if i.get("gate", {}).get("passed", True)}
    board = build(items, Path(args.runs_dir), args.n_boot, args.seed)
    runs = collect_runs(Path(args.runs_dir), items)
    records, inputs = [], {Path(args.items)}
    # Hash all run selection inputs, including excluded runs.
    for entry in runs.values():
        for run in entry["runs"].values():
            inputs.update(p for p in Path(run["dir"]).iterdir() if p.name in
                          {"config.json", "summary.json", "raw.jsonl", "scored.json", "scored.jsonl"})
    for row in board["rows"]:
        entry = runs[(row["model"], row["thinking"])]
        sp = Path(entry["runs"]["unwarned"]["dir"]) / "scored.jsonl"
        fp = Path(entry["runs"]["original"]["dir"]) / "scored.json"
        records.append((row, [s for s in load_jsonl(sp) if s["unit_id"] in items], json.loads(fp.read_text())["familiar"]))
    if not records:
        ap.error("no eligible completed runs; inspect board checks before making slices")
    failure = {s["unit_id"] for r, ss, _ in records if r["thinking"] == "on" for s in ss if s["label"] == "original"}
    minimal = {u for u, it in items.items() if Path(it.get("file", "")).name == "batch8.yaml"}
    slices = {name: analyze(items, records, ids, n_boot=args.n_boot, seed=args.seed)
              for name, ids in {"core": set(items), "minimal_insertion_development": minimal,
                                "observed_thinking_failures_posthoc": failure}.items()}
    queue = []
    for uid in sorted(items, key=lambda u: (u not in failure, u not in minimal, u)):
        it = items[uid]
        examples = [{"run": r["id"], "sample": s["sample"], "label": s["label"], "final": s["final"]}
                    for r, ss, _ in records for s in ss if s["unit_id"] == uid and s["label"] == "original"]
        queue.append({"id": uid, "source": it["source"], "priority": "thinking_failure" if uid in failure else "minimal_insertion" if uid in minimal else "routine",
                      "status": "unreviewed", "reviewers": [], "disposition": None,
                      "original_text": it["original_text"], "original_answer": it["original_answer"],
                      "text": it["text"], "answer": it["answer"], "why_original_fails": it.get("why_original_fails"),
                      "questions": ["Is the original answer necessarily invalid?", "Is the accepted answer entailed?",
                                    "Are there defensible alternative readings?", "Does the scored label match the actual response?"],
                      "override_examples": examples})
    manifest = {"seed": args.seed, "n_boot": args.n_boot,
                "inputs_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(inputs)},
                "code_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                [Path(__file__), Path(__file__).with_name("board.py"), Path(__file__).with_name("statistics.py")]},
                "excluded": board["excluded"], "api_calls": 0,
                "warning": "Development diagnostics, not a held-out Hard leaderboard. Failure selection uses these same models and unequal k. No human review is attested. Pairwise intervals are pointwise, not multiple-comparison-adjusted."}
    out.mkdir(parents=True, exist_ok=True)
    for name, value in [("manifest.json", manifest), ("slices.json", slices), ("leaderboard.json", board)]:
        (out / name).write_text(json.dumps(value, indent=2) + "\n")
    (out / "validity_queue.jsonl").write_text("".join(json.dumps(q, ensure_ascii=False) + "\n" for q in queue))
    lines = ["# Altered Riddles — development slice audit", "", manifest["warning"], "",
             "COR is response-weighted on each model's familiar sources; accuracy uses all selected items. Shared COR restricts to sources familiar to every included row. Pairwise JSON comparisons are item-balanced on pairwise-shared familiar items.", ""]
    for name, data in slices.items():
        lines += [f"## {name} ({len(data['item_ids'])} items)", "", "| Model | Thinking | COR ↓ | CI95 | Alt acc ↑ | Shared COR ↓ |", "|---|---|---:|---|---:|---:|"]
        def pct(x):
            return "—" if x is None else f"{100*x:.1f}%"
        for r in data["rows"]:
            lines.append(f"| {r['model']} | {r['thinking']} | {pct(r['cor'])} | {pct(r['ci95'][0])}–{pct(r['ci95'][1])} | {pct(r['alt_acc'])} | {pct(r['shared_familiar_cor'])} |")
        lines.append("")
    (out / "README.md").write_text("\n".join(lines) + "\n")
    print(f"Wrote {out}: {len(records)} rows, {len(queue)} unreviewed items; no API calls.")


if __name__ == "__main__":
    main()
