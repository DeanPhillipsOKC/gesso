"""Tests for a version 3 lesson's paints, step pictures and shapes (spike/steps3.py, spike/lesson3.py;
docs/design/pipeline-v3.md sections 7 to 9), on test_erase3's made-up scene and stand-in model."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import erase3  # noqa: E402
import lesson3  # noqa: E402
import lessons  # noqa: E402
import plan2  # noqa: E402
import plan3  # noqa: E402
import steps3  # noqa: E402
import tools  # noqa: E402
from test_erase3 import CAT, PALE, RUG, SHADOW, SKY, WHERE, Model, pictures  # noqa: E402
from test_plan3 import plan, step  # noqa: E402


def made(p: dict | None = None) -> tuple[Path, dict, list[dict]]:
    """A lesson folder with the made-up scene's plan, finish and chain."""
    p = p or plan()
    lesson = Path(tempfile.mkdtemp())
    (lesson / "plan.json").write_text(json.dumps(p), encoding="utf-8")
    Image.fromarray(pictures()[-1]).save(lesson / "99_finish.png")
    erase3.run(lesson, p, pictures()[-1], Model())
    return lesson, p, erase3.load(lesson, p)


def near(hx: str, rgb: tuple, by: int = 3) -> bool:
    return max(abs(int(hx[i:i + 2], 16) - v) for i, v in zip((1, 3, 5), rgb)) <= by


