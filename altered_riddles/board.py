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
  point_rank     descriptive COR ordering, not a significance claim
  rank_best/worst plausible rank range: 1 + rows significantly better ... n - rows
                 significantly worse, from the pairwise comparison intervals
  original_acc   accuracy on the original riddles (mean per-source accuracy of the
                 familiarity run over the item sources)
  mean_output_tokens  mean completion tokens per unwarned answer (verbosity/cost)
  alteration_types    per-type COR / altered accuracy per row (board level)
  comparisons    jointly clustered, shared-familiar-item comparisons
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

from altered_riddles.statistics import pairwise_comparisons

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


def collect_runs(runs_dir: Path, items: dict[str, dict[str, Any]], manifest: list[str] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """One run per (model, thinking, condition). `manifest` is an explicit list of run
    directories to use; without it every run directory is a candidate, and two candidates
    for the same slot are an error rather than a silent directory-order choice."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    candidates = [Path(d) for d in manifest] if manifest is not None else sorted(runs_dir.glob("*/*"))
    for run_dir in candidates:
        cfg_p, sum_p = run_dir / "config.json", run_dir / "summary.json"
        if not cfg_p.exists() or not sum_p.exists():
            if manifest is not None:
                raise SystemExit(f"manifest run {run_dir} has no config.json/summary.json")
            continue
        cfg, summ = json.loads(cfg_p.read_text()), json.loads(sum_p.read_text())
        key = (f"{cfg['provider']}:{cfg['model']}", cfg["thinking"])
        entry = rows.setdefault(key, {"model": cfg["model"], "provider": cfg["provider"], "thinking": key[1], "runs": {}})
        if cfg["condition"] in entry["runs"]:
            raise SystemExit(f"two runs for {key[0]} thinking={key[1]} condition={cfg['condition']}: "
                             f"{entry['runs'][cfg['condition']]['dir']} and {run_dir}; pass --manifest listing the run directories to use")
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
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    for r in load_jsonl(Path(run_dir) / "raw.jsonl"):
        if r["unit_id"] not in expected:
            continue
        key = (r["unit_id"], r.get("sample", 0))
        # Match score.latest_rows: retain a prior success over a failed retry.
        if key not in latest or not r.get("reply", {}).get("error"):
            latest[key] = r
    cur = {u: hashlib.sha256(items[u]["text"].encode()).hexdigest()[:16] for u in expected if u in items}
    stale = sum(1 for (u, _), r in latest.items() if r.get("text_sha") is not None and r["text_sha"] != cur[u])
    unhashed = sum(1 for r in latest.values() if r.get("text_sha") is None)
    missing = sum(1 for u in expected if u not in {key[0] for key in latest})
    return {"stale": stale, "missing": missing, "unhashed": unhashed}


def score_staleness(run_dir: str, items: dict[str, dict[str, Any]], expected: set[str]) -> str | None:
    """A reason the scored file is stale, or None. Scores carry per-item fingerprints of the
    fields a label depends on (text, answer, aliases, original answer/aliases) and the
    matcher version; any mismatch with the current item file invalidates them."""
    from altered_riddles.match import MATCHER_VERSION
    from altered_riddles.score import SCORER_VERSION, item_fingerprints
    summ_p = Path(run_dir) / "scored_summary.json"
    if not summ_p.exists():
        return "no scored_summary.json"
    prov = json.loads(summ_p.read_text()).get("scoring")
    if not prov:
        return "scores carry no provenance fingerprint (re-score)"
    if prov.get("matcher_version") != MATCHER_VERSION:
        return f"scored with matcher v{prov.get('matcher_version')}, current v{MATCHER_VERSION} (re-score)"
    if prov.get("scorer_version") != SCORER_VERSION:
        return f"scores predate scorer v{SCORER_VERSION} empty/truncated-answer handling (re-score)"
    stored = prov.get("item_fingerprints", {})
    now = item_fingerprints(items, expected)
    changed = sum(1 for u, h in now.items() if stored.get(u) != h)
    if changed:
        return f"{changed} items changed text/aliases since scoring (re-score)"
    return None


def familiarity_staleness(run_dir: str, items: dict[str, dict[str, Any]]) -> str | None:
    from altered_riddles.score import SCORER_VERSION, familiarity_fingerprint
    prov = json.loads((Path(run_dir) / "scored.json").read_text()).get("scoring")
    if not prov:
        return "familiarity scores carry no provenance fingerprint (re-score)"
    if prov.get("scorer_version") != SCORER_VERSION:
        return f"familiarity scores predate scorer v{SCORER_VERSION} answer extraction (re-score)"
    if prov.get("familiarity_fingerprint") != familiarity_fingerprint(items):
        return "original answers/aliases changed since familiarity scoring (re-score)"
    return None


def mean_output_tokens(run_dir: str, expected: set[str]) -> float | None:
    """Mean completion tokens over the latest successful reply per (item, sample)."""
    latest: dict[tuple[str, int], dict[str, Any]] = {}
    raw_p = Path(run_dir) / "raw.jsonl"
    if not raw_p.exists():
        return None
    for r in load_jsonl(raw_p):
        if r["unit_id"] not in expected:
            continue
        key = (r["unit_id"], r.get("sample", 0))
        if key not in latest or not r.get("reply", {}).get("error"):
            latest[key] = r
    toks = [r["reply"]["completion_tokens"] for r in latest.values()
            if isinstance(r.get("reply"), dict) and isinstance(r["reply"].get("completion_tokens"), (int, float))]
    return mean(toks)


def rank_spread(row_id: str, board: list[dict[str, Any]], comparisons: list[dict[str, Any]]) -> tuple[int, int]:
    """Plausible rank range from the pairwise COR-difference intervals: best = 1 + number of
    rows whose COR is significantly lower, worst = n - number of rows significantly higher.
    A pointwise interval excluding zero counts as significant; no multiplicity adjustment."""
    better, worse = set(), set()
    for c in comparisons:
        if row_id not in (c["a"], c["b"]) or c.get("ci95") is None or c["ci95"][0] is None:
            continue
        other = c["b"] if c["a"] == row_id else c["a"]
        lo, hi = c["ci95"]
        # difference is COR(a) - COR(b): entirely positive means a overrides more than b
        a_worse = lo > 0
        a_better = hi < 0
        if c["a"] == row_id:
            (worse if a_better else better if a_worse else set()).add(other)
        else:
            (better if a_better else worse if a_worse else set()).add(other)
    return 1 + len(better), len(board) - len(worse)


def type_breakdown(board: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per alteration type: mean COR / altered accuracy across rows, and each row's values."""
    types = sorted({t for r in board for t in r.get("by_type", {})})
    out = []
    for t in types:
        per = {r["id"]: {"model": r["model"], "thinking": r["thinking"], **r["by_type"][t]} for r in board if t in r.get("by_type", {})}
        cors = [v["cor"] for v in per.values() if v["cor"] is not None]
        accs = [v["alt_acc"] for v in per.values() if v["alt_acc"] is not None]
        out.append({"type": t, "n_items": max((v["n_items"] for v in per.values()), default=0),
                    "mean_cor": mean(cors), "mean_alt_acc": mean(accs),
                    "per_model": {k: {kk: vv for kk, vv in v.items() if kk != "n_items"} for k, v in per.items()}})
    return out


def build(items: dict[str, dict[str, Any]], runs_dir: Path, n_boot: int, seed: int, manifest: list[str] | None = None) -> dict[str, Any]:
    if n_boot < 1:
        raise ValueError("n_boot must be positive")
    items = {u: it for u, it in items.items() if it.get("gate", {}).get("passed", True)}
    expected = set(items)
    rng = random.Random(seed)
    rows = collect_runs(runs_dir, items, manifest)
    board: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    item_rates: dict[str, dict[str, float]] = {}
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
        # rows for items dropped since the run are ignored (their raw rows are pruned on the next resume)
        scored = [s for s in load_jsonl(scored_p) if s["unit_id"] in items]
        unresolved = sum(s["label"] not in {"correct", "original", "other", "abstain"} for s in scored)
        answered = {s["unit_id"] for s in scored}
        keys = {(s["unit_id"], s["sample"]) for s in scored}
        expected_keys = {(u, sample) for u in expected for sample in range(unw["config"]["samples"])}
        if unresolved or answered != expected or keys != expected_keys or len(keys) != len(scored):
            excluded.append({"model": mkey, "thinking": th,
                             "reason": f"incomplete/invalid scoring: {unresolved} unresolved, "
                                       f"{len(expected - answered)} missing items, {len(expected_keys - keys)} missing samples, "
                                       f"{len(keys - expected_keys)} unexpected samples, {len(scored) - len(keys)} duplicate samples"})
            continue
        familiar = json.loads(fam_p.read_text())["familiar"]
        pending = 0
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
        rates: dict[str, list[int]] = defaultdict(list)
        for s in scored:
            if familiar.get(items[s["unit_id"]]["source"], 0) >= FAMILIAR_THRESHOLD:
                rates[s["unit_id"]].append(int(s["label"] == "original"))
        labels = defaultdict(int)
        for s in scored:
            labels[s["label"]] += 1
        n = len(scored)
        warned = e["runs"].get("warned")
        warned_acc = None
        if warned and (Path(warned["dir"]) / "scored.jsonl").exists():
            ws = [s for s in load_jsonl(Path(warned["dir"]) / "scored.jsonl") if s["unit_id"] in items]
            warned_keys = {(s["unit_id"], s["sample"]) for s in ws}
            expected_warned = {(u, sample) for u in expected for sample in range(warned["config"]["samples"])}
            if (warned_keys == expected_warned and len(warned_keys) == len(ws)
                    and all(s["label"] in {"correct", "original", "other", "abstain"} for s in ws)):
                warned_acc = mean([int(s["label"] == "correct") for s in ws])
        alt_acc = mean([int(s["label"] == "correct") for s in scored])
        item_sources = {items[u]["source"] for u in expected if u in items}
        original_acc = mean([familiar[src] for src in sorted(item_sources) if src in familiar])
        mean_tokens = mean_output_tokens(unw["dir"], expected)
        by_type_acc: dict[str, list[int]] = defaultdict(list)
        by_type_cor: dict[str, list[int]] = defaultdict(list)
        for s in scored:
            it = items[s["unit_id"]]
            t = it.get("type", "unknown")
            by_type_acc[t].append(int(s["label"] == "correct"))
            if familiar.get(it["source"], 0) >= FAMILIAR_THRESHOLD:
                by_type_cor[t].append(int(s["label"] == "original"))
        by_type = {t: {"n_items": len({s["unit_id"] for s in scored if items[s["unit_id"]].get("type", "unknown") == t}),
                       "alt_acc": mean(by_type_acc[t]), "cor": mean(by_type_cor.get(t, []))} for t in sorted(by_type_acc)}
        # pre-publish checks (automatic part of the release checklist)
        checks: list[str] = []
        d = drift(unw["dir"], items, expected)
        if d["stale"]:
            checks.append(f"{d['stale']} raw samples have stale item text (re-run to refresh)")
        if d["missing"]:
            checks.append(f"{d['missing']} passed items not answered")
        if d["unhashed"]:
            checks.append(f"{d['unhashed']} rows predate text hashes (item set unverifiable)")
        stale = score_staleness(unw["dir"], items, expected)
        if stale:
            checks.append(f"unwarned scores: {stale}")
        stale_fam = familiarity_staleness(orig["dir"], items)
        if stale_fam:
            checks.append(stale_fam)
        if warned and warned_acc is not None:
            stale_w = score_staleness(warned["dir"], items, expected)
            if stale_w:
                checks.append(f"warned scores: {stale_w}")
        if warned:
            dw = drift(warned["dir"], items, expected)
            if dw["stale"] or dw["missing"]:
                checks.append(f"warned run: {dw['stale']} stale samples, {dw['missing']} missing items")
        n_rows = unw["summary"].get("n_rows") or n
        trunc_rate = (unw["summary"].get("truncated") or 0) / n_rows if n_rows else 0.0
        if trunc_rate > CHECK_MAX_TRUNCATED:
            checks.append(f"{trunc_rate:.0%} of replies truncated by max_tokens")
        dodge = ((labels["other"] + labels["abstain"]) / n) if n else 0.0
        if dodge > CHECK_MAX_DODGE:
            checks.append(f"other+abstain {dodge:.0%}: COR flattered, rank by accuracy")
        fam_share = (sum(1 for src in item_sources if familiar.get(src, 0) >= FAMILIAR_THRESHOLD) / len(item_sources)) if item_sources else 0.0
        if fam_share < CHECK_MIN_FAMILIAR:
            checks.append(f"familiar with only {fam_share:.0%} of item sources")
        if checks:
            excluded.append({"model": mkey, "thinking": th, "reason": "; ".join(checks)})
            continue
        item_rates[row_id] = {u: sum(v) / len(v) for u, v in rates.items()}
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
            "mean_output_tokens": mean_tokens, "original_acc": original_acc, "by_type": by_type,
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
    # Non-significance is not equivalence and is not transitive: do not form tie groups.
    for rank, r in enumerate(board, 1):
        r["point_rank"] = rank
    comparisons = pairwise_comparisons(item_rates, {u: it.get("cluster", it["source"]) for u, it in items.items()},
                                      n_boot=n_boot, seed=seed)
    for r in board:
        r["rank_best"], r["rank_worst"] = rank_spread(r["id"], board, comparisons)
    alteration_types = type_breakdown(board)
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
            "run_manifest": manifest if manifest is not None else sorted(r["dir"] for e in rows.values() for r in e["runs"].values()),
            "familiar_threshold": FAMILIAR_THRESHOLD, "rows": board, "excluded": excluded, "review_flags": review,
            "alteration_types": alteration_types, "comparisons": comparisons,
            "comparison_method": "item-balanced COR difference a-b on shared familiar items; jointly resampled clusters; pointwise CI95, no multiplicity adjustment"}


