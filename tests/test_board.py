import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from altered_riddles.board import build, render_md
from altered_riddles.match import MATCHER_VERSION
from altered_riddles.score import familiarity_fingerprint, item_fingerprints


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.items = {"a": {"id": "a", "text": "changed", "source": "src", "gate": {"passed": True},
                            "answer": "x", "aliases": [], "original_answer": "o", "original_aliases": []}}
        self.unw = self.root / "model" / "unwarned"
        self.orig = self.root / "model" / "original"
        for condition, path in [("unwarned", self.unw), ("original", self.orig)]:
            path.mkdir(parents=True)
            (path / "config.json").write_text(json.dumps({"provider": "test", "model": "model", "thinking": "off", "condition": condition, "samples": 1}))
            (path / "summary.json").write_text(json.dumps({"guardrail": "PASS", "n_rows": 1}))
            (path / "raw.jsonl").write_text(json.dumps({"unit_id": "a", "text_sha": hashlib.sha256(b"changed").hexdigest()[:16]}) + "\n")
        (self.orig / "scored.json").write_text(json.dumps({"familiar": {"src": 1.},
                                                           "scoring": {"familiarity_fingerprint": familiarity_fingerprint(self.items)}}))
        (self.unw / "scored_summary.json").write_text(json.dumps({"scoring": {"matcher_version": MATCHER_VERSION,
                                                                              "item_fingerprints": item_fingerprints(self.items, {"a"})}}))
        self.scored = {"unit_id": "a", "sample": 0, "label": "correct"}
        self.save()

    def save(self, rows=None):
        (self.unw / "scored.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (rows if rows is not None else [self.scored])))

    def board(self):
        return build(self.items, self.root, 100, 0)

    def test_point_rank_not_equivalence(self):
        b = self.board()
        self.assertEqual(b["rows"][0]["point_rank"], 1)
        self.assertNotIn("rank_group", b["rows"][0])
        self.assertIn("not significant differences", render_md(b))

    def test_pending_error_unknown_labels_excluded(self):
        for label in ["pending", "error", "unknown"]:
            with self.subTest(label=label):
                self.scored["label"] = label
                self.save()
                self.assertEqual(self.board()["rows"], [])

    def test_missing_and_duplicate_samples_excluded(self):
        self.save([])
        self.assertEqual(self.board()["rows"], [])
        self.save([self.scored, self.scored])
        self.assertEqual(self.board()["rows"], [])
        self.save()
        cfg = json.loads((self.unw / "config.json").read_text())
        cfg["samples"] = 2
        (self.unw / "config.json").write_text(json.dumps(cfg))
        self.assertEqual(self.board()["rows"], [])

    def test_failed_gate_item_is_not_scored(self):
        self.items["dropped"] = {"text": "no", "source": "src", "gate": {"passed": False}}
        self.save([self.scored, {"unit_id": "dropped", "sample": 0, "label": "original"}])
        b = self.board()
        self.assertEqual(b["rows"][0]["n_items"], 1)
        self.assertEqual(b["rows"][0]["cor"], 0.)

    def test_stale_sample_cannot_hide_behind_fresh_sample(self):
        raw = self.unw / "raw.jsonl"
        fresh = json.loads(raw.read_text())
        raw.write_text(json.dumps({**fresh, "sample": 0, "text_sha": "stale"}) + "\n" +
                       json.dumps({**fresh, "sample": 1}) + "\n")
        self.assertEqual(self.board()["rows"], [])

    def test_dodge_guardrail_blocks_row(self):
        self.scored["label"] = "other"
        self.save()
        self.assertEqual(self.board()["rows"], [])

    def test_stale_text_blocks_row(self):
        self.items["a"]["text"] = "edited"
        self.assertEqual(self.board()["rows"], [])

    def test_alias_edit_invalidates_scores(self):
        # the raw text hash still matches, but the accepted aliases changed after scoring
        self.items["a"]["aliases"] = ["new alias"]
        b = self.board()
        self.assertEqual(b["rows"], [])
        self.assertIn("changed text/aliases since scoring", b["excluded"][0]["reason"])

    def test_original_alias_edit_invalidates_familiarity(self):
        self.items["a"]["original_aliases"] = ["another"]
        b = self.board()
        self.assertEqual(b["rows"], [])
        self.assertIn("familiarity", b["excluded"][0]["reason"])

    def test_scores_without_provenance_are_excluded(self):
        (self.unw / "scored_summary.json").write_text(json.dumps({}))
        b = self.board()
        self.assertEqual(b["rows"], [])
        self.assertIn("no provenance fingerprint", b["excluded"][0]["reason"])

    def test_old_matcher_version_is_excluded(self):
        (self.unw / "scored_summary.json").write_text(json.dumps({"scoring": {"matcher_version": MATCHER_VERSION - 1,
                                                                              "item_fingerprints": item_fingerprints(self.items, {"a"})}}))
        b = self.board()
        self.assertEqual(b["rows"], [])
        self.assertIn("matcher v", b["excluded"][0]["reason"])

    def test_two_runs_for_one_slot_need_a_manifest(self):
        dup = self.root / "model" / "unwarned-again"
        dup.mkdir()
        for name in ["config.json", "summary.json", "raw.jsonl", "scored.jsonl", "scored_summary.json"]:
            (dup / name).write_text((self.unw / name).read_text())
        with self.assertRaises(SystemExit):
            self.board()
        b = build(self.items, self.root, 100, 0, manifest=[str(self.unw), str(self.orig)])
        self.assertEqual(len(b["rows"]), 1)
        self.assertEqual(b["run_manifest"], [str(self.unw), str(self.orig)])


if __name__ == "__main__":
    unittest.main()
