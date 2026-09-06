import unittest

from altered_riddles.statistics import paired_comparison


class PairedComparisonTests(unittest.TestCase):
    def test_identical_models_have_zero_difference_on_every_draw(self):
        rates = {"easy": 0., "hard": 1.}
        result = paired_comparison(rates, rates, {u: u for u in rates}, n_boot=100)
        self.assertEqual(result["ci95"], [0., 0.])

    def test_only_shared_items_are_compared(self):
        result = paired_comparison({"a": .2, "only_a": 1.}, {"a": .7}, {"a": "c"}, n_boot=100)
        self.assertEqual(result["n_items"], 1)
        self.assertAlmostEqual(result["difference"], -.5)

    def test_cluster_is_resampled_as_a_whole(self):
        result = paired_comparison({"a": 0., "b": 1.}, {"a": 0., "b": 0.}, {"a": "c", "b": "c"}, n_boot=100)
        self.assertEqual(result["ci95"], [.5, .5])
        self.assertEqual(result["n_clusters"], 1)

    def test_no_overlap_and_invalid_draw_count(self):
        self.assertIsNone(paired_comparison({}, {}, {}, n_boot=10)["difference"])
        with self.assertRaises(ValueError):
            paired_comparison({}, {}, {}, n_boot=0)

    def test_reproducible_and_symmetric(self):
        a, b, cl = {"a": .1, "b": .5}, {"a": .4, "b": .2}, {"a": "a", "b": "b"}
        ab = paired_comparison(a, b, cl, n_boot=200, seed=10)
        self.assertEqual(ab, paired_comparison(a, b, cl, n_boot=200, seed=10))
        ba = paired_comparison(b, a, cl, n_boot=200, seed=10)
        self.assertAlmostEqual(ab["difference"], -ba["difference"])


if __name__ == "__main__":
    unittest.main()
