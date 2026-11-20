"""The cover-margin spike's step pictures (#289, `spike/experiments/cover_margin.py`) on a small made-up scene: a
textured sky with a cloud, a flat hill with its shading, a textured meadow, a rock on the hill and a thin trunk."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))

import cover_margin as cm  # noqa: E402
import from_finish as ff  # noqa: E402

H, W, PPI = 160, 96, 8.0  # a 12 x 20 in canvas, 8 pixels an inch
CANVAS = np.array(ff.CANVAS, np.float32)


def box(y0, y1, x0, x1) -> np.ndarray:
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


def textured(color, amount, seed) -> np.ndarray:
    import cv2
    rng = np.random.default_rng(seed)
    n = cv2.GaussianBlur(rng.standard_normal((H, W)).astype(np.float32), (0, 0), 1.5)
    n = n / (n.std() + 1e-6) * amount
    return np.clip(np.array(color, np.float32)[None, None] + n[..., None], 0, 255)


# unit: (id, stage, things, where it lays, its paint's picture, its paint, kind)
SKY = box(0, H, 0, W)
CLOUD = box(10, 40, 30, 80)
HILL = box(70, H, 0, W)
SHADE = box(70, H, 0, W)  # a later stage of the hill, laid over all of it
ROCK = box(85, 115, 30, 70)  # an island on the hill, clear of the meadow
MEADOW = box(130, H, 0, W)  # runs to the bottom edge
TRUNK = box(20, 140, 10, 13)  # 3 pixels wide: thinner than any margin
UNITS = [
    ("sky", "s1", ["sky"], SKY, textured((120, 160, 220), 25, 1), "Sky blue", "first"),
    ("cloud", "s1", ["cloud"], CLOUD, textured((240, 240, 245), 20, 2), "Cloud white", "behind"),
    ("hill", "s2", ["hill"], HILL, textured((90, 110, 160), 0.3, 3), "Hill blue", "behind"),
    ("rock", "s3", ["rock"], ROCK, textured((120, 110, 100), 20, 4), "Rock gray", "behind"),
    ("meadow", "s3", ["meadow"], MEADOW, textured((110, 150, 60), 25, 5), "Meadow green", "behind"),
    ("trunk", "s3", ["trunk"], TRUNK, textured((240, 240, 230), 5, 6), "Trunk white", "behind"),
    ("shade", "s4", ["hill"], SHADE, None, "Hill blue", "back"),
]


def scene() -> dict:
    us, steps, P, m = [], [], [], []
    owner = np.zeros((H, W), np.uint8)
    pic = np.empty((H, W, 3), np.float32)
    pic[:] = CANVAS
    hexes = {}
    for n, (uid, stage, things, where, paint, name, kind) in enumerate(UNITS):
        if paint is None:  # the hill's shading: the hill's own picture, a little darker on its left
            paint = pic.copy()
            paint[:, : W // 2] *= 0.9
            where = where & ~ROCK & ~MEADOW & ~TRUNK
        pic = np.where(where[..., None], paint, pic)
        P.append(np.clip(pic, 0, 255).astype(np.uint8))
        m.append(where)
        owner[where] = n
        us.append({"stage": stage, "things": things, "steps": [n], "kind": kind, "id": uid, "name": uid})
        steps.append({"id": f"paint-{uid}", "paints": [name]})
        c = paint[where].mean(0)
        hexes.setdefault(name, "#%02x%02x%02x" % tuple(int(x) for x in c))
    plan = {"stages": [{"id": s} for s in ("s1", "s2", "s3", "s4")]}
    return {"picture": "scene", "plan": plan, "units": us, "steps": steps, "P": P, "m": m, "owner_png": owner,
            "ppi": PPI, "crop": (0, H, 0, W), "canvas_in": (W / PPI, H / PPI), "hexes": hexes}


class CoverMapTests(unittest.TestCase):
    def setUp(self):
        self.L = scene()
        self.cov = cm.covered(self.L)

    def test_a_later_thing_covers_what_is_on_top(self):
        sky = self.cov[0]
        self.assertTrue(sky[100, 5])  # the sky under the hill
        self.assertTrue(sky[20, 50])  # and under the cloud
        self.assertFalse(sky[5, 5])  # the sky that stays sky

    def test_a_later_stage_of_the_same_thing_is_not_a_cover(self):
        hill = self.cov[2]  # after the hill: its shading owns most of it at the finish, and doesn't cover it
        self.assertFalse(hill[80, 5])
        self.assertTrue(hill[100, 50])  # the rock does

    def test_nothing_is_covered_after_the_last_unit(self):
        self.assertFalse(self.cov[-1].any())

    def test_detail(self):
        d = {r["id"]: r for r in cm.layer_detail(self.L, self.cov)}
        self.assertTrue(d["sky"]["detail"])
        self.assertFalse(d["hill"]["detail"])  # one flat coat: painted straight through


class VariantTests(unittest.TestCase):
    def setUp(self):
        self.L = scene()
        self.base = cm.baseline(self.L)

    def test_the_baseline_is_the_chain(self):
        for n, u in enumerate(self.L["units"]):
            gap = np.abs(self.base[u["steps"][-1]].astype(int) - self.L["P"][n].astype(int)).max()
            self.assertLessEqual(gap, 1)

    def test_every_variant_keeps_build_steps_checks(self):
        """The last picture is the finish, and no step changes a pixel outside where its unit lays paint."""
        for v in cm.VARIANTS:
            with self.subTest(v):
                r = cm.variant_steps(self.L, v, self.base)
                c = cm.checks(self.L, self.base, r["pictures"])
                self.assertEqual(c["final_gap"], 0.0)
                self.assertEqual(c["outside_unit_max"], 0.0)

    def test_a_thin_cover_is_painted_through(self):
        for margin in cm.MARGINS:
            r = cm.variant_steps(self.L, f"canvas-{margin:g}-all", self.base)
            self.assertLess(r["hidden"][0][60, 11], 0.01, margin)  # the sky under the trunk

    def test_the_margin_stays_painted(self):
        r = cm.variant_steps(self.L, "canvas-1-all", self.base)
        h = r["hidden"][0]
        self.assertLess(h[72, 48], 0.01)  # 2 px inside where the hill will go: well inside the margin
        self.assertGreater(h[115, 85], 0.99)  # 6 in below the hill's top and clear of the rock: hidden

    def test_fills(self):
        for fill, want in (("canvas", "bare"), ("wash", "flat")):
            r = cm.variant_steps(self.L, f"{fill}-0.5-all", self.base)
            px = r["pictures"][0][120, 85].astype(np.float32)
            if want == "bare":
                self.assertLess(np.abs(px - CANVAS).max(), 2)
            else:
                self.assertGreater(np.abs(px - CANVAS).max(), 30)

    def test_edge_fill(self):
        """Bare canvas where the hidden area runs out to the edge (the sky below the hill line), a wash where it is
        an island inside its layer (the hill under the rock)."""
        r = cm.variant_steps(self.L, "edge-0.5-all", self.base)
        sky_low = r["pictures"][0][120, 85].astype(np.float32)
        self.assertLess(np.abs(sky_low - CANVAS).max(), 2)
        hill_under_rock = r["pictures"][2][100, 50].astype(np.float32)
        self.assertGreater(np.abs(hill_under_rock - CANVAS).max(), 30)
        self.assertTrue(r["hidden"][2][100, 50] > 0.99)

    def test_detail_paints_a_flat_layer_through(self):
        r = cm.variant_steps(self.L, "edge-0.5-detail", self.base)
        self.assertLess(r["hidden"][2][100, 50], 0.01)  # the flat hill under the rock
        self.assertGreater(r["hidden"][0][120, 85], 0.99)  # the textured sky under the hill

    def test_staged_drops_a_cover_of_the_same_stage(self):
        detail = cm.variant_steps(self.L, "edge-0.5-detail", self.base)
        staged = cm.variant_steps(self.L, "edge-0.5-staged", self.base)
        self.assertGreater(detail["hidden"][0][25, 55], 0.99)  # the sky under the cloud
        self.assertLess(staged["hidden"][0][25, 55], 0.01)
        self.assertGreater(staged["hidden"][0][120, 85], 0.99)  # the hill is a later stage

    def test_spared(self):
        r = cm.variant_steps(self.L, "canvas-0.5-all", self.base)
        sp = cm.spared(self.L, self.base, r["hidden"])
        self.assertGreater(sp[0]["spared"], 0.3)
        self.assertEqual(sp[-1]["spared"], 0.0)


if __name__ == "__main__":
    unittest.main()
