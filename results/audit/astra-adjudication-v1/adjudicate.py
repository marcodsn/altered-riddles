"""Scoped, offline AI adjudication overlay. Run from the repository root; never rescore.

No client is constructed. Disable dotenv before importing the existing scorer's
pure extraction/fingerprint helpers. Existing output directories are never reused.
"""
import os
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import argparse
import copy
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from altered_riddles import board, score
from altered_riddles.match import extract_final_answer

ROOT = Path("results/audit/astra-adjudication-v1")
CANDIDATE = Path("results/audit/adjudication-v2/core.candidate.jsonl")
SOURCE_MANIFEST = Path("results/audit/adjudication-v2/candidate_run_manifest_scorer_v2.json")
CAP_MANIFEST = Path("results/audit/cap-sensitivity-v1/run_manifest.json")
CORE_TARGET = Path("runs/core-candidate-adjudicated-v1")
CAP_TARGET = Path("runs/cap-sensitivity-adjudicated-v1")
MODEL = "openai-codex/gpt-6-astra"
NOTICE = "AI adjudication, not human review or independent empirical validation; selected cases, not a representative judge-accuracy audit."


def load(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def save(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_sha(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def require(ok, context):
    if not ok:
        raise ValueError(context)


def one(sequence, key, context):
    found = [r for r in sequence if (r["unit_id"], r["sample"]) == key]
    require(len(found) == 1, f"{context}: expected exactly one row for {key}, got {len(found)}")
    return found[0]


def bind(run, item, sample, final, context):
    """Fail closed on item, response, or raw/scored identity drift."""
    run = Path(run)
    key = (item["id"], sample)
    raw = one(score.latest_rows(run / "raw.jsonl"), key, context + " raw")
    scored = one(rows(run / "scored.jsonl"), key, context + " scored")
    text_sha = hashlib.sha256(item["text"].encode()).hexdigest()[:16]
    require(raw.get("text_sha") == scored.get("text_sha") == text_sha, context + ": item text hash mismatch")
    require(scored["final"] == final == extract_final_answer(score.answer_text(raw["reply"])), context + ": final-answer mismatch")
    require(not raw["reply"].get("error"), context + ": raw error")
    return {
        "run": str(run), "unit_id": item["id"], "sample": sample,
        "final_answer": final, "final_answer_sha256": hashlib.sha256(final.encode()).hexdigest(),
        "item_fingerprint": score.item_fingerprints({item["id"]: item}, [item["id"]])[item["id"]],
        "item_fields_sha256": object_sha({k: item.get(k) for k in score.ITEM_FIELDS}),
        "text_sha": text_sha, "raw_file_sha256": sha(run / "raw.jsonl"),
        "raw_row_sha256": object_sha(raw), "scored_file_sha256": sha(run / "scored.jsonl"),
        "scored_row_sha256": object_sha(scored), "base_label": scored["label"],
        "base_judge_verdict": scored.get("judge"),
    }


def prepare_decisions():
    manifest = load(ROOT / "input_manifest.json")
    require(sha(ROOT / "review_packet.json") == manifest["packet_sha256"], "packet hash mismatch")
    audit_path = Path("results/audit/adjudication-v2/label_audit.json")
    require(sha(audit_path) == manifest["audit_sha256"], "historical audit hash mismatch")
    audit = {r["n"]: r for r in load(audit_path)["rows"]}
    packet = {r["case_id"]: r for r in load(ROOT / "review_packet.json")["cases"]}
    evidence = load(ROOT / "review_evidence.json")
    for review in evidence["evidence"]:
        require(sha(review["audit_copy"]) == review["sha256"], "review evidence hash mismatch: " + review["audit_copy"])
    dispositions = load(ROOT / "approved_dispositions.json")
    require(dispositions["runtime_model"] == MODEL, "runtime model mismatch")
    final_cases = {r["case_id"]: r for r in dispositions["cases"]}
    require(len(packet) == len(manifest["lineage"]) == len(final_cases) == 15, "case count mismatch")
    require(set(packet) == set(final_cases) == {r["case_id"] for r in manifest["lineage"]}, "case identity mismatch")
    current = score.load_items(CANDIDATE)
    candidate_runs = set(load(SOURCE_MANIFEST)["runs"])
    cap_runs = set(load(CAP_MANIFEST)["runs"])
    decisions = []
    for lineage in manifest["lineage"]:
        cid = lineage["case_id"]
        case, disposition = packet[cid], final_cases[cid]
        require(disposition["label"] in score.JUDGE_LABELS, cid + ": invalid disposition")
        item_file = Path(lineage["item_file"])
        require(sha(item_file) == lineage["item_file_sha256"], cid + ": item file hash mismatch")
        item = score.load_items(item_file)[lineage["unit_id"]]
        require(case["item"]["id"] == item["id"] and all(case["item"].get(k) == item.get(k) for k in score.ITEM_FIELDS), cid + ": packet item mismatch")
        source = Path(lineage["run"] if lineage["run"].startswith("runs/") else "runs/" + lineage["run"])
        for field, name in [("raw_sha256", "raw.jsonl"), ("scored_sha256", "scored.jsonl")]:
            if field in lineage:
                require(sha(source / name) == lineage[field], cid + ": " + field + " mismatch")
        binding = bind(source, item, lineage["sample"], case["final_answer_to_grade"], cid)
        decision = {**disposition, "item_file": str(item_file), "item_file_sha256": sha(item_file), "source_binding": binding}
        if cid.startswith("historical-"):
            old = audit[lineage["audit_n"]]
            require((old["run"], old["unit_id"], old["sample"], old["final"], old["new_label"]) ==
                    (lineage["run"], item["id"], lineage["sample"], binding["final_answer"], binding["base_label"]), cid + ": historical audit identity mismatch")
            decision["previous_review_label"] = old["review_label"]
            decision["previous_review_provenance"] = old["label_provenance"]
            if item["id"] not in current:
                decision["scope"] = "historical-only; item absent from current candidate, no transfer"
            else:
                require(all(item.get(k) == current[item["id"]].get(k) for k in score.ITEM_FIELDS), cid + ": current item fingerprint mismatch; stop, do not transfer")
                target_source = Path("runs/core-candidate-scored-v2") / lineage["run"]
                require(str(target_source) in candidate_runs, cid + ": run absent from current manifest")
                cb = bind(target_source, current[item["id"]], lineage["sample"], binding["final_answer"], cid + " candidate")
                require(cb["raw_row_sha256"] == binding["raw_row_sha256"], cid + ": candidate raw lineage mismatch")
                origins = load(target_source / "lineage.json")
                origin = one(origins["sample_origin"], (item["id"], lineage["sample"]), cid + " origin")
                require(origin["run"] == str(source), cid + ": candidate origin run mismatch")
                require(origins["historical"]["raw_sha256"] == binding["raw_file_sha256"], cid + ": candidate historical raw hash mismatch")
                decision.update(scope="current-candidate and historical", application_binding=cb,
                                candidate_lineage_sha256=sha(target_source / "lineage.json"))
        else:
            require(str(source) in cap_runs, cid + ": cap run absent from manifest")
            decision.update(scope="cap-only; never spliced into full candidate", application_binding=binding)
        decisions.append(decision)
    return decisions


def rates(counts):
    n = sum(v for k, v in counts.items() if k != "error")
    return {"n": n, **{k: round(counts[k] / n, 4) if n else None for k in ("correct", "original", "other", "abstain", "pending")}}


def refreshed_summary(base, scored, items, familiar, overlay):
    result = copy.deepcopy(base)
    counts = Counter(r["label"] for r in scored)
    conditioned = Counter(r["label"] for r in scored if r["label"] != "error" and familiar.get(items[r["unit_id"]]["source"], 0) >= score.FAMILIAR_THRESHOLD)
    by_type, by_family = defaultdict(Counter), defaultdict(Counter)
    for r in scored:
        item = items[r["unit_id"]]
        by_type[item["type"]][r["label"]] += 1
        by_family[item.get("family", "?")][r["label"]] += 1
    result.update(overall=rates(counts), conditioned_on_familiar={**rates(conditioned), "familiar_sources_known": bool(familiar), "cor": rates(conditioned)["original"]},
                  by_type={k: rates(v) for k, v in by_type.items()}, by_family={k: rates(v) for k, v in by_family.items()})
    # Preserve base judge, judged_rows, scored_at, and scoring/code provenance.
    # This is an overlay, not another deterministic pass or fresh judge inference.
    result["adjudication_overlay"] = overlay
    return result


def differences(before, after, prefix=""):
    changes = []
    if isinstance(before, dict) and isinstance(after, dict):
        for k in sorted(before.keys() | after.keys()):
            changes.extend(differences(before.get(k), after.get(k), prefix + "." + k if prefix else k))
    elif isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)) and len(before) == len(after):
        for index, (old, new) in enumerate(zip(before, after)):
            changes.extend(differences(old, new, f"{prefix}[{index}]"))
    elif before != after:
        row = {"field": prefix, "before": before, "after": after}
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            row["delta"] = after - before
        changes.append(row)
    return changes


def derivative(manifest_path, target_root, items_file, decisions):
    items = score.load_items(items_file)
    source_runs = load(manifest_path)["runs"]
    runs, impacts, lineage_records = [], [], []
    for run in source_runs:
        source = Path(run)
        target = target_root / source.parent.name / source.name
        shutil.copytree(source, target)
        selected = [d for d in decisions if d.get("application_binding", {}).get("run") == run]
        overlay = {"type": "AI adjudication overlay", "runtime_model": MODEL, "notice": NOTICE,
                   "decisions_file": str(ROOT / "decisions.json"), "decisions_sha256": sha(ROOT / "decisions.json"),
                   "case_ids": [d["case_id"] for d in selected], "inference_calls": 0,
                   "base_run": run, "base_raw_sha256": sha(source / "raw.jsonl")}
        save(target / "adjudication_overlay.json", overlay)
        if (source / "scored.jsonl").exists():
            scored = rows(source / "scored.jsonl")
            for d in selected:
                binding = d["application_binding"]
                r = one(scored, (binding["unit_id"], binding["sample"]), d["case_id"])
                require(object_sha(r) == binding["scored_row_sha256"], d["case_id"] + ": score changed after preflight")
                r["adjudication_overlay"] = {"case_id": d["case_id"], "base_label": r["label"],
                                             "decisions_sha256": overlay["decisions_sha256"], "runtime_model": MODEL}
                r["label"] = d["label"]
            (target / "scored.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in scored))
            fam_paths = sorted(source.parent.glob("original-think*-k*/scored.json"), key=lambda p: ("thinkoff" in p.parent.name, int(p.parent.name.split("-k", 1)[1].split("-", 1)[0])))
            familiar = load(fam_paths[-1])["familiar"] if fam_paths else {}
            base = load(source / "scored_summary.json")
            summary = refreshed_summary(base, scored, items, familiar, overlay)
            save(target / "scored_summary.json", summary)
            impacts.append({"source_run": run, "run": str(target), "case_ids": overlay["case_ids"],
                            "label_transitions": dict(Counter(d["application_binding"]["base_label"] + " -> " + d["label"] for d in selected)),
                            "summary_changes": differences({k: base[k] for k in ("overall", "conditioned_on_familiar", "by_type", "by_family")}, {k: summary[k] for k in ("overall", "conditioned_on_familiar", "by_type", "by_family")})})
        require(sha(source / "raw.jsonl") == sha(target / "raw.jsonl"), run + ": raw copy mismatch")
        runs.append(str(target))
        lineage_records.append({"source_run": run, "derived_run": str(target), "source_files_sha256": {p.name: sha(p) for p in sorted(source.iterdir()) if p.is_file()}, "derived_files_sha256": {p.name: sha(p) for p in sorted(target.iterdir()) if p.is_file()}})
    manifest = {"runs": runs, "items_file": str(items_file), "items_sha256": sha(items_file), "source_manifest": str(manifest_path), "source_manifest_sha256": sha(manifest_path), "scorer_version": score.SCORER_VERSION, "adjudication": str(ROOT / "decisions.json"), "inference_calls": 0, "lineage": lineage_records}
    return manifest, impacts


def verify_preserved():
    hashes = load(ROOT / "preserved_hashes.json")
    for path, expected in hashes.items():
        require(Path(path).exists() and sha(path) == expected, "preserved artifact mismatch: " + path)
    return len(hashes)


def render_current_md(result):
    """Apply this audit's approved review policy without rewriting historical boards."""
    rendered = board.render_md(result).replace(
        "Human look before publishing; nothing is dropped automatically.",
        "Explicitly labelled AI validity review before publishing; no human review is required. Nothing is dropped automatically.",
    )
    return ("# Development candidate — scoped AI adjudication v1, NOT a release\n\n" + NOTICE
            + "\n\n13 historical cases resolved (all match unchanged current samples); two cap answers resolved separately. Historical token caps remain; no 64k splicing. Source permissions and release checks remain outstanding.\n\n"
            + rendered)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        print(f"Verified {verify_preserved()} preserved input files unchanged.")
        return
    for target in (CORE_TARGET, CAP_TARGET, ROOT / "core-board", ROOT / "decisions.json"):
        require(not target.exists(), "Output exists; use a new version: " + str(target))
    verify_preserved()
    decisions = prepare_decisions()  # all bindings validated before any derivative writes
    save(ROOT / "decisions.json", {"notice": NOTICE, "runtime_model": MODEL, "interpretation": "astra-answer-interpretation-v1 with supervisor-approved distinguishing-constraint qualification", "review_evidence": load(ROOT / "review_evidence.json"), "inference_calls": 0, "cases": decisions, "counts": dict(Counter(d["label"] for d in decisions))})
    core, core_impacts = derivative(SOURCE_MANIFEST, CORE_TARGET, CANDIDATE, decisions)
    cap, cap_impacts = derivative(CAP_MANIFEST, CAP_TARGET, Path("results/audit/adjudication-v2/repairs.gated.jsonl"), decisions)
    save(ROOT / "candidate_run_manifest.json", core)
    save(ROOT / "cap_run_manifest.json", cap)
    result = board.build(score.load_items(CANDIDATE), CORE_TARGET, 2000, 0, core["runs"])
    result.update(release_status="development candidate, not frozen or publication-approved", scorer_version=score.SCORER_VERSION,
                  adjudication=str(ROOT / "decisions.json"), limitations=[NOTICE, "Scoped interpretation only; unaudited responses were not reinterpreted.", "Historical token-cap responses retained; 64k repair-slice diagnostic is separate.", "Licensing, per-item provenance, packaging and release checks remain; no significant ranking claims."])
    save(ROOT / "core-board/leaderboard.json", result)
    (ROOT / "core-board/LEADERBOARD.md").write_text(render_current_md(result))
    previous = load("results/audit/adjudication-v2/core-board-scorer-v2/leaderboard.json")
    old_rows = {r["id"]: r for r in previous["rows"]}
    board_changes = {r["id"]: differences({k: v for k, v in old_rows[r["id"]].items() if k != "run_dir"}, {k: v for k, v in r.items() if k != "run_dir"}) for r in result["rows"]}
    comparison = load("results/audit/cap-sensitivity-v1/comparison.json")
    comparison.update(adjudication=str(ROOT / "decisions.json"), base_comparison_sha256=sha("results/audit/cap-sensitivity-v1/comparison.json"), notice=NOTICE)
    for condition in comparison["conditions"].values():
        high = condition["high_cap"]
        old_run = high["run_dir"]
        new_run = CAP_TARGET / Path(old_run).parent.name / Path(old_run).name
        high.update(base_run_dir=old_run, run_dir=str(new_run), labels=dict(Counter(r["label"] for r in rows(new_run / "scored.jsonl"))))
        high["accuracy"] = high["labels"].get("correct", 0) / high["n"]
    save(ROOT / "cap_comparison.json", comparison)
    save(ROOT / "impact.json", {"scope_counts": dict(Counter(d["scope"] for d in decisions)),
        "final_label_counts": dict(Counter(d["label"] for d in decisions)),
        "historical_judge_transitions": dict(Counter(d["source_binding"]["base_label"] + " -> " + d["label"] for d in decisions if d["case_id"].startswith("historical-"))),
        "historical_review_transitions": dict(Counter(d["previous_review_label"] + " -> " + d["label"] for d in decisions if "previous_review_label" in d)),
        "core_runs": core_impacts, "cap_runs": cap_impacts, "board_row_changes": board_changes,
        "board_comparison_changes": differences(previous["comparisons"], result["comparisons"]),
        "board_review_flag_changes": differences(previous["review_flags"], result["review_flags"]),
        "excluded_before": previous["excluded"], "excluded_after": result["excluded"]})
    count = verify_preserved()
    save(ROOT / "validation.json", {"preserved_input_files": count, "all_preserved_hashes_match": True, "inference_calls": 0, "runtime_model": MODEL, "case_count": len(decisions), "current_candidate_cases": sum(d["scope"] == "current-candidate and historical" for d in decisions), "historical_only_cases": sum(d["scope"].startswith("historical-only") for d in decisions), "cap_cases": 2, "board_rows": len(result["rows"]), "excluded": result["excluded"], "board_checks": {r["id"]: r["checks"] for r in result["rows"]}, "script_sha256": sha(__file__)})
    print(json.dumps({"cases": len(decisions), "labels": dict(Counter(d["label"] for d in decisions)), "preserved_files": count, "board_rows": len(result["rows"]), "inference_calls": 0}))


if __name__ == "__main__":
    main()
