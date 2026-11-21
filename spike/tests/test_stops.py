"""Pipeline v4's first build step (#295; docs/design/pipeline-v4.md, sections 2, 5 and 13): a covered layer stops at
its loose line (spike/stops.py), in build-steps behind --stops.

On a made-up scene (as test_v3_cover_margin's): a sky covered from the bottom edge by a hill of the next stage
stops about 1 in past the hill's top; a cover in the sky's own stage, one two stages on, a thin one, an island and
one shorter than 1 1/2 in each stop nothing; build-steps' checks 1 and 2 hold; and a unit that comes back to the sky
doesn't uncover the canvas the sky left bare. Then the tool on test_steps3's scene and the fixture lessons, and
(slow) the three bench chains against the spike's own `line-1-next` pictures and the design's section 3 table."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))

import build_steps as bs  # noqa: E402
import from_finish as ff  # noqa: E402
import lesson3  # noqa: E402
import lessons  # noqa: E402
import stops  # noqa: E402
import tools  # noqa: E402

H, W, PPI = 160, 96, 8.0  # a 12 x 20 in canvas, 8 pixels an inch
FR = {"crop": (0, H, 0, W), "ppi": PPI, "canvas_in": (W / PPI, H / PPI)}
CANVAS = np.array(ff.CANVAS, np.float32)
HILL_TOP = 70  # the hill's top, 8 3/4 in down


def box(y0, y1, x0, x1) -> np.ndarray:
    m = np.zeros((H, W), bool)
    m[y0:y1, x0:x1] = True
    return m


def flat(color) -> np.ndarray:
    rng = np.random.default_rng(sum(color))
    noise = rng.normal(0, 6, (H, W, 1)).astype(np.float32)
    return np.clip(np.array(color, np.float32)[None, None] + noise, 0, 255)


SKY = ("sky", ["sky"], box(0, H, 0, W), (120, 160, 220), "first")
HILL = ("hill", ["hill"], box(HILL_TOP, H, 0, W), (90, 110, 160), "behind")


def scene(units: list[tuple], stages: list[str]) -> dict:
    """units: (id, stage, things, where it lays, its color, kind). Each unit's picture P is the one before with its
    color laid where it lays; its step pictures are laid as steps3.build lays them."""
    us, steps, masks, P, owner = [], [], [], [], np.zeros((H, W), np.int32)
    pic = np.empty((H, W, 3), np.float32)
    pic[:] = CANVAS
    for n, (uid, stage, things, where, color, kind) in enumerate(units):
        pic = np.where(where[..., None], flat(color), pic)
        P.append(np.clip(pic, 0, 255).astype(np.uint8))
        masks.append(where)
        owner[where] = n
        us.append({"id": uid, "name": uid, "stage": stage, "things": things, "steps": [n], "kind": kind})
        steps.append({"id": f"paint-{uid}"})
    canvas = np.empty((H, W, 3), np.float32)
    canvas[:] = CANVAS
    base = []
    for n in range(len(us)):
        canvas = bs._lay(canvas, P[n], masks[n])
        base.append(np.clip(canvas, 0, 255).astype(np.uint8))
    return {"plan": {"stages": [{"id": s} for s in stages]}, "us": us, "masks": masks, "P": P, "owner": owner,
            "base": base}


def run(sc: dict) -> dict:
    worked = stops.work_out(sc["plan"], sc["us"], sc["masks"], sc["owner"], FR)
    laid = stops.lay(sc["base"], sc["masks"], sc["us"], worked["want"])
    return {**laid, "worked": worked, "said": stops.report(sc["plan"], sc["us"], sc["masks"], worked, laid, FR)}


def bare(px) -> bool:
    return float(np.abs(px.astype(np.float32) - CANVAS).max()) < 2


class TheRuleTests(unittest.TestCase):
    def two(self, hill=HILL, stages=("s1", "s2"), hill_stage="s2", more=()) -> dict:
        sky = (SKY[0], "s1", *SKY[1:])
        h = (hill[0], hill_stage, *hill[1:])
        return run(scene([sky, h, *more], list(stages)))

    def stopped(self, r: dict) -> bool:
        return r["hidden"][0].max() > stops.HIDDEN

    def test_a_band_covered_from_the_bottom_by_the_next_stage_stops_about_1_in_past_its_top(self):
        r = self.two()
        self.assertTrue(bare(r["pictures"][0][140, 50]))  # well under the hill's top: bare canvas
        self.assertFalse(bare(r["pictures"][0][HILL_TOP + 2, 50]))  # just under it: the sky is painted on
        row, = r["said"]["stops"]["stopped"]
        self.assertEqual((row["id"], row["steps"]), ("sky", [1]))
        self.assertEqual(row["covered_by"], {"unit": 1, "id": "hill", "step": 2})
        line = row["line"]
        self.assertAlmostEqual(line["past_cover"]["most"], 1.0, delta=0.3)
        self.assertAlmostEqual(line["most"], HILL_TOP / PPI + 1.0, delta=0.3)
        self.assertTrue(line["highest"] <= line["most"] <= line["lowest"])
        self.assertGreater(line["highest"], HILL_TOP / PPI + 0.5)
        self.assertIsNotNone(line["left"])
        self.assertGreater(r["said"]["spared"][0]["spared"], 0.3)
        self.assertEqual(r["said"]["spared"][1]["spared"], 0.0)
        self.assertAlmostEqual(r["said"]["spared_canvas"], r["said"]["spared"][0]["spared_canvas"], places=3)
        self.assertEqual(r["said"]["notes"], [])
        self.assertEqual(r["said"]["stops"]["rule"], "line-1-next")
        self.assertEqual(r["said"]["stops"]["numbers"]["margin_in"], 1.0)

    def test_covers_that_stop_nothing(self):
        cases = {
            "in the layer's own stage": dict(hill_stage="s1", stages=("s1",)),
            "two stages on": dict(stages=("s1", "between", "s2")),
            "thin": dict(hill=("trunk", ["trunk"], box(40, H, 40, 43), (240, 240, 230), "behind")),
            "an island": dict(hill=("rock", ["rock"], box(60, 130, 20, 70), (120, 110, 100), "behind")),
            "shorter than 1 1/2 in": dict(hill=("strip", ["strip"], box(H - 10, H, 0, W), (110, 150, 60), "behind")),
        }
        for what, kw in cases.items():
            with self.subTest(what):
                r = self.two(**kw)
                self.assertFalse(self.stopped(r))
                self.assertEqual(r["said"]["stops"]["stopped"], [])
                hill = kw.get("hill", HILL)
                sc = scene([(SKY[0], "s1", *SKY[1:]), (hill[0], kw.get("hill_stage", "s2"), *hill[1:])],
                           list(kw.get("stages", ("s1", "s2"))))
                self.assertTrue(all(np.array_equal(a, b) for a, b in zip(r["pictures"], sc["base"])))
        why = {w: self.two(**cases[w])["said"]["stops"]["not_stopped"]
               for w in ("in the layer's own stage", "two stages on")}
        self.assertEqual(why["in the layer's own stage"][0]["why"], "the cover is in its own stage")
        self.assertEqual(why["two stages on"][0]["why"], "the cover is more than one stage on")
        self.assertEqual(self.two(**cases["an island"])["said"]["stops"]["not_stopped"], [])
        self.assertEqual(self.two(**cases["thin"])["said"]["stops"]["not_stopped"][0]["why"], "the cover is too narrow")

    def checks_hold(self, sc: dict, r: dict) -> None:
        """build-steps' checks 1 and 2 on the second laying: the last picture is the finish, and no step changes a
        pixel outside where its unit lays paint."""
        self.assertTrue(np.array_equal(r["pictures"][-1], sc["base"][-1]))
        prev = np.full((H, W, 3), ff.CANVAS, np.float32)
        for i, pic in enumerate(r["pictures"]):
            moved = np.abs(pic.astype(np.float32) - prev).max(2) > 6
            self.assertFalse((moved & ~sc["masks"][i]).any(), i)
            prev = pic.astype(np.float32)

    def test_checks_1_and_2_hold(self):
        sky = (SKY[0], "s1", *SKY[1:])
        cloud = ("cloud", "s1", ["cloud"], box(10, 40, 30, 80), (240, 240, 245), "behind")
        hill = (HILL[0], "s2", *HILL[1:])
        rock = ("rock", "s3", ["rock"], box(85, 115, 30, 70), (120, 110, 100), "behind")
        shade = ("shade", "s4", ["hill"], box(HILL_TOP, H, 0, W // 2) & ~box(85, 115, 30, 70), (80, 100, 150), "back")
        sc = scene([sky, cloud, hill, rock, shade], ["s1", "s2", "s3", "s4"])
        r = run(sc)
        self.assertTrue(r["hidden"][0].max() > stops.HIDDEN)  # the sky and the cloud stop for the hill
        self.checks_hold(sc, r)
        sc1 = scene([(SKY[0], "s1", *SKY[1:]), (HILL[0], "s1", *HILL[1:])], ["s1"])  # nothing stops
        self.checks_hold(sc1, run(sc1))

    def test_a_unit_that_comes_back_to_the_stopped_thing_doesnt_uncover_its_bare_canvas(self):
        """A glow laid over the whole sky in the hill's stage: the hill is in the glow's own stage, so the glow's own
        line stops nothing, and without the rule its step would lay the sky's covered part back on the bare canvas."""
        sky = (SKY[0], "s1", *SKY[1:])
        glow = ("glow", "s2", ["sky"], box(0, H, 0, W), (200, 170, 200), "back")
        hill = (HILL[0], "s2", *HILL[1:])
        sc = scene([sky, glow, hill], ["s1", "s2"])
        r = run(sc)
        self.assertIsNone(r["worked"]["lines"][1])  # the glow, judged alone, doesn't stop
        self.assertTrue(bare(r["pictures"][0][140, 50]))
        self.assertTrue(bare(r["pictures"][1][140, 50]))  # still bare after the glow
        self.assertFalse(bare(r["pictures"][1][20, 50]))  # the glow above the line
        self.assertGreater(r["said"]["spared"][1]["spared"], 0.3)
        self.assertFalse(bare(r["pictures"][2][140, 50]))  # the hill, another thing, paints it
        self.checks_hold(sc, r)

    def test_canvas_two_layers_left_bare_stays_bare_for_a_glow_on_either(self):
        """The sky and a cloud bank under it both stop for the hill (the cow's sky, then its clouds): the glow on the
        sky stays off the canvas the cloud left bare too (#300's review)."""
        sky = (SKY[0], "s1", *SKY[1:])
        cloud = ("cloud", "s1", ["cloud"], box(100, H, 0, W), (240, 240, 245), "behind")
        glow = ("glow", "s2", ["sky"], box(0, H, 0, W), (200, 170, 200), "back")
        hill = (HILL[0], "s2", *HILL[1:])
        sc = scene([sky, cloud, glow, hill], ["s1", "s2"])
        r = run(sc)
        self.assertEqual([x["id"] for x in r["said"]["stops"]["stopped"]], ["sky", "cloud"])  # the glow has no line
        self.assertGreater(r["said"]["spared"][2]["spared"], 0.3)
        self.assertTrue(bare(r["pictures"][1][140, 50]))
        self.assertTrue(bare(r["pictures"][2][140, 50]))  # still bare after the glow
        self.assertFalse(bare(r["pictures"][3][140, 50]))
        self.checks_hold(sc, r)

    def test_a_unit_that_comes_back_after_its_cover_changes_nothing_the_cover_painted(self):
        """The glow after the hill: the hill has painted the canvas the sky left bare, so the glow lays only above."""
        sky = (SKY[0], "s1", *SKY[1:])
        hill = (HILL[0], "s2", *HILL[1:])
        glow = ("glow", "s3", ["sky"], box(0, HILL_TOP, 0, W), (200, 170, 200), "back")
        sc = scene([sky, hill, glow], ["s1", "s2", "s3"])
        r = run(sc)
        self.assertTrue(bare(r["pictures"][0][140, 50]))
        self.assertFalse(bare(r["pictures"][2][140, 50]))
        self.assertFalse(bare(r["pictures"][2][20, 50]))
        self.checks_hold(sc, r)