@lessons.slow
class Steps3Tests(unittest.TestCase):
    whole = True

    @classmethod
    def setUpClass(cls):
        cls.lesson, cls.plan, cls.ch = made()
        cls.finish = pictures()[-1]
        cls.built = steps3.build(cls.plan, cls.finish, cls.ch)

    def test_each_paint_is_fitted_to_what_its_units_changed(self):
        one, per_unit, rows = steps3.fit(self.plan, plan3.units(self.plan), self.ch)
        for name, rgb in (("Sky blue", SKY), ("Rug red", RUG), ("Cat gray", CAT), ("Shadow", SHADOW), ("Pale gray", PALE)):
            self.assertTrue(near(one[name], rgb), (name, one[name]))
        by = {r["paint"]: r for r in rows}
        self.assertEqual(by["Shadow"]["units"], [3, 4])
        self.assertEqual(by["Shadow"]["from_unit"], 3)  # the shadows lay more of it than the eyes
        self.assertFalse(any(r["far_from_name"] or r["not_in_finish"] for r in rows))

    def test_a_paint_far_from_its_name_and_a_paint_the_finish_lacks_are_reported(self):
        p = plan()
        p["paints"][1]["color"] = "#2244cc"  # "Rug red" given as a blue: it is still fitted to the rug
        p["paints"].append({"name": "Lime", "looks": "x", "color": "#00ff00"})
        step(p, "light-cat")["paints"] = ["Pale gray", "Lime"]
        one, _, rows = steps3.fit(p, plan3.units(p), self.ch)
        by = {r["paint"]: r for r in rows}
        self.assertTrue(near(one["Rug red"], RUG))
        self.assertTrue(by["Rug red"]["far_from_name"])
        self.assertTrue(by["Lime"]["not_in_finish"])
        self.assertEqual(one["Lime"], "#00ff00")
        bad, notes = steps3.problems({**self.built, "paints": rows})
        self.assertEqual(bad, [])
        self.assertTrue(any("'Rug red' was fitted to" in n for n in notes))
        self.assertTrue(any("'Lime'" in n and "doesn't have" in n for n in notes))

    def test_the_three_checks_hold(self):
        b = self.built
        self.assertEqual((b["final_gap"], b["outside_unit_max"]), (0.0, 0.0))
        self.assertLess(b["from_its_paints_median"], 3)
        self.assertTrue(np.array_equal(b["pictures"][-1], self.finish))
        self.assertEqual(steps3.problems(b), ([], []))
        self.assertEqual(steps3.problems({**b, "final_gap": 0.01})[0][0][:38], "the last step picture isn't the finish")

    def test_a_units_last_step_is_its_picture_and_an_earlier_step_lays_only_its_own_paint(self):
        b = self.built
        self.assertEqual([r["show"] for r in b["rows"]], ["all", "all", "all", "pass", "all", "all"])
        for n, i in ((0, 0), (1, 1), (2, 2), (3, 4), (4, 5)):
            self.assertTrue(np.array_equal(b["pictures"][i], self.ch[n]["P"]), n)
        shadows, light = b["pictures"][3], WHERE["light"]
        inner = np.zeros_like(light)
        inner[130:145, 210:290] = True
        self.assertTrue((np.abs(shadows[inner].astype(int) - CAT).max() <= 2))  # the light isn't there yet
        self.assertTrue((np.abs(shadows[275:295, 100:150].astype(int) - SHADOW).max() <= 2))
        self.assertGreater(b["masks"][4][inner].mean(), 0.99)
        self.assertFalse(b["masks"][3][inner].any())

    def test_a_step_that_changes_almost_nothing_is_reported(self):
        p = plan()
        p["paints"].append({"name": "Lime", "looks": "x", "color": "#00ff00"})
        st = p["stages"][2]["steps"]
        st.insert(1, dict(st[1], id="lime-dots", paints=["Lime"]))
        b = steps3.build(p, self.finish, erase3.load(made(p)[0], p))
        self.assertEqual(b["little"], ["lime-dots"])
        self.assertTrue(any("lime-dots: changes almost nothing" in n for n in steps3.problems(b)[1]))

    def test_shapes_and_the_plan_in_version_2s_shape(self):
        us = plan3.units(self.plan)
        owner = steps3.owner_from(self.ch)
        self.assertEqual([int(owner[y, x]) for y, x in ((50, 50), (280, 100), (200, 250), (168, 250), (5, 5))], [0, 3, 2, 4, 0])
        shapes = steps3.shapes(self.ch, owner)
        self.assertGreater(shapes[2][WHERE["cat"]].mean(), 0.9)  # the cat's shape is all of it, eyes and shadow too
        view = steps3.as_v2(self.plan, us, self.ch, self.built["hexes"], owner, self.finish)
        self.assertEqual(plan2.problems(view), [])
        self.assertEqual([(p["id"], p["kind"], p.get("parent")) for p in view["parts"]],
                         [("sky", "area", None), ("rug", "area", None), ("cat", "object", None),
                          ("the-shadows", "marks", "rug"), ("the-cat-s-eyes", "marks", "cat")])
        x0, y0, x1, y1 = view["parts"][2]["box"]
        self.assertTrue(abs(x0 - 170 / 480) < 0.02 and abs(y1 - 250 / 320) < 0.02, view["parts"][2]["box"])
        self.assertEqual([(s["part"], s["show"]) for st in view["stages"] for s in st["steps"]],
                         [("sky", "blend"), ("rug", "full"), ("cat", "full"), ("the-shadows", "pass"),
                          ("the-shadows", "full"), ("the-cat-s-eyes", "full")])
        paints = {c["id"]: c for c in view["paints"]}
        self.assertEqual(paints["pale-gray"]["of"], "cat-gray")
        self.assertEqual(paints["shadow"]["parts"], ["the-shadows", "the-cat-s-eyes"])
        self.assertEqual((view["plan_version"], view["made_from"]), (2, 3))

    def test_every_bench_plan_and_awkward_plan_fits_version_2s_shape(self):
        def view_of(p):
            us = plan3.units(p)
            n = len(us)
            ch = []
            for k in range(n):  # a stand-in chain: each unit changed its own stripe
                d = np.zeros((40, 10 * n), bool)
                d[:, 10 * k:10 * k + 10] = True
                ch.append({"P": np.full((40, 10 * n, 3), 200, np.uint8), "D": d, "core": d})
            hexes = {q["name"]: q["color"] for q in p["paints"]}
            return steps3.as_v2(p, us, ch, hexes, steps3.owner_from(ch), ch[-1]["P"])

        for path in sorted((HERE / "fixtures" / "plans3").glob("*.json")):
            self.assertEqual(plan2.problems(view_of(json.loads(path.read_text(encoding="utf-8")))), [], path.name)
        # a thing painted in several steps is marks, and a unit that comes back to it can't be marks on marks
        p = plan()
        del step(p, "block-cat")["block_in"]
        p["stages"][1]["steps"].append(dict(step(p, "light-cat"), id="cat-belly", paints=["Pale gray"]))
        step(p, "light-cat")["paints"] = ["Sky blue"]
        view = view_of(p)
        self.assertEqual(plan2.problems(view), [])
        kinds = {x["id"]: (x["kind"], x.get("parent")) for x in view["parts"]}
        self.assertEqual(kinds["cat"], ("marks", "rug"))
        self.assertEqual(kinds["the-cat-s-eyes"], ("marks", "rug"))
        # a blend of four paints with another step of its thing after it in the stage: the blend is a unit alone
        p = plan()
        p["paints"] += [{"name": "Gold", "looks": "x", "color": "#d0a020"}, {"name": "Teal", "looks": "x", "color": "#208080"}]
        step(p, "blend-sky")["paints"] = ["Sky blue", "Gold", "Teal", "Shadow"]
        p["stages"][0]["steps"].append(dict(step(p, "light-cat"), id="sky-glow", lays=[{"thing": "sky", "what": "x"}],
                                            paints=["Pale gray"], unit="The glow"))
        p["things"][0]["plain"] = "the plain sky"
        self.assertEqual([u["steps"] for u in plan3.units(p)][:2], [[0], [1]])
        self.assertEqual(plan2.problems(view_of(p)), [])

    def test_build_steps_keeps_what_the_later_tools_read_and_refuses_it_stale(self):
        with self.assertRaises(lesson3.Stale) as e:
            lesson3.read(self.lesson)
        self.assertIn("run build-steps", str(e.exception))
        got = lesson3.make(self.lesson, self.plan, self.finish)
        self.assertEqual(got["steps"][0], "01_blend-sky.png")
        kept = lesson3.read(self.lesson)
        self.assertEqual(kept["plan"], got["plan"])
        self.assertTrue(np.array_equal(kept["owner"], got["owner"]))
        self.assertTrue(all(np.array_equal(a, b) for a, b in zip(kept["pictures"], got["pictures"])))
        self.assertTrue(all(np.array_equal(a, b) for a, b in zip(kept["masks"], got["masks"])))
        self.assertEqual(len(kept["shapes"]), 5)
        self.assertNotIn("pictures", lesson3.read(self.lesson, pictures=False))
        (self.lesson / "02_block-rug.png").unlink()
        with self.assertRaises(lesson3.Stale):
            lesson3.read(self.lesson)
        lesson3.make(self.lesson, self.plan, self.finish)
        Image.fromarray(pictures()[0]).save(self.lesson / "02_block-rug.png")  # a step picture something else wrote
        with self.assertRaises(lesson3.Stale) as e:
            lesson3.read(self.lesson)
        self.assertIn("02_block-rug.png isn't the file build-steps wrote", str(e.exception))
        with mock.patch.object(steps3, "as_v2", lambda *a, **k: {"plan_version": 2, "parts": []}):
            with self.assertRaises(erase3.Refused) as e:
                lesson3.make(self.lesson, self.plan, self.finish)
        self.assertIn("report it", str(e.exception))
        lesson3.make(self.lesson, self.plan, self.finish)
        p = plan()
        step(p, "light-cat")["name"] = "Light the cat's back"
        (self.lesson / "plan.json").write_text(json.dumps(p), encoding="utf-8")
        with self.assertRaises(lesson3.Stale) as e:
            lesson3.read(self.lesson)
        self.assertIn("changed since", str(e.exception))


