"""Regression checks for the scoped Astra overlay, not a new general scorer rubric."""
import copy
import importlib.util
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "results/audit/astra-adjudication-v1/adjudicate.py"
spec = importlib.util.spec_from_file_location("astra_adjudicate", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AstraAdjudicationTests(unittest.TestCase):
    def test_packet_lineage_and_approved_dispositions_offline(self):
        with patch.object(audit.score, "Client", side_effect=AssertionError("No inference allowed")):
            decisions = audit.prepare_decisions()
        self.assertEqual(len(decisions), 15)
        self.assertEqual(Counter(d["label"] for d in decisions), {"original": 5, "other": 10})
        self.assertEqual(sum(d["scope"] == "current-candidate and historical" for d in decisions), 13)
        for cid in ("historical-18", "historical-32"):
            self.assertEqual(next(d["label"] for d in decisions if d["case_id"] == cid), "other")

    def test_binding_rejects_changed_final_item_and_duplicate_sample(self):
        d = audit.load(audit.ROOT / "decisions.json")["cases"][0]
        item = audit.score.load_items(Path(d["item_file"]))[d["source_binding"]["unit_id"]]
        binding = d["source_binding"]
        with tempfile.TemporaryDirectory() as td:
            run = Path(td)
            raw = audit.one(audit.score.latest_rows(Path(binding["run"]) / "raw.jsonl"), (item["id"], binding["sample"]), "fixture")
            scored = audit.one(audit.rows(Path(binding["run"]) / "scored.jsonl"), (item["id"], binding["sample"]), "fixture")
            (run / "raw.jsonl").write_text(json.dumps(raw) + "\n")
            (run / "scored.jsonl").write_text(json.dumps(scored) + "\n")
            audit.bind(run, item, binding["sample"], binding["final_answer"], "fixture")
            with self.assertRaisesRegex(ValueError, "final-answer mismatch"):
                audit.bind(run, item, binding["sample"], binding["final_answer"] + " changed", "fixture")
            changed = {**item, "text": item["text"] + " changed"}
            with self.assertRaisesRegex(ValueError, "item text hash mismatch"):
                audit.bind(run, changed, binding["sample"], binding["final_answer"], "fixture")
            (run / "scored.jsonl").write_text((json.dumps(scored) + "\n") * 2)
            with self.assertRaisesRegex(ValueError, "exactly one row"):
                audit.bind(run, item, binding["sample"], binding["final_answer"], "fixture")

    def test_all_derivatives_preserve_raw_and_base_provenance(self):
        label_changes, overlays = Counter(), Counter()
        for manifest_name, expected_runs in (("candidate_run_manifest.json", 13), ("cap_run_manifest.json", 2)):
            manifest = audit.load(audit.ROOT / manifest_name)
            self.assertEqual(len(manifest["runs"]), expected_runs)
            for entry in manifest["lineage"]:
                source, target = Path(entry["source_run"]), Path(entry["derived_run"])
                self.assertEqual(audit.sha(source / "raw.jsonl"), audit.sha(target / "raw.jsonl"))
                for name in ("config.json", "summary.json", "lineage.json", "judge_cache.jsonl", "scored.json"):
                    if (source / name).exists():
                        self.assertEqual(audit.sha(source / name), audit.sha(target / name))
                if not (source / "scored.jsonl").exists():
                    continue
                before, after = audit.rows(source / "scored.jsonl"), audit.rows(target / "scored.jsonl")
                self.assertEqual(len(before), len(after))
                for old, new in zip(before, after):
                    clean = copy.deepcopy(new)
                    overlay = clean.pop("adjudication_overlay", None)
                    if old["label"] != new["label"]:
                        label_changes[manifest_name] += 1
                        self.assertIsNotNone(overlay)
                    if overlay:
                        overlays[manifest_name] += 1
                        self.assertEqual(overlay["base_label"], old["label"])
                    clean["label"] = old["label"]
                    self.assertEqual(clean, old)
                old_summary = audit.load(source / "scored_summary.json")
                summary = audit.load(target / "scored_summary.json")
                for key in ("scoring", "judge", "judged_rows", "scored_at", "deterministic_resolved"):
                    self.assertEqual(summary[key], old_summary[key])
                self.assertEqual(summary["overall"], audit.rates(Counter(r["label"] for r in after)))
        self.assertEqual(label_changes, {"candidate_run_manifest.json": 12, "cap_run_manifest.json": 2})
        self.assertEqual(overlays, {"candidate_run_manifest.json": 13, "cap_run_manifest.json": 2})

    def test_cap_is_separate_and_fully_resolved(self):
        core = audit.load(audit.ROOT / "candidate_run_manifest.json")
        cap = audit.load(audit.ROOT / "cap_run_manifest.json")
        self.assertTrue(all("cap-sensitivity" not in r and "cap64000" not in r for r in core["runs"]))
        self.assertTrue(set(core["runs"]).isdisjoint(cap["runs"]))
        for run in cap["runs"]:
            self.assertEqual(Counter(r["label"] for r in audit.rows(Path(run) / "scored.jsonl")), {"correct": 39, "other": 1})
            self.assertEqual(audit.load(Path(run) / "config.json")["max_tokens"], 64000)

    def test_board_and_exact_impact(self):
        impact = audit.load(audit.ROOT / "impact.json")
        self.assertEqual(impact["historical_judge_transitions"], {"other -> original": 3, "correct -> other": 7, "correct -> original": 2, "other -> other": 1})
        board = audit.load(audit.ROOT / "core-board/leaderboard.json")
        self.assertEqual(len(board["rows"]), 5)
        self.assertEqual(board["excluded"], [])
        for row in board["rows"]:
            self.assertEqual(row["checks"], [])
            self.assertEqual(row["n_items"], 264)
        self.assertEqual(audit.differences({"ci": [0.1, 0.2]}, {"ci": (0.1, 0.2)}), [])
        self.assertEqual(audit.differences([1], [2])[0]["delta"], 1)

    def test_current_board_uses_approved_ai_review_policy(self):
        result = audit.load(audit.ROOT / "core-board/leaderboard.json")
        rendered = audit.render_current_md(result)
        self.assertEqual(rendered, (audit.ROOT / "core-board/LEADERBOARD.md").read_text())
        self.assertIn("Explicitly labelled AI validity review before publishing", rendered)
        self.assertIn("no human review is required", rendered)
        self.assertNotIn("Human look before publishing", rendered)
        # The audit-local policy clarification does not mutate the generic renderer.
        self.assertIn("Human look before publishing", audit.board.render_md(result))

    def test_preserved_hashes_and_amended_policy(self):
        self.assertEqual(audit.verify_preserved(), 780)
        amendment = Path("docs/CORE_RELEASE_POLICY_AMENDMENT_ASTRA_V1.md").read_text()
        self.assertIn(audit.sha("docs/CORE_RELEASE_POLICY.md"), amendment)


if __name__ == "__main__":
    unittest.main()
