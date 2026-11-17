"""Tests for spike S1 (#166, spike/experiments/v3_peel.py): the levels, the peel with its guard, the measures, and
step pictures built from the peeled layers (docs/spikes/v3-peel.md). A made-up scene and a stand-in for the image
model: no renders, no network, no model files."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import build_steps as bs  # noqa: E402
import v3_peel as vp  # noqa: E402

H, W = 120, 160
SKY, GROUND, RUG, CAT = (120, 160, 220), (60, 120, 60), (230, 170, 30), (90, 90, 95)


def scene() -> dict:
    """A sky over ground, a rug on the ground, a cat on the rug (it covers the rug's middle), and a post that
    touches neither."""
    finish = np.zeros((H, W, 3), np.uint8)
    owner = np.zeros((H, W), np.int32)
    finish[:] = SKY
    finish[70:], owner[70:] = GROUND, 1
    finish[60:100, 30:110], owner[60:100, 30:110] = RUG, 2
    finish[40:85, 50:90], owner[40:85, 50:90] = CAT, 3
    finish[20:110, 135:145], owner[20:110, 135:145] = (200, 60, 50), 4
    parts = [{"id": "sky", "name": "Sky", "kind": "area", "box": [0, 0, 1, 1]},
             {"id": "ground", "name": "Ground", "kind": "area", "box": [0, 0.55, 1, 1]},
             {"id": "rug", "name": "The rug", "kind": "object", "box": [0.17, 0.48, 0.71, 0.85]},
             {"id": "cat", "name": "The cat", "kind": "object", "box": [0.3, 0.32, 0.58, 0.72]},
             {"id": "post", "name": "The post", "kind": "object", "box": [0.83, 0.15, 0.92, 0.93]}]
    paints = [{"id": f"{p['id']}-1", "name": p["name"], "hex": "#%02x%02x%02x" % c, "parts": [p["id"]]}
              for p, c in zip(parts, [SKY, GROUND, RUG, CAT, (200, 60, 50)])]
    stages = [{"id": p["id"], "name": p["name"], "steps": [
        {"id": f"{p['id']}-all", "name": p["name"], "part": p["id"], "show": "full", "paints": [f"{p['id']}-1"]}]}
        for p in parts]
    plan = {"plan_version": 2, "parts": parts, "paints": paints, "stages": stages}
    return {"picture": "made-up", "run": Path("made-up_skill_1"), "finish": finish, "plan": plan, "owner": owner}


def truth(d: dict, gone: np.ndarray) -> np.ndarray:
    """What is really behind: the sky and ground, and the whole rug unless it's gone too."""
    out = np.zeros((H, W, 3), np.uint8)
    out[:] = SKY
    out[70:] = GROUND
    if not gone[60, 35]:
        out[60:100, 30:110] = RUG
    return np.where(gone[..., None], out, d["finish"])


class PeelTests(unittest.TestCase):
    def setUp(self):
        self.d = scene()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = []

        def fake(src: Path, prompt: str, out: Path, quality: str) -> dict:
            """The image model's stand-in: the true scene behind whatever the prompt names, a touch lighter
            everywhere (a render never comes back the same tone)."""
            self.calls.append(prompt)
            names = prompt.split("completely: ")[1].split(". Where")[0].split("; ")
            parts, owner = self.d["plan"]["parts"], self.d["owner"]
            now = np.array(Image.open(src).convert("RGB"))
            # gone: what the prompt names, and what an earlier render already took out of the picture it was given
            spot = {2: (95, 35), 3: (45, 55), 4: (25, 140)}
            taken = [k for k, p in enumerate(parts) if p["name"] in names
                   or (k in spot and (now[spot[k]] != self.d["finish"][spot[k]]).any())]
            gone = np.isin(owner, taken)
            if 2 in taken:
                gone[60:100, 30:110] = True  # the rug's place under the cat goes with the rug
            got = np.where(gone[..., None], truth(self.d, gone), now)
            Image.fromarray(np.clip(got.astype(int) + 3, 0, 255).astype(np.uint8)).save(out)
            return {"seconds": 1.0, "cost_usd": 0.01}

        for patch in (mock.patch.object(vp, "OUT", Path(self.tmp.name)),
                      mock.patch.object(vp, "load", lambda picture, runs=None: self.d),
                      mock.patch.dict(vp.RENDERERS, {"gpt-image": fake})):
            patch.start()
            self.addCleanup(patch.stop)

    def test_levels(self):
        parts, owner = self.d["plan"]["parts"], self.d["owner"]
        self.assertEqual(vp.levels(parts, owner).tolist(), [0, 0, 1, 2, 1])  # the post touches nothing in front
        self.assertEqual(vp.levels(parts, owner, deep=True).tolist(), [0, 1, 2, 3, 2])

    def test_parallel_peel_keeps_everything_outside_the_hole(self):
        r = vp.peel("made-up", "parallel", "low")
        self.assertEqual((r["levels"], r["renders"], r["stack_gap"]), (2, 2, 0.0))
        folder = Path(self.tmp.name) / "parallel-low" / "made-up"
        finish, owner = self.d["finish"], self.d["owner"]
        p1 = np.array(Image.open(folder / "P1.png"))
        p0 = np.array(Image.open(folder / "P0.png"))
        away = ~bs.halo(owner == 3)
        self.assertTrue((p1[away] == finish[away]).all())  # the guard: the lighter render changed nothing else
        self.assertLess(np.abs(p1[62:68, 55:85].astype(int) - RUG).max(), 12)  # the rug is whole under the cat
        self.assertLess(np.abs(p0[75:95, 40:100].astype(int) - GROUND).max(), 12)  # and gone a level down
        for row in r["rows"]:
            self.assertEqual(row["render_problems"], [])
            self.assertLess(row["edge"], 0.1)
        self.assertEqual(len(self.calls), 2)
        vp.peel("made-up", "parallel", "low")  # a second run reads the renders from the folder
        self.assertEqual(len(self.calls), 2)

    def test_chained_peel_clears_what_the_last_render_painted(self):
        vp.peel("made-up", "chained", "low")
        p0 = np.array(Image.open(Path(self.tmp.name) / "chained-low" / "made-up" / "P0.png"))
        # the rug under the cat came from the first render and has no outline: it must go with the rug
        self.assertLess(np.abs(p0[62:68, 55:85].astype(int) - SKY).max(), 12)
        self.assertIn("The rug; The post", self.calls[1])
        self.assertNotIn("The cat", self.calls[1].split("Where")[0])

    def test_a_render_that_removes_nothing_is_reported(self):
        def lazy(src, prompt, out, quality):
            Image.open(src).save(out)
            return {"seconds": 1.0, "cost_usd": 0.01}

        with mock.patch.dict(vp.RENDERERS, {"gpt-image": lazy}):
            r = vp.peel("made-up", "parallel", "low")
        self.assertTrue(all(row["render_problems"] for row in r["rows"]))
        self.assertGreater(max(row["edge"] for row in r["rows"]), 0.9)

    def test_steps_from_the_layers(self):
        vp.peel("made-up", "parallel", "low")
        d, folder = self.d, Path(self.tmp.name) / "parallel-low" / "made-up"
        level = vp.levels(d["plan"]["parts"], d["owner"])
        P = {0: np.array(Image.open(folder / "P0.png")), 1: np.array(Image.open(folder / "P1.png")), 2: d["finish"]}
        whole_rug = np.zeros((H, W), bool)
        whole_rug[60:100, 30:110] = True
        given = {"ground": np.arange(H)[:, None] >= 70 + np.zeros(W, int), "rug": whole_rug, "post": d["owner"] == 4, "cat": d["owner"] == 3}
        own = vp.owners(d, P, level, given=given)
        self.assertTrue((own[1][62:68, 55:85] == 2).all())  # the rug owns its place under the cat
        self.assertTrue((own[0][75:95, 40:100] == 1).all())  # and the ground its place under the rug
        pictures, rows, _ = vp.build(d, P, level, own)
        self.assertEqual(len(pictures), 5)
        self.assertLess(np.abs(pictures[1][75:95, 40:100].astype(int) - GROUND).max(), 12)  # ground, no rug-shaped hole
        self.assertLess(np.abs(pictures[2][62:68, 55:85].astype(int) - RUG).max(), 12)  # a whole rug before the cat
        self.assertTrue((pictures[-1] == d["finish"]).all())
        self.assertLess(rows[-1]["final_gap"], 0.01)
        self.assertEqual(max(r["outside"] for r in rows), 0.0)

    def test_measures(self):
        finish, gone = self.d["finish"], self.d["owner"] == 3
        self.assertEqual(vp.edge_left(finish, truth(self.d, gone), gone)["edge"], 0.0)
        self.assertGreater(vp.edge_left(finish, finish, gone)["edge"], 0.9)
        self.assertEqual(vp.moved(finish, finish, ~gone), 0.0)
        self.assertGreater(vp.moved(finish, truth(self.d, gone), gone), 0.9)

    def test_results(self):
        vp.peel("made-up", "parallel", "low")
        got = vp.results()
        self.assertEqual(list(got), ["parallel-low"])
        self.assertEqual(got["parallel-low"][0]["renders"], 2)
        json.dumps(got)


if __name__ == "__main__":
    unittest.main()
