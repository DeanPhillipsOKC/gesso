"""The student test (#174, v4's yardstick): near misses, worsened words, the measure and the report. No network."""

from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))

import v4_student as vs  # noqa: E402


def scene(box=None, colour=(200, 60, 40), size=(300, 225)):
    """A pale canvas with a blue band at the top and, if `box`, a block of paint."""
    im = Image.new("RGB", size, (240, 238, 230))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, size[0], 40], fill=(90, 140, 210))
    if box:
        d.rectangle(box, fill=colour)
    return im


class Words(unittest.TestCase):
    def test_swap_sides_mirrors_every_side_and_keeps_case(self):
        s = "Its left side is 2 in from the left edge; the top is at the Top edge, upper left, below the sill."
        self.assertEqual(vs.swap_sides(s),
                         "Its right side is 2 in from the right edge; the bottom is at the Bottom edge, lower right, "
                         "above the sill.")

    def test_swap_sides_leaves_other_words(self):
        self.assertEqual(vs.swap_sides("Leftover paint, topping, brightness."), "Leftover paint, topping, brightness.")

    def test_step_text_header_only_has_no_words(self):
        s = {"n": 3, "name": "Paint the barn", "group": "Barn", "brushes": "1 inch flat", "tip": "Go slow.",
             "lines": ["Inside the outlined area.", "Stroke side to side."],
             "paints": [{"name": "Barn red", "hex": "#aa2211", "recipe": "2 parts red, 1 part burnt sienna"}]}
        full = vs.step_text(s, [16, 12], 20)
        head = vs.step_text(s, [16, 12], 20, header_only=True)
        self.assertIn("1. Inside the outlined area.", full)
        self.assertIn("Tip: Go slow.", full)
        self.assertIn("Barn red (#aa2211)", head)
        self.assertNotIn("Stroke", head)
        self.assertNotIn("Tip", head)
        self.assertIn("16 in wide and 12 in tall", head)
        other = vs.step_text(s, [16, 12], 20, words={"lines": ["Paint it."], "tip": ""})
        self.assertIn("1. Paint it.", other)
        self.assertNotIn("Tip", other)


class NearMisses(unittest.TestCase):
    def test_change_mask_finds_the_block(self):
        m = vs.change_mask(scene(), scene((30, 120, 110, 200)), side=120)
        ys, xs = np.nonzero(m)
        self.assertGreater(m.mean(), 0.05)
        self.assertLess(xs.max(), 60)  # left part of a 120-pixel-wide mask
        self.assertGreater(ys.min(), 40)  # the block starts 120 px down a 225 px canvas

    def test_moved_puts_the_change_on_the_other_side(self):
        b, a = scene(), scene((30, 120, 110, 200))
        m = vs.change_mask(b, a)
        top, mm, how = vs.moved(b, a, m)
        self.assertEqual(how, "mirrored side to side")
        self.assertLess(vs.iou(m, mm), 0.1)

    def test_moved_flips_a_change_that_mirrors_onto_itself(self):
        b, a = scene(), scene((100, 150, 200, 215))  # centred: the side-to-side mirror is the same block
        top, mm, how = vs.moved(b, a, vs.change_mask(b, a))
        self.assertEqual(how, "mirrored top to bottom")

    def test_half_keeps_about_half(self):
        m = vs.change_mask(scene(), scene((30, 120, 270, 200)))
        h = vs.half_of(m, random.Random(1))
        self.assertAlmostEqual(h.sum() / m.sum(), 0.5, delta=0.1)
        self.assertTrue(np.all(h <= m))

    def test_lay_changes_only_inside_the_mask(self):
        b, a = scene(), scene((30, 120, 110, 200))
        out = np.asarray(vs.lay(b, a, vs.change_mask(b, a)), dtype=float)
        self.assertLess(np.abs(out[60:110, 20:120] - np.asarray(a, dtype=float)[60:110, 20:120]).mean(), 3)
        self.assertLess(np.abs(out[150:, 200:] - np.asarray(b, dtype=float)[150:, 200:]).mean(), 1)

    def test_candidates_on_a_bench_step(self):
        cands, info = vs.candidates("sleeping-cat", 14, 21)
        self.assertEqual(set(cands), set(vs.KINDS))
        self.assertEqual(info["other_step"], 15)
        sizes = {c.size for c in cands.values()}
        self.assertEqual(len(sizes), 1)
        self.assertGreater(info["area"], 0.05)


