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
    return d, fw.units(d["painter"])


class CombinedTests(unittest.TestCase):
    def test_kinds_follow_the_plan(self):
        d, us = cow()
        kinds = [vc.kind_of(us, n, d["behind"]) for n in range(len(us))]
        assert len(us) == 11
        # the loch and the ground have nothing behind them; the coat, the face and the tall grass come back to a thing
        assert kinds[3] == kinds[4] == "bare"
        assert kinds[8] == kinds[9] == kinds[10] == "back"
        assert kinds[1] == kinds[5] == kinds[6] == kinds[7] == "behind"

    def test_state_drops_what_is_not_there_yet(self):
        line = "The whole bottom half is covered in green. It is smooth, with no bushes, blades or cow yet."
        assert vc._state(line) == "The whole bottom half is covered in green."

    def test_requests_name_what_is_behind_and_never_ask_for_the_cow_to_go_with_the_grass(self):
        d, us = cow()
        grass = vc.prompt_for(d["painter"], us, 10, d["behind"])
        assert "Take it back one stage" in grass and "cow yet" not in grass
        cow_shape = vc.prompt_for(d["painter"], us, 6, d["behind"])
        assert "Behind them there is only this" in cow_shape and "the plain green meadow" in cow_shape
        assert "leave bare" in vc.prompt_for(d["painter"], us, 4, d["behind"])
        assert "smooth, flat and softly blended" in vc.prompt_for(d["painter"], us, 10, d["behind"], 2)
        assert "smooth, flat and softly blended" not in vc.prompt_for(d["painter"], us, 10, d["behind"], 1)

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