class FrameTests(unittest.TestCase):
    def test_the_canvas_inside_the_frame(self):
        fr = stops.frame((1536, 1024, 3), [0.0, 0.056, 1.0, 0.945], {"w_in": 12.0, "h_in": 16.0})
        self.assertEqual(fr["crop"], (86, 1452, 0, 1024))
        self.assertAlmostEqual(fr["ppi"], 1024 / 12)
        self.assertEqual(stops.frame((320, 480, 3), None, {"w_in": 12, "h_in": 8})["crop"], (0, 320, 0, 480))


def quiet(*argv) -> tuple[int, dict]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = tools.main(list(argv))
    return code, json.loads(buf.getvalue())


@lessons.slow
class BuildStepsTests(unittest.TestCase):
    """What build-steps --stops keeps, on test_steps3's scene (its rug doesn't reach the bottom edge: nothing stops),
    and the tool on the fixture lessons."""

    def test_what_it_keeps(self):
        from test_erase3 import pictures
        from test_steps3 import made
        lesson, plan, _ = made()
        finish = pictures()[-1]
        built = lesson3.make(lesson, plan, finish)
        self.assertNotIn("stops", built)
        before = [(lesson / n).read_bytes() for n in built["steps"]]
        kept = json.loads((lesson / "v3" / "build.json").read_text())
        self.assertNotIn("stops", kept)
        masks = np.load(lesson / "v3" / "masks.npz")
        for i in range(len(built["steps"])):
            self.assertTrue(np.array_equal(masks[f"m{i:02d}"], masks[f"f{i:02d}"]))
        box = [0, 0, 1, 1]
        (lesson / "canvas.json").write_text(json.dumps({"canvas": {"w_in": 12, "h_in": 8}, "canvas_box": box}))
        lesson3.read(lesson)  # a build without the rule doesn't read the canvas
        built = lesson3.make(lesson, plan, finish, stops=True)
        self.assertEqual(built["stops"]["rule"], "line-1-next")
        self.assertEqual(built["stops"]["stopped"], [])
        self.assertEqual(built["spared_canvas"], 0.0)
        self.assertEqual([(lesson / n).read_bytes() for n in built["steps"]], before)  # nothing stops: the same
        kept = json.loads((lesson / "v3" / "build.json").read_text())
        self.assertEqual((kept["stops"], kept["spared_canvas"]), (built["stops"], 0.0))
        self.assertTrue(all("spared" in r for r in kept["rows"]))
        got = lesson3.read(lesson)
        self.assertEqual(len(got["full"]), len(got["masks"]))
        (lesson / "canvas.json").write_text(json.dumps({"canvas": {"w_in": 18, "h_in": 12}, "canvas_box": box}))
        with self.assertRaises(lesson3.Stale) as err:
            lesson3.read(lesson)
        self.assertIn("--stops", str(err.exception))
        (lesson / "canvas.json").unlink()  # 480 x 320 is no standard canvas's shape: refused, not guessed
        with self.assertRaises(lesson3.erase3.Refused):
            lesson3.make(lesson, plan, finish, stops=True)
        shutil.rmtree(lesson)

    def test_the_fixtures(self):
        """Without --stops a fixture's step pictures are today's, byte for byte (TODAY, recorded before the rule was
        built); with it, a fixture where nothing stops gives the same pictures, and one where a layer stops keeps
        checks 1 and 2 and shows only paint it lays."""
        for name in lessons.NAMES:
            with self.subTest(name):
                _, pics, _, _ = lessons.built(name)
                self.assertEqual([hashlib.sha256(p.tobytes()).hexdigest()[:16] for p in pics], TODAY[name])
                lesson = lessons.lesson(name, "chained")
                code, out = quiet("build-steps", "--lesson", str(lesson), "--stops")
                self.assertEqual((code, out["problems"]), (0, []))
                got = lesson3.read(lesson)
                same = all(np.array_equal(a, b) for a, b in zip(got["pictures"], pics))
                self.assertEqual(same, not out["stops"]["stopped"], out["stops"]["stopped"])
                self.assertLessEqual(out["checks"]["outside_unit_max"], 0.0005)
                self.assertLessEqual(out["checks"]["final_gap"], 0.0005)
                for m, f in zip(got["masks"], got["full"]):
                    self.assertFalse((m & ~f).any())
                if out["stops"]["stopped"]:
                    self.assertGreater(out["spared_canvas"], 0)
                shutil.rmtree(lesson)


