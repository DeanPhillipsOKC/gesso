"""Tests for the #218 experiment (spike/experiments/v3_combined.py --stays, v3_stays.py): the requests and the
left-standing measure, no render."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))

import v3_combined as vc  # noqa: E402


def setup(picture: str, stays: bool):
    was = vc.STAYS
    vc.STAYS = stays
    try:
        d = vc.load(picture)
    finally:
        vc.STAYS = was
    return d, vc.units(d["painter"], vc.flats(d))


class StaysTests(unittest.TestCase):
    def test_a_behind_request_names_what_stays_and_reads_no_hand_written_sentence(self):
        d, us = setup("birch-grove", True)
        text = vc.prompt_for(d["painter"], us, 15, d["behind"])  # the fallen leaves, which took the rock in #214
        self.assertIn("All of this goes: The carpet of fallen leaves.", text)
        self.assertIn("stay exactly as they are, wherever they can be seen now: The misty sky and glow;", text)
        self.assertIn("the plain gray-green rock", text)
        self.assertNotIn("are not fallen leaves", text)  # #214's sentence by hand
        self.assertTrue(text.rstrip().endswith("No text, signature, or watermark."))
        self.assertEqual(d["painter"]["say"], {})

    def test_a_back_request_names_what_stays(self):
        d, us = setup("highland-cow", True)
        text = vc.prompt_for(d["painter"], us, 16, d["behind"])  # the tall grass, which redrew the bushes in #214
        self.assertIn("Nothing else in the painting is touched. These stay exactly as they are now:", text)
        self.assertIn("The dark bushes on the hillside", text)

    def test_without_the_switch_the_requests_are_as_they_were(self):
        d, us = setup("birch-grove", False)
        text = vc.prompt_for(d["painter"], us, 15, d["behind"])
        self.assertIn("are not fallen leaves: they stay exactly as they are.", text)  # #214's renders are checked
        self.assertNotIn("All of this goes", text)                                    # against these words
        self.assertNotIn("Nothing else in the painting is touched", vc.prompt_for(d["painter"], us, 16, d["behind"]))

    def test_a_thing_left_standing_beside_the_hole_is_measured(self):
        src = np.full((300, 400, 3), 200, np.uint8)
        src[100:200, 50:350] = (20, 60, 40)  # a dark band on a pale ground
        whole, half = src.copy(), src.copy()
        whole[100:200, 50:350] = 200
        half[100:200, 50:200] = 200  # the right half of the band stays
        frozen = np.zeros(src.shape[:2], bool)
        for raw, more in ((whole, False), (half, True)):
            D = vc.ws.diff_mask(src, raw, None, frozen)
            self.assertEqual(vc.left_standing(src, raw, D, frozen) >= vc.LEFT, more)

    def test_a_checker_is_told_what_goes_and_what_stays(self):
        d, us = setup("birch-grove", True)
        a = vc.asked(d, us, 8)
        self.assertTrue(a["goes"].startswith("all of: The yellow bushes along the path"))
        self.assertIn("The far misty firs", a["stays"])
        self.assertNotIn("The mossy rock", a["stays"])  # painted later
        self.assertTrue(vc.asked(d, us, 16)["goes"].startswith("only the last layer of paint on: The mossy rock"))


if __name__ == "__main__":
    unittest.main()
