import unittest

from altered_riddles.match import MATCHER_VERSION, extract_final_answer, label, matches


class MatchTests(unittest.TestCase):
    """Regression cases from the 2026-09-06 scoring audit of the Tier-0 runs."""

    def test_version_marker(self):
        self.assertGreaterEqual(MATCHER_VERSION, 2)

    def test_justification_phrase_does_not_flip_a_correct_reply(self):
        # three-apples-3: the original alias "the two you took" is longer than "three apples"
        correct = ["three", "3", "three apples", "3 apples"]
        original = ["two", "2", "the two you took"]
        for reply in ["Three apples (the two you took plus the one in your pocket)",
                      "3 apples (the two you took plus the one already in your pocket)"]:
            self.assertEqual(label(reply, correct=correct, original=original), "both", reply)

    def test_mixed_replies_go_to_the_judge(self):
        cases = [
            # surgeon-1
            ("His grandfather (the surgeon is the boy's mother's father).",
             ["his grandfather", "grandfather", "the boy's grandfather"], ["the surgeon is the boy's mother", "mother", "the boy's mother"]),
            # cowboy-friday-1
            ("Thursday (his horse is named Friday)", ["Thursday", "on Thursday"], ["his horse is named Friday", "friday is the horse's name"]),
            # months-28-days-3: a self-correction that ends on the right answer
            ("All 12 months have at least 28 days, but only February has exactly 28. So the answer is 0.",
             ["none", "zero", "0", "no months"], ["all of them", "all 12", "twelve", "12", "every month"]),
            # monty-hall-1: the token-subset rule matches "you should switch" inside "you should not switch"
            ("No, you should not switch.", ["no", "do not switch", "stay"], ["yes, switch", "switch", "you should switch"]),
            # a genuine override with the right words quoted back
            ("Once (after subtracting 5 from 25, you have 20 left; to reach nothing you subtract five times)",
             ["five", "5", "five times"], ["once", "one time", "only once"]),
        ]
        for reply, correct, original in cases:
            self.assertEqual(label(reply, correct=correct, original=original), "both", reply)

    def test_exact_match_still_beats_substring_overlap(self):
        # bat-and-ball-2: "$1.05" contains the original alias ".05"
        self.assertEqual(label("$1.05", correct=["$1.05", "1.05"], original=["5 cents", ".05", "$0.05"]), "correct")
        self.assertEqual(label("two", correct=["one", "1"], original=["two", "2", "the two you took"]), "original")

    def test_single_list_matches_are_deterministic(self):
        self.assertEqual(label("He was bald.", correct=["he walked under the arcade"], original=["he is bald", "bald"]), "original")
        self.assertEqual(label("Under the covered arcade", correct=["the covered arcade", "under cover"], original=["he is bald", "bald"]), "correct")
        self.assertEqual(label("I don't know", correct=["x"], original=["y"]), "unmatched")

    def test_matches_word_boundaries_and_reordering(self):
        self.assertTrue(matches("mother, his", ["his mother"]))  # reordering of a short reply
        self.assertFalse(matches("...so the hat just gets wet", ["a wet hat"]))
        self.assertFalse(matches("brown", ["brow"]))

    def test_extract_final_answer(self):
        self.assertEqual(extract_final_answer("thinking...\nAnswer: seven\n"), "seven")
        self.assertEqual(extract_final_answer("no answer line\nlast line"), "last line")


if __name__ == "__main__":
    unittest.main()
