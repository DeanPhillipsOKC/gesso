"""Tests for a version 3 lesson's paints, step pictures and shapes (spike/steps3.py, spike/lesson3.py;
docs/design/pipeline-v3.md sections 7 to 9), on test_erase3's made-up scene and stand-in model."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import checks  # noqa: E402
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
        p["paints"][1]["color"] = "#b06848"  # "Rug red" given as a dull orange-brown: it is still fitted to the rug
        p["paints"][0]["color"] = "#22aa44"  # "Sky blue" given as a green: nothing in the sky is like that
        p["paints"].append({"name": "Lime", "looks": "x", "color": "#00ff00"})
        step(p, "light-cat")["paints"] = ["Pale gray", "Lime"]
        one, _, rows = steps3.fit(p, plan3.units(p), self.ch)
        by = {r["paint"]: r for r in rows}
        self.assertTrue(near(one["Rug red"], RUG))
        self.assertGreater(by["Rug red"]["moved"], 20)
        self.assertTrue(by["Lime"]["not_in_finish"])
        self.assertEqual(one["Lime"], "#00ff00")
        self.assertTrue(by["Sky blue"]["not_in_finish"])  # a paint keeps its color where no pixel is like it
        self.assertEqual(one["Sky blue"], "#22aa44")
        rows[1]["far_from_name"] = True
        bad, notes = steps3.problems({**self.built, "paints": rows})
        self.assertEqual(bad, [])
        self.assertTrue(any("'Rug red' was fitted to" in n for n in notes))
        self.assertTrue(any("'Lime'" in n and "doesn't have" in n for n in notes))

    def test_a_paint_is_not_fitted_to_what_else_its_units_change_holds(self):
        # the cat's change, widened to take in the sky and rug round it, as a render that drew them again would
        ch = [dict(c) for c in self.ch]
        wide = np.zeros_like(ch[2]["D"])
        wide[60:300, 100:400] = True
        ch[2] = {**ch[2], "D": wide}
        one, _, rows = steps3.fit(self.plan, plan3.units(self.plan), ch)
        self.assertTrue(near(one["Cat gray"], CAT), one["Cat gray"])

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


class ShadingPaintTests(unittest.TestCase):
    """#250: a unit that comes back to a block-in is kept over the whole thing (#217), so its change is all of the
    cat while it lays a few marks. A shading or lighting paint was fitted to all of it, came out the cat's own gray,
    and `check` asked to merge it into the block-in's paint."""

    def chain(self) -> tuple[dict, list[dict]]:
        import cv2

        rng = np.random.default_rng(250)
        h, w = 200, 300
        cat = np.zeros((h, w), bool)
        cat[40:180, 50:250] = True
        base = np.empty((h, w, 3), np.float32)
        base[:] = steps3.ff.CANVAS
        p0 = base.copy()
        p0[cat] = CAT

        def marks(img, rows, color):  # soft-edged strokes, then faint brushwork over the whole cat
            m = np.zeros((h, w), np.float32)
            for y in rows:
                m[y:y + 10, 60:240] = 1.0
            a = cv2.GaussianBlur(m, (0, 0), 2.0)[..., None] * cat[..., None]
            out = img * (1 - a) + np.array(color, np.float32) * a
            out[cat] += rng.normal(0, 2.5, (int(cat.sum()), 1))
            return np.clip(out, 0, 255).astype(np.uint8)

        p0 = np.clip(p0, 0, 255).astype(np.uint8)
        p1 = marks(p0.astype(np.float32), range(130, 170, 16), SHADOW)  # shade the cat's belly
        p2 = marks(p1.astype(np.float32), range(48, 90, 16), PALE)  # light its back
        ch = [{"P": p, "D": cat, "core": cat} for p in (p0, p1, p2)]
        paints = [{"name": "Cat gray", "looks": "x", "color": "#808080"},
                  {"name": "Shadow gray", "looks": "x", "color": "#4a4040", "of": "Cat gray"},
                  {"name": "Light gray", "looks": "x", "color": "#c0c0c0", "of": "Cat gray"}]
        steps = [{"id": "block-in-cat", "paints": ["Cat gray"]}, {"id": "shade-cat", "paints": ["Shadow gray"]},
                 {"id": "light-cat", "paints": ["Light gray"]}]
        return {"paints": paints, "stages": [{"id": "cat", "steps": steps}]}, ch

    def test_a_one_paint_shading_unit_keeps_a_paint_of_its_own(self):
        import mixing

        p, ch = self.chain()
        us = [{"steps": [0], "kind": "bare"}, {"steps": [1], "kind": "back"}, {"steps": [2], "kind": "back"}]
        one, _, rows = steps3.fit(p, us, ch)
        self.assertTrue(near(one["Cat gray"], CAT), one["Cat gray"])
        self.assertTrue(near(one["Shadow gray"], SHADOW, 12), one["Shadow gray"])
        self.assertTrue(near(one["Light gray"], PALE, 12), one["Light gray"])
        lightness = {n: steps3.ff.hex_lab(one[n])[0] for n in one}
        self.assertLess(lightness["Shadow gray"], lightness["Cat gray"] - 20)
        self.assertGreater(lightness["Light gray"], lightness["Cat gray"] + 20)
        tubes = ["Titanium white", "Ultramarine blue", "Burnt sienna", "Cadmium yellow medium (hue)"]
        self.assertEqual(tools.duplicate_recipes(mixing.solve_lesson(one, tubes)), [])
        # fitted to all of what the units changed, as before #250: both come out the cat's own gray
        with mock.patch.object(steps3, "what_moved", lambda ch, n: ch[n]["D"]), \
                mock.patch.object(steps3, "before", lambda ch, n: None):
            old, _, _ = steps3.fit(p, us, ch)
        self.assertTrue(near(old["Shadow gray"], CAT, 12) and near(old["Light gray"], CAT, 12), old)

    def test_a_unit_that_moved_almost_nothing_is_fitted_to_all_of_its_change(self):
        p, ch = self.chain()
        ch[1] = {**ch[1], "P": ch[0]["P"]}
        self.assertTrue(np.array_equal(steps3.what_moved(ch, 1), ch[1]["D"]))
        self.assertGreater(steps3.what_moved(ch, 2).mean(), 0)
        self.assertLess(steps3.what_moved(ch, 2).mean(), ch[2]["D"].mean() / 2)


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
        real = checks._technique

        def no_ranges(lesson, plan):  # the made-up plan has 6 steps; the real technique wants 12 to 24
            return {k: v for k, v in real(lesson, plan).items() if k not in ("v2_step_range", "v2_stage_range")}

        cls.patch2 = mock.patch.object(checks, "_technique", no_ranges)
        cls.patch2.start()
        cls.addClassCleanup(cls.patch2.stop)

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
        code, r = self.tool("build-steps")
        self.assertEqual((code, r["problems"], r["notes"]), (0, [], []))
        self.assertEqual(len(r["paints"]), 5)
        self.assertEqual(r["checks"]["final_gap"], 0.0)
        self.assertEqual(len(r["steps"]), 6)
        self.assertTrue((self.lesson / "trials" / "steps.jpg").exists())
        with mock.patch("steps3.build", side_effect=AssertionError("a step was cut again after build-steps")):
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
        self.words_check_and_seal()
        # the plan changes: what was kept is stale, and every later tool says so
        p = json.loads((self.lesson / "plan.json").read_text())
        step(p, "light-cat")["name"] = "Light the cat's back"
        (self.lesson / "plan.json").write_text(json.dumps(p), encoding="utf-8")
        code, r = self.tool("step-aids")
        self.assertEqual(code, 2)
        self.assertIn("changed since", r["refused"])

    def words_check_and_seal(self):
        """packets, a stand-in lesson writer through every round (v3.1, #276), the arc and its round, check, and what
        the seal asks of the run."""
        self.assertIn("run draft-text, then packets", self.tool("check-text")[1]["refused"])
        code, r = self.tool("packets")
        self.assertEqual((code, r["steps"], r["stages"]), (0, 6, 3))
        folder = self.lesson / "words" / "lesson"
        for name in ("brief.md", "arc-brief.md", "steps.md", "cards.md", "stages.md", "plan.json", "facts.md",
                     "pair-01.jpg", "change-06.jpg", "finish.jpg"):
            self.assertTrue((folder / name).exists(), name)
        steps_md = (folder / "steps.md").read_text()
        self.assertIn("step 5 `light-cat`: Light the cat. Part: ", steps_md)
        self.assertIn("Stroke card: curved-strokes", steps_md)
        self.assertIn("Pale gray (", steps_md)  # its recipe, as the page shows it
        facts_md = (folder / "facts.md").read_text()
        self.assertNotIn("Where line (kept as it is", facts_md)  # the lean sheet (#267)
        self.assertNotIn(" in (", facts_md)
        self.assertIn("stage 3 `the-finish`: Shadows and lights. Steps 4, 5, 6. Its end: pair-06.jpg.",
                      (folder / "stages.md").read_text())
        sheet = json.loads((self.lesson / "words" / "sheet.json").read_text())
        # a unit that comes back to a thing is measured by what it changed (#214): the eyes, not a speck
        self.assertAlmostEqual(sheet["parts"]["the-cat-s-eyes"]["wide"], 70 / 480 * 12, delta=0.3)

        def six(what: str, **lines) -> dict:
            return {"first": "", "start": f"Start on {what} where the after picture has it.",
                    "strokes": "Pull each stroke smoothly, the way the card says.", "inside": f"Cover {what} evenly.",
                    "leave": "Leave the paint already there as it is.", "stop": f"Stop when {what} matches the "
                    "after picture.", **lines}

        def write(name: str, steps: dict) -> None:
            (folder / name).write_text(json.dumps({"steps": steps}), encoding="utf-8")

        long = " ".join(["Work the red into the weave of the rug slowly and patiently"] * 5) + "."
        first = {"blend-sky": six("the sky"), "block-rug": six("the rug", inside=long),
                 "block-cat": six("the cat"), "shadows": six("the shadows"),
                 "light-cat": six("the cat's back", strokes="Lay the Pale gray over the Cat gray coat."),
                 "cat-eyes": six("the eyes", inside="The eyes are about 9 in wide. Keep them dark.")}
        self.assertIn("no out.json", self.tool("check-text")[1]["problems"][0])
        (folder / "out.json").write_text("{not json", encoding="utf-8")
        code, r = self.tool("check-text")
        self.assertTrue(any("out.json isn't valid JSON" in x for x in r["problems"]), r)
        write("out.json", {**first, "nope": six("x"), "block-cat": {k: v for k, v in six("the cat").items()
                                                                    if k != "stop"}})
        code, r = self.tool("check-text")
        self.assertTrue(any("no step nope" in x for x in r["problems"]), r)
        self.assertTrue(any("block-cat) has no `stop` line" in x for x in r["problems"]), r)
        # round 1: the number the sheet doesn't have goes back, and only that
        write("out.json", first)
        code, r = self.tool("check-text")
        self.assertEqual((code, r["round"], r["send_back"]), (0, 1, "fix-1.json"), r)
        fb = (folder / "feedback.md").read_text()
        self.assertIn("9 in", fb)
        self.assertNotIn("Cat gray", fb)
        self.assertIn("only the steps you change", fb)
        text = {t["stage_id"]: t for t in json.loads((self.lesson / "text.json").read_text())["steps"]}
        self.assertEqual([x["kind"] for x in text["light-cat"]["lines"]],
                         ["start", "strokes", "inside", "leave", "stop"])  # `first` left empty; no drafted lines
        self.assertNotIn("summary", text["light-cat"])
        self.assertEqual(text["light-cat"]["reason"], tools.V3_REASON)  # the header is still draft-text's
        self.assertEqual(self.tool("check-text")[1]["send_back"], "fix-1.json")  # waiting on the answer
        # its answer changes one step and still says a size the sheet doesn't have; round 2: the paint and the line
        write("fix-1.json", {"cat-eyes": six("the eyes", inside="The eyes are about 8 in wide. Keep them dark.")})
        code, r = self.tool("check-text")
        self.assertEqual((r["round"], r["send_back"]), (2, "fix-2.json"), r)
        fb = (folder / "feedback.md").read_text()
        self.assertIn("names Cat gray, which isn't one of its paints (Pale gray)", fb)
        self.assertIn("its `inside` line is 60 words", fb)
        self.assertNotIn("8 in", fb)  # check-text's failures went back once, in round 1
        write("fix-2.json", {"block-rug": six("the rug")})
        code, r = self.tool("check-text")
        self.assertTrue(r["done"], r)
        self.assertEqual([x["sent"] for x in r["rounds"]], [1, 2])
        # the last check takes out what still fails either check; it never rewords
        code, r = self.tool("check-text", "--final")
        self.assertEqual((r["ok"], r["dropped"], r["left_failing"], r["long_lines"]), (True, 2, 0, []), r)
        self.assertEqual(r["emptied"], [{"id": "light-cat", "kind": "strokes"}])
        text = {t["stage_id"]: t for t in json.loads((self.lesson / "text.json").read_text())["steps"]}
        self.assertEqual(next(x for x in text["cat-eyes"]["lines"] if x["kind"] == "inside")["text"], "Keep them dark.")
        self.assertNotIn("strokes", [x["kind"] for x in text["light-cat"]["lines"]])
        self.assertEqual(sorted(x["id"] for x in json.loads((self.lesson / "words" / "dropped.json").read_text())),
                         ["cat-eyes", "light-cat"])
        self.assertIn("## Step 6 `cat-eyes`", (folder / "words.md").read_text())
        # draft-text run again keeps the writer's lines, and adds none of its own (it makes the header only)
        before = json.loads((self.lesson / "text.json").read_text())
        self.tool("draft-text")
        self.assertEqual([t["lines"] for t in json.loads((self.lesson / "text.json").read_text())["steps"]],
                         [t["lines"] for t in before["steps"]])
        self.arc_round(folder)
        code, r = self.tool("check")
        self.assertEqual((code, r["problems"]), (0, []))
        # the seal: a version 3 run needs the chain's checker and the words' last check, not the text review
        text = {t["stage_id"]: t for t in json.loads((self.lesson / "text.json").read_text())["steps"]}
        review = {"finish_issues": [], "text_issues": []}
        (self.lesson / "review.json").write_text(json.dumps(review), encoding="utf-8")
        plan_model = tools.load_plan(self.lesson)[1]
        asks = lambda: [x for x in tools.seal_problems(self.lesson, plan_model, text, review, {}, {})  # noqa: E731
                        if "checker" in x or "check-text" in x or "text review" in x or "summary" in x]
        self.assertEqual(len(asks()), 1)
        self.assertIn("chain/looks/answers.json", asks()[0])
        (self.lesson / "chain" / "looks" / "answers.json").write_text("[]", encoding="utf-8")
        self.assertIn("doesn't answer for every unit", asks()[0])
        (self.lesson / "chain" / "looks" / "answers.json").write_text(
            json.dumps([{"look": f"U{n:02d}", "stray": False, "left": False} for n in range(1, 5)]), encoding="utf-8")
        self.assertEqual(asks(), [])
        os.environ.setdefault("GESSO_HISTORY", str(self.lesson / "history"))
        code, r = self.tool("publish")
        self.assertEqual(code, 0, r)
        data = json.loads((self.lesson / "lesson.json").read_text())
        self.assertEqual((data["plan_version"], data["pipeline"], len(data["stages"])), (2, 3, 6))
        # the lessons site takes a version 3 lesson like any other (owner, 2026-11-18)
        import site_lessons

        self.assertTrue(site_lessons.on_site_era(self.lesson))
        # the words laid again from the writer's files bring the failing sentences back: the last check no longer
        # stands, and `check` (which the seal runs) says so
        code, r = self.tool("check-text")
        self.assertFalse((self.lesson / "words" / "dropped.json").exists())
        self.assertTrue(any("8 in" in x and "check-text --final" in x for x in self.tool("check")[1]["problems"]))
        # a new out.json starts its rounds again, and the old answers go
        write("out.json", {**first, "cat-eyes": six("the eyes")})
        code, r = self.tool("check-text")
        self.assertFalse((folder / "fix-1.json").exists())
        self.assertIn("out.json is new: its rounds start from round 1", r["said"])
        # packets made again throw the old words away, and check-text refuses words written for other pictures
        self.tool("packets")
        self.assertFalse((folder / "out.json").exists())
        sheet_path = self.lesson / "words" / "sheet.json"
        sheet_path.write_text(sheet_path.read_text().replace('"w_in": 12.0', '"w_in": 11.0'), encoding="utf-8")
        self.assertIn("run packets again", self.tool("check-text")[1]["refused"])

    def arc_round(self, folder: Path) -> None:
        """The arc as the writer's next message: each of its checks, its one round, and what --final writes."""
        self.assertIn("no arc.json", self.tool("check-text", "--arc")[1]["problems"][0])

        def write(name: str, arc: dict) -> None:
            (folder / name).write_text(json.dumps(arc), encoding="utf-8")

        good = {"opening": {"welcome": "A gray cat asleep on a red rug.", "light": "Soft daylight from the window.",
                            "skills": [{"card": "build-from-pieces", "steps": [2, 3], "how": "Flat shapes first."},
                                       {"card": "curved-strokes", "steps": [4, 5], "how": "Strokes that follow the "
                                        "form."}],
                            "road": "The sky goes first, then the shapes, then the shadows and lights."},
                "stages": {"the-sky": {"for": "The sky behind it all.", "end": "A soft blue sky."},
                           "the-shapes": {"for": "The rug and the cat as flat shapes.", "end": "Two flat shapes."},
                           "the-finish": {"for": "Shadow and light.", "end": "The cat looks round."}},
                "steps": {"block-cat": {"back": {"step": 2, "text": "The same flat pieces as the rug, now in gray."}},
                          "light-cat": {"back": {"step": 4, "text": "The same curved strokes as the shadows."}},
                          "cat-eyes": {"back": {"step": 4, "text": "The same dark paint as the shadows."}}}}
        bad = json.loads(json.dumps(good))
        bad["opening"]["skills"].append({"card": "glazing", "steps": [4], "how": "Thin layers."})  # not a card it uses
        bad["opening"]["skills"][1]["steps"] = [4, 6]  # step 6 is dotting
        bad["opening"]["road"] += " Finish on the right side of the cat."  # a side word in the opening
        bad["stages"]["the-sky"]["end"] = "A blue sky about 12 in wide."  # a number in a stage's line
        del bad["stages"]["the-finish"]["for"]
        bad["steps"]["light-cat"]["back"] = {"step": 1, "text": "Like the sky."}  # shares neither card nor paint
        bad["steps"]["block-rug"] = {"back": {"step": 3, "text": "As the cat."}}  # not an earlier step
        bad["steps"]["cat-eyes"]["back"]["text"] = "The same dark paint as the Rug red shadows."  # not its paint
        bad["steps"]["block-cat"]["back"]["text"] = "The cat is about 9 in wide, like the rug."  # check-text fails
        write("arc.json", bad)
        code, r = self.tool("check-text", "--arc")
        self.assertEqual((code, r["send_back"]), (0, "arc-fix.json"), r)
        fb = (folder / "arc-feedback.md").read_text()
        for said in ("`glazing` isn't a stroke card this lesson uses", "steps [6] don't use the card `curved-strokes`",
                     "right side of the cat", "about 12 in wide", "stage the-finish.for: missing",
                     "step 1 shares neither this step's stroke card", "step 3 isn't an earlier step",
                     "names Rug red, which isn't one of its paints", "9 in"):
            self.assertIn(said, fb)
        self.assertEqual(r["first"], {"arc": 9, "back_check_text": 1})
        # the whole arc again, with two faults left: they are taken out, and nothing else is
        again = json.loads(json.dumps(good))
        again["opening"]["road"] += " Finish on the right side of the cat."
        again["steps"]["light-cat"]["back"] = {"step": 1, "text": "Like the sky."}
        write("arc-fix.json", again)
        code, r = self.tool("check-text", "--arc", "--final")
        self.assertEqual((r["ok"], r["taken_out"], r["left_failing"], r["back_lines"]), (True, 2, 0, 2), r)
        t = json.loads((self.lesson / "text.json").read_text())
        self.assertEqual(t["opening"]["road"], good["opening"]["road"])
        self.assertEqual(t["stages"]["the-shapes"], good["stages"]["the-shapes"])
        by = {x["stage_id"]: x for x in t["steps"]}
        self.assertEqual([x["kind"] for x in by["block-cat"]["lines"]], ["start", "back", "strokes", "inside", "leave",
                                                                        "stop"])
        self.assertEqual(by["block-cat"]["lines"][1]["step"], 2)
        self.assertFalse(any(x["kind"] == "back" for x in by["light-cat"]["lines"]))
        self.assertEqual(len(json.loads((folder / "arc-dropped.json").read_text())), 2)


if __name__ == "__main__":
    unittest.main()
