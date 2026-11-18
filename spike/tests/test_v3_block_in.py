"""Tests for the #217 experiment (spike/experiments/v3_block_in.py): the requests and the masks, no render."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))

import v3_block_in as vb  # noqa: E402


class BlockInTests(unittest.TestCase):
    def test_a_block_in_request_names_its_paint_and_what_is_not_painted_yet(self):
        d, us, steps = vb.setup("sleeping-cat")
        for way in (1, 2):
            text = vb.request(d, us, steps, 7, way)
            self.assertIn("Golden yellow (a rich warm mustard yellow", text)
            self.assertIn("None of this is painted yet, so none of it may show: deep ochre", text)
            self.assertIn("rows of small slanted comma pairs", text)  # the stitches, two units later
            self.assertTrue(text.rstrip().endswith("No text, signature, or watermark."))
        self.assertIn("Take it back one stage", vb.request(d, us, steps, 7, 1))  # way 1 is unit 8's own request
        self.assertIn("painted too far for this stage: the plain yellow blanket", vb.request(d, us, steps, 7, 2))

    def test_a_later_stage_lists_only_what_comes_from_it_on(self):
        d, us, steps = vb.setup("sleeping-cat")
        text = vb.not_yet(us, steps, 13)  # the cat's fur flicks: the stripes before them are painted
        self.assertIn("short light flicks of silver gray", text)
        self.assertIn("thin white whiskers", text)
        self.assertNotIn("bold dark stripes", text)

    def test_stages_are_the_units_that_come_back_to_the_thing(self):
        d, us, _ = vb.setup("sleeping-cat")
        self.assertEqual(vb.stages(us, d, 7), [8, 9])
        self.assertEqual(vb.stages(us, d, 10), [11, 12, 13, 14])
        d, us, _ = vb.setup("highland-cow")
        self.assertEqual(vb.stages(us, d, 8), [9])  # the horns' units come next
        self.assertEqual(vb.stages(us, d, 8, far=True), [9, 10, 11, 12, 13, 14, 15])

    def test_solid_fills_holes_and_closes_narrow_gaps(self):
        m = np.zeros((80, 80), bool)
        m[10:70, 10:70] = True
        m[30:50, 30:50] = False  # a hole
        m[10:70, 38:42] = False  # a narrow gap through it
        s = vb.solid(m)
        self.assertTrue(s[40, 40])
        self.assertTrue(s[15, 40])
        self.assertFalse(s[2, 2])


if __name__ == "__main__":
    unittest.main()