TODAY = {  # each fixture's step pictures as build-steps made them before #295 (sha256 of the pixels, 16 digits)
    "chickadee": [
        "9e46d61dac66d56b", "384c9fde109b020c", "dcc084381dcfe00f", "b131cc59ad5ac686", "5c9495a9964a06b0",
        "769e61927ce62968", "4662bc062737d75d", "f74b36b17a6f0ff9", "eb80535322a61ea0", "49d51467fb27d596",
        "80bb2b24a79816a0", "c8134832a739547f", "d1ef1ec52a621504", "7c115a1c02ce69c6", "cdcff324a4bc796f",
        "304e0cef4c981b0e", "0d0ae1d40c19b585", "7aa6ea6e20273ee4", "e6d96829b4dc0da4", "366d2e8ef1beb20f",
        "59783b586b1787ee", "8c5a80c1b29fb030", "e3030ac788ae9d69", "7283ca1b35110036",
    ],
    "lavender-balloon": [
        "cf76d5469238d13f", "a1eee3a66de7004d", "2d1161f3fec2ed57", "7f7d96392eb09e72", "b78741fef4fb4315",
        "00d33d4117da5348", "6a21f99ef3c0043d", "bca3c040b93e2268", "28047a06841aa47e", "5ace40e8f257d042",
        "b3d44a8b4f978a51", "5ef1c2a157c45897", "d36127decb9528f6", "471c18f60aaf8122", "2060498b560b5cc9",
        "a6b9842f7602b5d6", "3f458dc743f09abf", "5921104452c4dd93", "0ede771d2f20b5c5", "e55e87b80911fac9",
        "610bc73db4026c4c", "7e8627a84fca06f2", "7af4b0a4ce9470bf", "4ccf157952e704cb",
    ],
    "red-sailboat": [
        "38b8dab4c222f889", "11e3cee3b1d662af", "1f14b5b8fa87efe6", "6d22d426aaf69d5f", "7119d6cecdff3235",
        "358ff0bfb2c7e1a6", "7d2fef2614552183", "9cf7a4c76c728483", "4ae7e6429be4a81b", "82edda1d9f0ae471",
        "3efddb4faad908c2", "57551d1a67ac2df8", "6fd4532a1e8e96ef", "3866995cce08a213", "814d9b728e770a4e",
        "e5e6534fda615c88", "9189f39e1b021c45", "8fca483e604d7491", "75ee740805bffa13", "a9fed3757df9a908",
        "5836fa89185c164b", "3fc7673b3455458f",
    ],
}


