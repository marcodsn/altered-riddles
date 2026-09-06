import calendar
import hashlib
import json
import unittest
from pathlib import Path

from altered_riddles.audit import analyze
from altered_riddles.review_validity import load_review_items, parse_review, request_tags


class AuditTests(unittest.TestCase):
    def test_shared_familiarity_and_pairing(self):
        items = {"x": {"source": "s"}, "y": {"source": "t"}}
        a = {"id": "a", "model": "a", "thinking": "on"}
        b = {"id": "b", "model": "b", "thinking": "on"}
        sa = [{"unit_id": "x", "label": "correct"}, {"unit_id": "y", "label": "original"}]
        sb = [{"unit_id": "x", "label": "original"}, {"unit_id": "y", "label": "correct"}]
        result = analyze(items, [(a, sa, {"s": 1, "t": 1}), (b, sb, {"s": 1, "t": 0})], set(items), n_boot=100)
        self.assertEqual(result["n_shared_familiar_sources"], 1)
        self.assertEqual(result["rows"][0]["cor"], .5)
        self.assertEqual(result["rows"][0]["shared_familiar_cor"], 0.)
        self.assertEqual(result["comparisons"][0]["difference"], -1.)
        self.assertEqual(result["comparisons"][0]["n_items"], 1)

    def test_nous_user_tag_wire_shape(self):
        self.assertEqual(request_tags("marcodsn"), {"tags": ["user=marcodsn"]})
        self.assertEqual(request_tags(None), {})

    def test_revision_provenance_and_isolation(self):
        root = Path(__file__).resolve().parents[1]
        decisions = json.loads((root / "results/audit/adjudication-v1/decisions.json").read_text())
        for prefix in ["items", "revision"]:
            self.assertEqual(hashlib.sha256((root / decisions[prefix + "_path"]).read_bytes()).hexdigest(),
                             decisions[prefix + "_sha256"])
        drafts = load_review_items(root / decisions["revision_path"])
        active = load_review_items(root / decisions["items_path"])
        self.assertEqual(len(drafts), 6)
        self.assertFalse(drafts.keys() & active.keys())
        for draft in drafts.values():
            self.assertIn(draft["replaces"], active)
            self.assertEqual(draft["status"], "draft_pending_validation")
            self.assertEqual(draft["human_review"], "pending")

    def test_exactly_28_is_not_at_least_28(self):
        # Gregorian calendar ground truth over a full 400-year cycle.
        # This independently checks the numerical claim, not natural-language
        # validity of every item in the benchmark.
        for year in range(2000, 2400):
            days = [calendar.monthrange(year, month)[1] for month in range(1, 13)]
            self.assertEqual(sum(n == 28 for n in days), 0 if calendar.isleap(year) else 1)
            self.assertEqual(sum(n >= 28 for n in days), 12)

    def test_review_parser_fails_closed(self):
        valid = {"id": "x", "original_excluded": True, "accepted_entailed": False,
                 "contradictory_premises": None, "disposition": "revise", "concern": "ambiguous"}
        self.assertIsNotNone(parse_review(json.dumps([valid]), ["x"]))
        self.assertIsNone(parse_review(json.dumps([valid, valid]), ["x", "y"]))
        self.assertIsNone(parse_review(json.dumps([{**valid, "original_excluded": "true"}]), ["x"]))
        self.assertIsNone(parse_review("not json", ["x"]))


if __name__ == "__main__":
    unittest.main()
