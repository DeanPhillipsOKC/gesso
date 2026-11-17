"""Tests for the #210 experiment (spike/experiments/v3_combined.py): the requests and the shapes, no render."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))

import v3_combined as vc  # noqa: E402
import v4_forward as fw  # noqa: E402


def cow():
    d = vc.load("highland-cow")
    return d, vc.units(d["painter"], vc.flats(d))


class CombinedTests(unittest.TestCase):
    def test_units_cut_a_block_in_and_a_shared_paint_into_their_own(self):
        d, us = cow()
        steps = [[i + 1 for i in u["steps"]] for u in us]
        self.assertEqual(len(fw.units(d["painter"])), 11)
        self.assertEqual(len(us), 17)
        self.assertIn([9], steps)  # the cow's block-in, apart from its shade
        self.assertIn([10], steps)
        self.assertIn([17, 18], steps)  # the nose's light and the nostrils: two paints, one render
        self.assertIn([19], steps)  # the mouth line: Dark umber again, so its own render
        self.assertIn([20, 21, 22, 23, 24], steps)

    def test_kinds_follow_the_plan(self):
        d, us = cow()
        kind = {tuple(i + 1 for i in u["steps"]): vc.kind_of(us, n, d["behind"]) for n, u in enumerate(us)}
        self.assertEqual(kind[(5,)], "bare")
        self.assertEqual(kind[(6,)], "bare")
        for k in ((2,), (7,), (9,), (11,)):
            self.assertEqual(kind[k], "behind")
        for k in ((3,), (10,), (13, 14, 15), (19,), (20, 21, 22, 23, 24)):
            self.assertEqual(kind[k], "back")

    def test_the_extras_of_a_picture_change_its_requests_and_units(self):
        # #214: the sleeping cat and the birch grove
        d = vc.load("birch-grove")
        us = vc.units(d["painter"], vc.flats(d))
        steps = [[i + 1 for i in u["steps"]] for u in us]
        self.assertIn([17, 18, 19], steps)  # the dark leaf dabs are no block-in (`not_flat`): one render for all three
        self.assertEqual(vc.shows(d)["dab-dark-floor-leaves"], "pass")
        at = {u["steps"][0] + 1: n for n, u in enumerate(us)}
        leaves = vc.prompt_for(d["painter"], us, at[17], d["behind"])
        self.assertIn("The mossy rock right of the path", leaves)  # `say`
        self.assertIn("the plain light sandy path", leaves)  # `called`
        self.assertNotIn("smooth, flat and softly blended", leaves)
        d = vc.load("sleeping-cat")
        us = vc.units(d["painter"], vc.flats(d))
        self.assertEqual(len(us), 15)
        trees = vc.prompt_for(d["painter"], us, 1, d["behind"])
        self.assertIn("Behind them there is only this: the pale sky through the window.", trees)

    def test_results_holds_a_picture_each(self):
        import json

        kept = json.loads((vc.HERE / "v3_combined.json").read_text())["pictures"]
        self.assertEqual(sorted(kept), ["birch-grove", "highland-cow", "sleeping-cat"])
        for r in kept.values():
            self.assertEqual(r["checks"]["final_gap"], 0.0)

    def test_state_drops_what_is_not_there_yet(self):
        line = "The whole bottom half is covered in green. It is smooth, with no bushes, blades or cow yet."
        self.assertEqual(vc._state(line), "The whole bottom half is covered in green.")

    def test_requests_name_what_is_behind_and_never_ask_for_the_cow_to_go_with_the_grass(self):
        d, us = cow()
        at = {u["steps"][0] + 1: n for n, u in enumerate(us)}
        ask = lambda step, again=0: vc.prompt_for(d["painter"], us, at[step], d["behind"], again)  # noqa: E731
        self.assertIn("Take it back one stage", ask(20))
        self.assertNotIn("cow yet", ask(20))
        self.assertIn("Behind them there is only this", ask(9))
        self.assertIn("the plain green meadow", ask(9))
        self.assertIn("leave bare", ask(6))
        smooth = "smooth, flat and softly blended"
        self.assertIn(smooth, ask(20, 2))
        self.assertNotIn(smooth, ask(20, 1))
        self.assertIn(smooth, ask(10))  # what is left under the cow's shade is its block-in
        self.assertNotIn(smooth, ask(13))

    def test_owner_is_the_last_core_then_the_last_change_then_the_nearest(self):
        D0, D1 = np.zeros((4, 6), bool), np.zeros((4, 6), bool)
        D0[:, :3] = True
        D1[:, 2:5] = True
        core1 = np.zeros((4, 6), bool)
        core1[:, 3:5] = True
        owner = vc.owner_from([{"D": D0, "core": D0}, {"D": D1, "core": core1}])
        assert (owner[:, :3] == 0).all() and (owner[:, 3:5] == 1).all()
        assert (owner[:, 5] == 1).all()  # no unit changed it: the nearest pixel that has one

    def test_erase_one_keeps_everything_outside_the_change(self):
        src = np.full((80, 80, 3), 120, np.uint8)
        raw = src.copy()
        raw[20:50, 20:50] = (250, 250, 250)
        raw[70:, 70:] += 3  # drift too small to count
        out, D = vc.erase_one(src, raw, True, np.zeros((80, 80), bool))
        assert D[30, 30] and not D[75, 75]
        assert (out[~D] == src[~D]).all()


if __name__ == "__main__":
    unittest.main()