class Measure(unittest.TestCase):
    def setUp(self):
        self.b = scene()
        self.real = scene((30, 120, 110, 200))
        self.misses = {"place": scene((190, 120, 270, 200)), "half": scene((30, 120, 70, 200)),
                       "other": scene((120, 60, 180, 100), colour=(30, 120, 40))}

    def test_the_real_after_beats_everything(self):
        m = vs.measure(self.b, self.real, self.real.copy(), self.misses)
        self.assertEqual(m["beats"], 1.0)
        self.assertGreater(m["toward"], 0.9)
        self.assertGreater(m["where"], 0.9)

    def test_doing_nothing_beats_nothing(self):
        m = vs.measure(self.b, self.real, self.b.copy(), self.misses)
        self.assertLessEqual(m["beats"], 0.25)
        self.assertLessEqual(m["toward"], 0.01)

    def test_the_wrong_place_loses(self):
        m = vs.measure(self.b, self.real, self.misses["place"].copy(), self.misses)
        self.assertLess(m["beats"], 1.0)

    def test_a_colour_shift_everywhere_is_forgiven(self):
        shifted = Image.fromarray(np.clip(np.asarray(self.real, dtype=int) * 0.92 + 12, 0, 255).astype(np.uint8))
        self.assertEqual(vs.measure(self.b, self.real, shifted, self.misses)["beats"], 1.0)


class Results(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.saved = (vs.RESULTS, vs.WORK, vs._STATE)
        vs.RESULTS, vs.WORK, vs._STATE = self.tmp / "r.json", self.tmp / "work", None
        vs._NEW.clear()

    def tearDown(self):
        vs.RESULTS, vs.WORK, vs._STATE = self.saved
        vs._NEW.clear()

    def test_save_keeps_records_another_process_wrote(self):
        vs.add("pick", {"a": 1})
        disk = json.loads(vs.RESULTS.read_text())
        disk["pick"].append({"b": 2})  # another command's record, written meanwhile
        disk["prepared"]["cow"] = {"1": {"area": 0.5}}
        vs.RESULTS.write_text(json.dumps(disk))
        vs.add("pick", {"c": 3})
        got = json.loads(vs.RESULTS.read_text())
        self.assertEqual(got["pick"], [{"a": 1}, {"b": 2}, {"c": 3}])
        self.assertEqual(got["prepared"]["cow"]["1"]["area"], 0.5)

    def test_report_on_made_up_answers(self):
        st = vs.state()
        rows = []
        for pic in vs.PICTURES:
            for n in range(1, 7):
                rows.append({"picture": pic, "n": n, "condition": "words", "rep": 1, "p_real": n / 6,
                             "hit": n > 2, "pick": "real" if n > 2 else "half", "probs": {}})
                rows.append({"picture": pic, "n": n, "condition": "header", "rep": 1, "p_real": 0.25,
                             "hit": False, "pick": "place", "probs": {}})
            st["graders"].append({"picture": pic, "grader": 1, "real": 3, "paintable": 3, "agree": 3,
                                  "worst_steps": [1, 2], "steps": {str(n): n for n in range(1, 7)}})
        st["pick"] = rows
        out = vs.report(None)
        p = out["pick"]
        self.assertEqual(p["words"]["n"], 18)
        self.assertEqual(p["agree_with_graders"]["spearman"], 1.0)
        self.assertEqual(p["agree_with_graders"]["in_lowest_third"], 6)
        self.assertEqual(p["agree_with_graders"]["of"], 6)
        self.assertLess(p["vs_words"]["header"]["change"], 0)

    def test_spearman(self):
        self.assertEqual(vs.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertEqual(vs.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertIsNone(vs.spearman([1, 1, 1], [1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