@lessons.slow
class V3ToolsTests(unittest.TestCase):
    """The version 2 tools on a version 3 lesson: each reads what build-steps kept, and none cuts a step again."""

    whole = True

    @classmethod
    def setUpClass(cls):
        p = plan()
        for sid, stroke in (("shadows", "curved-strokes"), ("light-cat", "curved-strokes"), ("cat-eyes", "dotting")):
            step(p, sid)["stroke"] = stroke
        cls.lesson, cls.plan, _ = made(p)
        (cls.lesson / "canvas.json").write_text(json.dumps({
            "canvas": {"w_in": 12.0, "h_in": 8.0, "orientation": "landscape"}, "canvas_box": [0.0, 0.0, 1.0, 1.0],
            "chosen": "test", "mode": "none", "lost_share": 0.0}), encoding="utf-8")
        cls.patch = mock.patch.object(tools, "_v3_plan", lambda lesson: (json.loads((lesson / "plan.json").read_text()), {}))
        cls.patch.start()
        cls.addClassCleanup(cls.patch.stop)

    def tool(self, name: str, *more: str) -> tuple[int, dict]:
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = tools.main([name, "--lesson", str(self.lesson), *more])
        return code, json.loads(buf.getvalue())

    def test_the_run_from_paints_to_drafted_lines(self):
        for name in ("step-aids", "mix", "draft-text"):  # nothing was built yet
            code, r = self.tool(name)
            self.assertEqual(code, 2, name)
            self.assertIn("run build-steps", r["refused"])
        code, r = self.tool("paints")
        self.assertEqual((code, len(r["paints"]), r["notes"]), (0, 5, []))
        self.assertIn("version 2 lesson", self.tool("paints", "--add", "cat")[1]["refused"])
        self.assertIn("version 2 lesson", self.tool("background")[1]["refused"])
        self.assertIn("isn't a version 2 plan", self.tool("outline")[1]["refused"])
        code, r = self.tool("build-steps")
        self.assertEqual((code, r["problems"], r["notes"]), (0, [], []))
        self.assertEqual(r["checks"]["final_gap"], 0.0)
        self.assertEqual(len(r["steps"]), 6)
        self.assertTrue((self.lesson / "trials" / "steps.jpg").exists())
        with mock.patch("build_steps.build", side_effect=AssertionError("a version 3 step was cut again")):
            code, r = self.tool("step-aids")
            self.assertEqual((code, r["steps"]), (0, 6))
            code, r = self.tool("mix")
            self.assertEqual(code, 0, r)
            self.assertEqual([m["name"] for m in r["paints"]], ["Sky blue", "Rug red", "Cat gray", "Shadow", "Pale gray"])
            code, r = self.tool("draft-text")
            self.assertEqual((code, r["steps"]), (0, 6))
        text = json.loads((self.lesson / "text.json").read_text())
        kinds = {x["kind"] for t in text["steps"] for x in t["lines"]}
        self.assertTrue({"where", "paints", "how"} <= kinds, kinds)
        cat = next(t for t in text["steps"] if t["stage_id"] == "block-cat")
        self.assertTrue(any(x["kind"] == "chalk" for x in cat["lines"]))  # a blocked-in thing in front: its outline
        # the plan changes: what was kept is stale, and every later tool says so
        p = json.loads((self.lesson / "plan.json").read_text())
        step(p, "light-cat")["name"] = "Light the cat's back"
        (self.lesson / "plan.json").write_text(json.dumps(p), encoding="utf-8")
        code, r = self.tool("step-aids")
        self.assertEqual(code, 2)
        self.assertIn("changed since", r["refused"])


if __name__ == "__main__":
    unittest.main()
