import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from altered_riddles.board import build, render_md


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.items = {"a": {"id": "a", "text": "changed", "source": "src", "gate": {"passed": True}}}
        self.unw = self.root / "model" / "unwarned"
        self.orig = self.root / "model" / "original"
        for condition, path in [("unwarned", self.unw), ("original", self.orig)]:
            path.mkdir(parents=True)
            (path / "config.json").write_text(json.dumps({"provider": "test", "model": "model", "thinking": "off", "condition": condition, "samples": 1}))
            (path / "summary.json").write_text(json.dumps({"guardrail": "PASS", "n_rows": 1}))
            (path / "raw.jsonl").write_text(json.dumps({"unit_id": "a", "text_sha": hashlib.sha256(b"changed").hexdigest()[:16]}) + "\n")
        (self.orig / "scored.json").write_text(json.dumps({"familiar": {"src": 1.}}))
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


if __name__ == "__main__":
    unittest.main()