def pct(x: float | None) -> str:
    return "—" if x is None else f"{100*x:.1f}%"


def render_md(b: dict[str, Any]) -> str:
    lines = ["# Altered Riddles v2 — leaderboard", "",
             f"_Generated {b['generated_at']}. Primary metric: **COR** (conditioned override rate, lower is better) with a clustered-bootstrap CI95 (clusters = source riddle, {b['n_boot']} draws). Ranks are point estimates, not significant differences; the rank spread counts rows whose pairwise interval excludes zero. Comparisons in the JSON use shared familiar items and jointly resampled clusters (pointwise intervals, not multiplicity-adjusted). Rows must pass scoring and pre-publish checks; Git commitment status is not verified._", "",
             "| point rank | rank spread | model | thinking | items | COR ↓ | CI95 | orig acc | alt acc ↑ | warned acc | override gap | abstain | other | median reasoning tok | mean out tok | k | pending | familiarity | checks |",
             "|---|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for r in b["rows"]:
        ci = "—" if r["cor_ci95"][0] is None else f"[{100*r['cor_ci95'][0]:.1f}, {100*r['cor_ci95'][1]:.1f}]"
        spread = f"{r['rank_best']}–{r['rank_worst']}" if r.get("rank_best") is not None else "—"
        mot = "—" if r.get("mean_output_tokens") is None else f"{r['mean_output_tokens']:.0f}"
        lines.append(f"| {r.get('point_rank','—')} | {spread} | {r['model']} | {r['thinking']} | {r['n_items']} | {pct(r['cor'])} | {ci} | {pct(r.get('original_acc'))} | {pct(r['alt_acc'])} | {pct(r['warned_acc'])} | {pct(r['override_gap'])} | {pct(r['abstain_rate'])} | {pct(r['other_rate'])} | {r['median_reasoning_tokens']} | {mot} | {r['samples']} | {r['pending']} | {r.get('familiarity_mode', 'direct')} | {'ok' if not r.get('checks') else 'see below'} |")
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
    ap.add_argument("--manifest", default=None, help="JSON file {\"runs\": [run dirs]} naming exactly which runs to use")
    ap.add_argument("--status", default="development candidate, not frozen or publication-approved",
                    help="release_status string written into the board; displayed verbatim by the website")
    args = ap.parse_args()
    items = {i["id"]: i for i in load_jsonl(Path(args.items))}
    manifest = json.loads(Path(args.manifest).read_text())["runs"] if args.manifest else None
    b = build(items, Path(args.runs_dir), args.n_boot, args.seed, manifest)
    b["release_status"] = args.status
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leaderboard.json").write_text(json.dumps(b, indent=1))
    (out / "LEADERBOARD.md").write_text(render_md(b))
    print(render_md(b))


if __name__ == "__main__":
    main()