BENCH = HERE.parent / "experiments" / "bench" / "v31-gate"
TABLE = {  # docs/design/pipeline-v4.md section 3: (unit, its steps, covered by its step, highest, most, lowest, past)
    "highland-cow": [("sky", [1], 4, 3 + 5 / 16, 3.5, 4 + 1 / 8, 1.0),  # the sky, then the clouds
                     ("clouds", [2, 3], 4, 3 + 5 / 16, 3.5, 4 + 1 / 8, 1.0),
                     ("far-hills", [4], 7, 4 + 5 / 8, 5.25, 6 + 1 / 16, 1 + 1 / 8)],
    "birch-grove": [("sky", [1], 4, 7 + 11 / 16, 8.25, 9.0, 1 + 1 / 8),  # the mist, and the far woods in it
                    ("far-woods", [2, 3], 4, 7 + 11 / 16, 8.25, 9.0, 1 + 1 / 8)],
    "sleeping-cat": [],
}


@lessons.slow
class BenchTests(unittest.TestCase):
    """The three bench chains (spike/experiments/bench/v31-gate/): the rule's pictures are the experiment's
    `line-1-next` pictures, pixel for pixel, and the lines are the design's section 3 table (to 1/16 in)."""

    def test_the_bench_chains(self):
        import cover_margin as cm
        for pic in cm.PICTURES:
            with self.subTest(pic):
                L = cm.load(pic)
                base = cm.baseline(L)
                want = cm.variant_steps(L, "line-1-next", base)["pictures"]
                c = json.loads((BENCH / pic / "data" / "canvas.json").read_text())
                fr = stops.frame(L["P"][0].shape, c["canvas_box"], c["canvas"])
                worked = stops.work_out(L["plan"], L["units"], L["m"], L["owner_png"], fr)
                laid = stops.lay(base, L["m"], L["units"], worked["want"])
                for i, (a, b) in enumerate(zip(laid["pictures"], want)):
                    self.assertTrue(np.array_equal(a, b), i + 1)
                said = stops.report(L["plan"], L["units"], L["m"], worked, laid, fr)
                got = [(r["id"], r["steps"], r["covered_by"]["step"], r["line"]["highest"], r["line"]["most"],
                        r["line"]["lowest"], r["line"]["past_cover"]["most"]) for r in said["stops"]["stopped"]]
                self.assertEqual([g[:3] for g in got], [t[:3] for t in TABLE[pic]])
                for g, t in zip(got, TABLE[pic]):
                    for a, b in zip(g[3:], t[3:]):
                        self.assertAlmostEqual(a, b, delta=1 / 16, msg=(pic, g[0]))
                self.assertEqual(said["notes"], [])
                if pic == "highland-cow":
                    self.assertEqual([s["spared"] for s in said["spared"][:4]], [0.688, 0.448, 0.278, 0.729])
                    self.assertAlmostEqual(said["spared_canvas"], 1.42, delta=0.01)
                if pic == "birch-grove":
                    self.assertAlmostEqual(said["spared"][0]["spared"], 0.28, delta=0.01)


if __name__ == "__main__":
    unittest.main()
