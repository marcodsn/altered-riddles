"""altered_riddles.board — the leaderboard (PLAN.md, D8).

Reads every scored run under runs/, keeps only runs whose guardrail passed,
and produces results/leaderboard.json + results/LEADERBOARD.md.

Per (model, thinking) row:
  alt_acc        unwarned accuracy over all items
  cor            Conditioned Override Rate: among unwarned answers on items
                 whose source the model is familiar with, the share that
                 gave the original answer. Primary metric, lower is better.
  ci95           clustered bootstrap on COR, clusters = source riddle
  override_gap   warned accuracy minus unwarned accuracy (same thinking)
  abstain        share of unwarned answers labelled abstain
  rank_group     models whose COR is not distinguishable by the pairwise
                 bootstrap share a group; the table shows groups, not ranks
  thinking_gap   COR(off) minus COR(on) for the same model, when both exist

Usage:
    .venv/bin/python -m altered_riddles.board --items data/gated.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

FAMILIAR_THRESHOLD = 0.8
REVIEW_MIN_ANSWERS = 5       # thinking-on answers needed before an item can be flagged
REVIEW_MIN_ON_OVERRIDE = 0.3  # flag when thinking-on override is this high AND above thinking-off
REVIEW_ALL_OVERRIDE = 0.7     # flag when BOTH modes override this often: strong prior or ambiguity, human look
CHECK_MAX_TRUNCATED = 0.05    # pre-publish: share of replies cut off by max_tokens
CHECK_MAX_DODGE = 0.10        # pre-publish: other + abstain share above which COR is flattered
CHECK_MIN_FAMILIAR = 0.80     # pre-publish: share of item sources the model is familiar with
BOOT = 2000


def load_jsonl(p: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def cluster_bootstrap(values_by_cluster: dict[str, list[int]], stat, n_boot: int, rng: random.Random) -> list[float]:
    clusters = list(values_by_cluster)
    out = []
    for _ in range(n_boot):
        sample = rng.choices(clusters, k=len(clusters))
        vals = [v for c in sample for v in values_by_cluster[c]]
        out.append(stat(vals))
    return out


def mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def collect_runs(runs_dir: Path, items: dict[str, dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for run_dir in sorted(runs_dir.glob("*/*")):
        cfg_p, sum_p = run_dir / "config.json", run_dir / "summary.json"
        if not cfg_p.exists() or not sum_p.exists():
            continue
        cfg, summ = json.load(cfg_p.open()), json.load(sum_p.open())
        key = (f"{cfg['provider']}:{cfg['model']}", cfg["thinking"])
        entry = rows.setdefault(key, {"model": cfg["model"], "provider": cfg["provider"], "thinking": key[1], "runs": {}})
        entry["runs"][cfg["condition"]] = {"dir": str(run_dir), "guardrail": summ.get("guardrail"),
                                           "reasons": summ.get("guardrail_reasons", []), "summary": summ, "config": cfg}
    # the original condition belongs to the model, not the thinking mode: share it across rows,
    # preferring a direct (thinking-off) familiarity run when both exist
    by_model: dict[str, dict[str, Any]] = {}

    def _rank(o: dict[str, Any]) -> tuple[int, int]:  # passing runs first, then direct over thinking
        return (int(o["guardrail"] == "PASS"), int(o["config"].get("familiarity_mode", "direct") == "direct"))

    for (m, th), e in rows.items():
        o = e["runs"].get("original")
        if o and (m not in by_model or _rank(o) > _rank(by_model[m])):
            by_model[m] = o
    for (m, th), e in rows.items():
        if m in by_model:
            e["runs"]["original"] = by_model[m]
    return rows


def drift(run_dir: str, items: dict[str, dict[str, Any]], expected: set[str]) -> dict[str, int]:
    """Item-set drift between a run and the current item file: `stale` = units whose text
    changed after they were answered (hash mismatch), `missing` = expected items with no
    reply, `unhashed` = rows from before text hashes were recorded (cannot be verified)."""
    latest: dict[str, str | None] = {}
    for r in load_jsonl(Path(run_dir) / "raw.jsonl"):
        latest[r["unit_id"]] = r.get("text_sha")
    cur = {u: hashlib.sha256(items[u]["text"].encode()).hexdigest()[:16] for u in expected if u in items}
    stale = sum(1 for u, h in latest.items() if h is not None and u in cur and h != cur[u])
    unhashed = sum(1 for h in latest.values() if h is None)
    missing = sum(1 for u in expected if u not in latest)
    return {"stale": stale, "missing": missing, "unhashed": unhashed}


def build(items: dict[str, dict[str, Any]], runs_dir: Path, n_boot: int, seed: int) -> dict[str, Any]:
    expected = {u for u, it in items.items() if it.get("gate", {}).get("passed", True)}
    rng = random.Random(seed)
    rows = collect_runs(runs_dir, items)
    board: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    boot_samples: dict[str, list[float]] = {}
    item_override: dict[tuple[str, str], list[int]] = defaultdict(list)  # (item, thinking) -> 0/1 per answer
    for (mkey, th), e in rows.items():
        unw = e["runs"].get("unwarned")
        orig = e["runs"].get("original")
        if not unw or not orig:
            excluded.append({"model": mkey, "thinking": th, "reason": "missing unwarned or original run"})
            continue
        bad = [c for c, r in e["runs"].items() if r["guardrail"] != "PASS"]
        if bad:
            excluded.append({"model": mkey, "thinking": th, "reason": f"guardrail failed: " + "; ".join(f"{c}: {', '.join(e['runs'][c]['reasons'])}" for c in bad)})
            continue
        scored_p = Path(unw["dir"]) / "scored.jsonl"
        fam_p = Path(orig["dir"]) / "scored.json"
        if not scored_p.exists() or not fam_p.exists():
            excluded.append({"model": mkey, "thinking": th, "reason": "not scored yet"})
            continue
        scored = [s for s in load_jsonl(scored_p) if s["label"] != "error"]
        familiar = json.load(fam_p.open())["familiar"]
        pending = sum(1 for s in scored if s["label"] == "pending")
        by_cluster_cor: dict[str, list[int]] = defaultdict(list)
        by_cluster_acc: dict[str, list[int]] = defaultdict(list)
        n_cond = 0
        for s in scored:
            it = items[s["unit_id"]]
            src = it["source"]
            cl = it.get("cluster", src)
            by_cluster_acc[cl].append(int(s["label"] == "correct"))
            if familiar.get(src, 0) >= FAMILIAR_THRESHOLD:
                by_cluster_cor[cl].append(int(s["label"] == "original"))
                n_cond += 1
            item_override[(s["unit_id"], th)].append(int(s["label"] == "original"))
        cor_vals = [v for vs in by_cluster_cor.values() for v in vs]
        cor = mean(cor_vals)
        boots = cluster_bootstrap(by_cluster_cor, lambda v: mean(v) or 0.0, n_boot, rng) if by_cluster_cor else []
        boots.sort()
        ci = (boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]) if boots else (None, None)
        row_id = f"{mkey}|{th}"
        boot_samples[row_id] = boots
        labels = defaultdict(int)
        for s in scored:
            labels[s["label"]] += 1
        n = len(scored)
        warned = e["runs"].get("warned")
        warned_acc = None
        if warned and (Path(warned["dir"]) / "scored.jsonl").exists():
            ws = [s for s in load_jsonl(Path(warned["dir"]) / "scored.jsonl") if s["label"] != "error"]
            warned_acc = mean([int(s["label"] == "correct") for s in ws])
        alt_acc = mean([int(s["label"] == "correct") for s in scored])
        # pre-publish checks (automatic part of the release checklist)
        checks: list[str] = []
        d = drift(unw["dir"], items, expected)
        if d["stale"]:
            checks.append(f"{d['stale']} items edited after this run (re-run to refresh)")
        if d["missing"]:
            checks.append(f"{d['missing']} passed items not answered")
        if d["unhashed"]:
            checks.append(f"{d['unhashed']} rows predate text hashes (item set unverifiable)")
        if warned:
            dw = drift(warned["dir"], items, expected)
            if dw["stale"] or dw["missing"]:
                checks.append(f"warned run: {dw['stale']} stale, {dw['missing']} missing")
        n_rows = unw["summary"].get("n_rows") or n
        trunc_rate = (unw["summary"].get("truncated") or 0) / n_rows if n_rows else 0.0
        if trunc_rate > CHECK_MAX_TRUNCATED:
            checks.append(f"{trunc_rate:.0%} of replies truncated by max_tokens")
        dodge = ((labels["other"] + labels["abstain"]) / n) if n else 0.0
        if dodge > CHECK_MAX_DODGE:
            checks.append(f"other+abstain {dodge:.0%}: COR flattered, rank by accuracy")
        item_sources = {items[u]["source"] for u in expected if u in items}
        fam_share = (sum(1 for src in item_sources if familiar.get(src, 0) >= FAMILIAR_THRESHOLD) / len(item_sources)) if item_sources else 0.0
        if fam_share < CHECK_MIN_FAMILIAR:
            checks.append(f"familiar with only {fam_share:.0%} of item sources")
        board.append({
            "checks": checks, "truncated_rate": round(trunc_rate, 4), "dodge_rate": round(dodge, 4), "familiar_share": round(fam_share, 3),
            "drift": d,
            "id": row_id, "model": mkey, "thinking": th, "n_items": len({s["unit_id"] for s in scored}),
            "n_answers": n, "familiar_sources": sum(1 for v in familiar.values() if v >= FAMILIAR_THRESHOLD),
            "n_conditioned": n_cond, "alt_acc": alt_acc, "cor": cor, "cor_ci95": ci,
            "original_rate": labels["original"] / n if n else None, "other_rate": labels["other"] / n if n else None,
            "abstain_rate": labels["abstain"] / n if n else None, "pending": pending,
            "warned_acc": warned_acc, "override_gap": (warned_acc - alt_acc) if (warned_acc is not None and alt_acc is not None) else None,
            "median_reasoning_tokens": unw["summary"].get("median_reasoning_tokens"),
            "familiarity_mode": orig["config"].get("familiarity_mode", "direct"),
            "samples": unw["config"]["samples"], "error_rate": unw["summary"].get("error_rate"),
            "run_dir": unw["dir"],
        })
    # validity flags: an item that thinking-ON models override MORE than thinking-off models
    # is one where reasoning finds a defensible alternative (pilot: the anchor/fishing-line item),
    # i.e. a candidate ambiguity the warned gate did not catch. Human look, not auto-drop.
    review: list[dict[str, Any]] = []
    for uid in {u for u, _ in item_override}:
        on, off = item_override.get((uid, "on")), item_override.get((uid, "off"))
        if on and off and len(on) >= REVIEW_MIN_ANSWERS:
            on_r, off_r = mean(on), mean(off)
            reason = None
            if on_r >= REVIEW_MIN_ON_OVERRIDE and on_r > off_r:
                reason = "thinking-on override above thinking-off: reasoning finds an alternative reading?"
            elif on_r >= REVIEW_ALL_OVERRIDE and off_r >= REVIEW_ALL_OVERRIDE and len(off) >= REVIEW_MIN_ANSWERS:
                reason = "overridden by everyone in both modes: very strong prior, or ambiguous"
            if reason:
                review.append({"item": uid, "override_on": round(on_r, 3), "override_off": round(off_r, 3),
                               "n_on": len(on), "n_off": len(off), "reason": reason})
    review.sort(key=lambda r: -r["override_on"])
    board.sort(key=lambda r: (r["cor"] is None, r["cor"] if r["cor"] is not None else 1.0))
    # rank groups: walk down; a row starts a new group only if its COR is significantly worse
    # than every row in the current group (pairwise bootstrap, one-sided 2.5%).
    groups: list[list[dict[str, Any]]] = []
    for r in board:
        if r["cor"] is None:
            continue
        placed = False
        if groups:
            cur = groups[-1]
            worse_than_all = all(_sig_worse(boot_samples[r["id"]], boot_samples[o["id"]]) for o in cur)
            if not worse_than_all:
                cur.append(r)
                placed = True
        if not placed:
            groups.append([r])
    for gi, g in enumerate(groups, start=1):
        for r in g:
            r["rank_group"] = gi
    # thinking gap
    by_model: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for r in board:
        by_model[r["model"]][r["thinking"]] = r
    for m, d in by_model.items():
        if "on" in d and "off" in d and d["on"]["cor"] is not None and d["off"]["cor"] is not None:
            gap = d["off"]["cor"] - d["on"]["cor"]
            d["on"]["thinking_gap"] = gap
            d["off"]["thinking_gap"] = gap
    return {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "n_boot": n_boot, "seed": seed,
            "familiar_threshold": FAMILIAR_THRESHOLD, "rows": board, "excluded": excluded, "review_flags": review}


def _sig_worse(a: list[float], b: list[float]) -> bool:
    """True if COR bootstrap `a` is higher than `b` in >= 97.5% of paired draws."""
    if not a or not b:
        return False
    n = min(len(a), len(b))
    # samples are sorted; re-pair randomly to avoid spurious correlation
    ra, rb = list(a[:n]), list(b[:n])
    random.Random(0).shuffle(ra)
    random.Random(1).shuffle(rb)
    return sum(1 for x, y in zip(ra, rb) if x > y) / n >= 0.975


def pct(x: float | None) -> str:
    return "—" if x is None else f"{100*x:.1f}%"


def render_md(b: dict[str, Any]) -> str:
    lines = ["# Altered Riddles v2 — leaderboard", "",
             f"_Generated {b['generated_at']}. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, {b['n_boot']} draws). Rows in the same **group** are not distinguishable at 95%. Rows are only listed when every run passed the guardrails and raw outputs are committed under `runs/`._", "",
             "| group | model | thinking | items | COR ↓ | CI95 | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | k | pending | familiarity | checks |",
             "|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for r in b["rows"]:
        ci = "—" if r["cor_ci95"][0] is None else f"[{100*r['cor_ci95'][0]:.1f}, {100*r['cor_ci95'][1]:.1f}]"
        lines.append(f"| {r.get('rank_group','—')} | {r['model']} | {r['thinking']} | {r['n_items']} | {pct(r['cor'])} | {ci} | {pct(r['alt_acc'])} | {pct(r['warned_acc'])} | {pct(r['override_gap'])} | {pct(r['abstain_rate'])} | {pct(r['other_rate'])} | {r['median_reasoning_tokens']} | {r['samples']} | {r['pending']} | {r.get('familiarity_mode', 'direct')} | {'ok' if not r.get('checks') else 'see below'} |")
    flagged = [r for r in b["rows"] if r.get("checks")]
    lines += ["", "## Pre-publish checks", ""]
    if not flagged:
        lines.append("_All rows pass: item set unchanged since the run, every passed item answered, truncation ≤ 5%, other + abstain ≤ 10%, familiar with ≥ 80% of item sources._")
    else:
        lines += [f"- **{r['model']} ({r['thinking']})**: " + "; ".join(r["checks"]) for r in flagged]
    gaps = [r for r in b["rows"] if r.get("thinking_gap") is not None and r["thinking"] == "on"]
    if gaps:
        lines += ["", "## Thinking gap (COR off minus COR on, same model)", "", "| model | COR off | COR on | gap |", "|---|---:|---:|---:|"]
        for r in gaps:
            off = next(x for x in b["rows"] if x["model"] == r["model"] and x["thinking"] == "off")
            lines.append(f"| {r['model']} | {pct(off['cor'])} | {pct(r['cor'])} | {pct(r['thinking_gap'])} |")
    if b["excluded"]:
        lines += ["", "## Not on the board", ""] + [f"- {e['model']} ({e['thinking']}): {e['reason']}" for e in b["excluded"]]
    if b.get("review_flags"):
        lines += ["", "## Items to review (validity flags)", "",
                  "_Human look before publishing; nothing is dropped automatically. Read the traces: a defensible alternative reading means re-pin or drop; a genuine override stays._", "",
                  "| item | override, thinking on | override, thinking off | n on / off | why flagged |", "|---|---:|---:|---:|---|"]
        for f in b["review_flags"]:
            lines.append(f"| {f['item']} | {pct(f['override_on'])} | {pct(f['override_off'])} | {f['n_on']} / {f['n_off']} | {f.get('reason', '')} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default="data/gated.jsonl")
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--n-boot", type=int, default=BOOT)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    items = {i["id"]: i for i in load_jsonl(Path(args.items))}
    b = build(items, Path(args.runs_dir), args.n_boot, args.seed)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leaderboard.json").write_text(json.dumps(b, indent=1))
    (out / "LEADERBOARD.md").write_text(render_md(b))
    print(render_md(b))


if __name__ == "__main__":
    main()
