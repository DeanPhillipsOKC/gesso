"""Tests for spike S7 (#172, spike/experiments/v3_plan_first.py): the painter's plan, the fit that carries it through
v2's tools, the fold back into the painter's steps, and how much two plans differ (docs/spikes/v3-plan-first.md).
Made-up plans and a made-up lesson folder: no renders, no network, no model files."""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE.parent / "experiments" / "bench"))

from PIL import Image  # noqa: E402

import benchlib  # noqa: E402
import checks  # noqa: E402
import v3_plan_first as pf  # noqa: E402

TECH = {"v2_step_range": [3, 6], "v2_stage_range": [2, 3]}
ELEMENTS = {"sky-blend", "simple-shape", "furry-animal"}
STROKES = {"side-to-side-blend", "build-from-pieces", "glazing", "dabbing"}


def painter() -> dict:
    """A sky, a rug and a cat: three coats, then one shadow step across the rug and the cat, then the cat's lights."""

    def step(i, name, things, paints, stroke, brush="1/2 inch flat", **more):
        return {"id": i, "name": name, "lays": [{"thing": t, "what": f"the {t}"} for t in things], "paints": paints,
                "stroke": stroke, "brush": brush, "after": f"{name} is done", **more}

    return {"plan_first": 1, "picture": "made-up",
            "things": [{"id": "sky", "name": "The sky", "element": "sky-blend", "why": "blended wet"},
                       {"id": "rug", "name": "The rug", "element": "simple-shape", "why": "one flat shape"},
                       {"id": "cat", "name": "The cat", "element": "furry-animal", "why": "short fur"}],
            "paints": [{"name": n, "looks": n} for n in ("Sky blue", "Mustard", "Cat gray", "Shadow", "Cat white")],
            "stages": [
                {"id": "coats", "name": "The big shapes", "steps": [
                    step("sky-blend", "Blend the sky", ["sky"], ["Sky blue"], "side-to-side-blend", blend=True),
                    step("rug-coat", "Block in the rug", ["rug"], ["Mustard"], "build-from-pieces"),
                    step("cat-coat", "Block in the cat", ["cat"], ["Cat gray"], "build-from-pieces")]},
                {"id": "finish", "name": "Shadows and lights", "steps": [
                    step("shadows", "Glaze the shadows", ["rug", "cat"], ["Shadow"], "glazing"),
                    step("cat-light", "Dab the white chest", ["cat"], ["Cat white"], "dabbing", "#6 round")]}]}


def fitted() -> dict:
    """The painter's plan as a version 2 plan: the shadow step is two v2 steps, and the cat has a part for its chest."""

    def step(i, of, part, show, paint, stroke, brush="1/2 inch flat"):
        return {"id": i, "of": of, "name": i, "part": part, "show": show, "paints": [paint], "stroke": stroke,
                "brush": brush}

    return {"plan_version": 2,
            "parts": [{"id": "sky", "name": "The sky", "kind": "area", "box": [0, 0, 1, 1], "thing": "sky"},
                      {"id": "rug", "name": "The rug", "kind": "object", "box": [0.1, 0.6, 0.9, 0.9], "thing": "rug"},
                      {"id": "cat", "name": "The cat", "kind": "object", "box": [0.3, 0.3, 0.7, 0.7], "thing": "cat"},
                      {"id": "chest", "name": "The white chest", "kind": "object", "parent": "cat",
                       "box": [0.3, 0.5, 0.4, 0.7], "thing": "cat"}],
            "paints": [],
            "stages": [
                {"id": "coats", "name": "The big shapes", "steps": [
                    step("v-sky", "sky-blend", "sky", "blend", "sky-1", "side-to-side-blend"),
                    step("v-rug", "rug-coat", "rug", "flat", "rug-1", "build-from-pieces"),
                    step("v-cat", "cat-coat", "cat", "flat", "cat-1", "build-from-pieces")]},
                {"id": "finish", "name": "Shadows and lights", "steps": [
                    step("v-shade-rug", "shadows", "rug", "pass", "rug-2", "glazing"),
                    step("v-shade-cat", "shadows", "cat", "pass", "cat-2", "glazing"),
                    step("v-chest", "cat-light", "chest", "full", "cat-3", "dabbing", "#6 round")]}]}


def problems(p: dict) -> list[str]:
    return pf.painter_problems(p, TECH, ELEMENTS, STROKES)


class PainterTests(unittest.TestCase):
    def test_a_good_plan_has_no_problems(self):
        self.assertEqual(problems(painter()), [])
        self.assertEqual([s["id"] for s in pf.crossing(painter())], ["shadows"])

    def test_each_fault_is_named(self):
        cases = {
            "isn't in things": lambda p: p["stages"][0]["steps"][1]["lays"].append({"thing": "dog", "what": "x"}),
            "no step lays paint on it": lambda p: p["things"].append(
                {"id": "sun", "name": "The sun", "element": "simple-shape"}),
            "isn't in techniques/elements": lambda p: p["things"][0].update(element="made-up"),
            "isn't a card": lambda p: p["stages"][0]["steps"][0].update(stroke="swirl"),
            "paints in one step": lambda p: p["stages"][0]["steps"][1].update(
                paints=["Sky blue", "Mustard", "Cat gray", "Shadow"]),
            "isn't in the plan's paints": lambda p: p["stages"][0]["steps"][1].update(paints=["Teal"]),
            "no `after`": lambda p: p["stages"][0]["steps"][0].pop("after"),
            "twice": lambda p: p["stages"][1]["steps"][0]["lays"].append({"thing": "cat", "what": "again"}),
            "no other stage or step has": lambda p: p["stages"][1]["steps"][1].update(id="shadows"),
            "name its brush": lambda p: p["stages"][0]["steps"][0].pop("brush"),
        }
        for words, break_it in cases.items():
            p = painter()
            break_it(p)
            self.assertTrue(any(words in x for x in problems(p)), (words, problems(p)))

    def test_a_blend_may_have_more_than_three_paints(self):
        p = painter()
        p["stages"][0]["steps"][0]["paints"] = ["Sky blue", "Mustard", "Cat gray", "Shadow"]
        self.assertEqual(problems(p), [])

    def test_step_and_stage_counts_follow_the_technique(self):
        p = painter()
        p["stages"][1]["steps"] = []
        out = problems(p)
        self.assertTrue(any("stage needs at least one step" in x for x in out), out)
        p["stages"] = p["stages"][:1]
        p["stages"][0]["steps"] = p["stages"][0]["steps"][:2]
        out = problems(p)
        self.assertTrue(any("2 steps; the technique wants 3 to 6" in x for x in out), out)
        self.assertTrue(any("1 stages; the technique wants 2 to 3" in x for x in out), out)

    def test_the_real_library_loads(self):
        out = pf.painter_problems(painter())  # the real technique, elements and cards
        self.assertFalse(any("element" in x or "card" in x for x in out), out)

    def test_the_brief_names_real_files(self):
        brief = (HERE.parent / "experiments" / "v3_plan_first_painter.md").read_text(encoding="utf-8")
        for path in ("techniques/acrylic-paint-along-beginner.yaml", "docs/research/acrylic-paint-along.md",
                     "techniques/elements", "techniques/strokes"):
            self.assertIn(path, brief)
            self.assertTrue((pf.ROOT / path).exists(), path)


class FitTests(unittest.TestCase):
    def test_a_fit_that_carries_the_plan(self):
        self.assertEqual(pf.fit_problems(painter(), fitted()), [])
        self.assertEqual([(of, [s["id"] for s in subs]) for of, subs in pf.groups_of(fitted())][3],
                         ("shadows", ["v-shade-rug", "v-shade-cat"]))
        d = pf.deviations(painter(), fitted())
        self.assertEqual((d["painter_steps"], d["fitted_steps"], d["v2_steps"], d["crossing_steps"]), (5, 5, 6, 1))

    def break_and_find(self, words, break_it):
        plan = fitted()
        break_it(plan)
        out = pf.fit_problems(painter(), plan)
        self.assertTrue(any(words in x for x in out), (words, out))

    def test_every_part_says_its_thing(self):
        self.break_and_find("which of the painter's things", lambda p: p["parts"][1].pop("thing"))

    def test_every_thing_needs_a_part_or_a_reason(self):
        def no_rug(p):
            p["parts"][1]["thing"] = "sky"
        self.break_and_find("thing rug: no part carries it", no_rug)
        plan = fitted()
        no_rug(plan)
        plan["things_dropped"] = {"rug": "too thin to outline; the sky carries it"}
        plan["stages"][0]["steps"].pop(1)  # the rug's coat
        plan["stages"][1]["steps"].pop(0)
        plan["painter_dropped"] = {"rug-coat": "no rug part"}
        self.assertEqual(pf.fit_problems(painter(), plan), [])

    def test_every_step_names_a_painters_step_in_its_stage(self):
        self.break_and_find("`of` must name", lambda p: p["stages"][0]["steps"][0].update(of="nope"))
        self.break_and_find("Keep the painter's stages", lambda p: p["stages"][0]["steps"][0].update(of="cat-light"))

    def test_the_painters_order_and_stages_are_kept(self):
        self.break_and_find("Keep the painter's order", lambda p: p["stages"][0]["steps"].reverse())
        self.break_and_find("Same ids, same order", lambda p: p["stages"].reverse())

    def test_a_painters_step_is_one_run_and_one_move(self):
        plan = fitted()
        plan["stages"][1]["steps"].append({**plan["stages"][1]["steps"][0], "id": "again"})
        out = pf.fit_problems(painter(), plan)
        self.assertTrue(any("aren't in a row" in x for x in out), out)
        self.break_and_find("different strokes or brushes",
                            lambda p: p["stages"][1]["steps"][1].update(brush="#4 round"))

    def test_a_lay_the_fit_leaves_out_needs_a_reason(self):
        self.break_and_find("no v2 step of it does", lambda p: p["stages"][1]["steps"].pop(1))
        plan = fitted()
        plan["stages"][1]["steps"].pop(1)
        plan["lays_dropped"] = {"shadows": "the cat's shadow is too close to its coat to split"}
        self.assertEqual(pf.fit_problems(painter(), plan), [])
        self.assertEqual(pf.deviations(painter(), plan)["crossing_steps"], 0)

    def test_a_step_may_not_paint_a_thing_the_painter_didnt_name(self):
        self.break_and_find("which the painter's step doesn't name",
                            lambda p: p["stages"][0]["steps"][1].update(part="cat"))

    def test_a_painters_step_with_no_v2_step_needs_a_reason(self):
        self.break_and_find("the painter's step has no v2 step", lambda p: p["stages"][1]["steps"].pop(2))

    def test_the_checks_left_out_are_the_ones_v2_prints(self):
        plan = {"stages": [{"id": "a", "steps": [{"id": "s"}]}]}
        for line in checks.counts(plan, {"v2_step_range": [12, 24], "v2_stage_range": [4, 9]}):
            self.assertTrue(pf.RANGE.match(line), line)
        out = checks.text_problems({"stages": [{"steps": [{"id": "v-shade-cat", "name": "x"}]}]},
                                   {"v-shade-cat": {"lines": [{"kind": "how", "text": "x"}]}}, None)
        self.assertEqual(sorted(pf.UNWRITTEN.match(x)["id"] for x in out if pf.UNWRITTEN.match(x)),
                         ["v-shade-cat", "v-shade-cat"], out)


class FoldTests(unittest.TestCase):
    def test_step_numbers_follow_the_fold(self):
        number_of = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 5}
        self.assertEqual(pf.renumber("Leave what steps 2 and 5 painted showing.", number_of, 5),
                         "Leave what steps 2 and 4 painted showing.")
        self.assertEqual(pf.renumber("Mix enough Shadow for this step and steps 5 and 6; cover it.", number_of, 4),
                         "Mix enough Shadow for this step and step 5; cover it.")
        self.assertEqual(pf.renumber("Leave what step 4 painted showing.", number_of, 4), "")  # its own step
        self.assertEqual(pf.renumber("Leave what steps 4, 5, and 6 painted showing.", number_of, 5),
                         "Leave what step 4 painted showing.")
        self.assertEqual(pf.renumber("Tap straight down. 3 taps.", number_of, 2), "Tap straight down. 3 taps.")

    def subs(self):
        def line(kind, text):
            return {"kind": kind, "text": text}
        return [{"part_name": "the rug", "lines": [line("dry", "Let the rug dry."), line("where", "Rug where."),
                                                   line("paints", "Paint: Shadow."), line("how", "Brush: flat."),
                                                   line("how", "Thin paint."), line("result", "A thin veil."),
                                                   line("result", "Leave what step 2 painted showing.")]},
                {"part_name": "the cat", "lines": [line("dry", "Let the cat dry."), line("where", "Cat where."),
                                                   line("where", "Cat where, more."),
                                                   line("paints", "Paint: Shadow."), line("how", "Brush: flat."),
                                                   line("how", "Thin paint."), line("result", "A thin veil."),
                                                   line("result", "Leave what steps 3 and 4 painted showing."),
                                                   line("step-back", "Step back.")]}]

    def test_lines_fold_kind_by_kind(self):
        out = pf.fold_lines(self.subs(), {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 5}, 4)
        self.assertEqual([x["text"] for x in out], [
            "Let the rug dry.", "Let the cat dry.",
            "The rug: Rug where.", "The cat: Cat where.", "The cat: Cat where, more.",
            "Paint: Shadow.", "Brush: flat.", "Thin paint.", "A thin veil.",
            "Leave what steps 2 and 3 painted showing.", "Step back."])  # one sentence about both parts' steps
        self.assertEqual([x["kind"] for x in out][:5], ["dry", "dry", "where", "where", "where"])

    def test_one_parts_lines_arent_led_by_its_name(self):
        out = pf.fold_lines(self.subs()[1:], {}, 9)
        self.assertEqual([x["text"] for x in out if x["kind"] == "where"], ["Cat where.", "Cat where, more."])

    def lesson(self, folder: Path) -> Path:
        """A fitted lesson folder as publish leaves it, with flat pictures a test can tell apart."""
        lesson = folder / "made-up_skill_1-plan-first"
        (lesson / "canvas").mkdir(parents=True)
        plan = fitted()
        stages = []
        for i, s in enumerate(s for st in plan["stages"] for s in st["steps"]):
            image = f"canvas/{i + 1:02d}_{s['id']}.png"
            Image.new("RGB", (8, 6), (i * 30, 0, 0)).save(lesson / image)
            stages.append({"id": s["id"], "name": s["name"], "image": image, "brushes": s["brush"],
                           "lines": [{"kind": "where", "text": f"Where {s['part']}."},
                                     {"kind": "how", "text": f"Brush: {s['brush']}."}],
                           "tip": "Shade both." if s["id"] == "v-shade-rug" else "",
                           "summary": f"Summary of {s['id']}",
                           "colors": [{"name": s["paints"][0], "hex": "#101010", "recipe": "r"}]})
        stages[4]["colors"] = stages[3]["colors"]  # the two shadow steps share one paint
        (lesson / "lesson.json").write_text(json.dumps({"stages": stages, "canvas": {"w_in": 8, "h_in": 6}}))
        (lesson / "plan.json").write_text(json.dumps(plan))
        (lesson / "painter.json").write_text(json.dumps(painter()))
        (lesson / "canvas.json").write_text(json.dumps({"canvas_box": [0, 0, 1, 1]}))
        (lesson / "bench.json").write_text(json.dumps({"picture": "made-up"}))
        Image.new("RGB", (8, 6)).save(lesson / "99_finish.png")
        return lesson

    def test_the_folded_lesson_is_the_painters_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson = self.lesson(Path(tmp))
            r = pf.fold(lesson)
            self.assertEqual((r["steps"], r["v2_steps"], r["crossing_steps"]), (5, 6, 1))
            folded = Path(r["folded"])
            self.assertEqual(folded.name, lesson.name + "-folded")
            self.assertEqual(benchlib.picture_of(folded), "made-up")
            steps = benchlib.lesson_steps(folded)  # what the A/B page and the packet read
            self.assertEqual([s["id"] for s in steps], ["sky-blend", "rug-coat", "cat-coat", "shadows", "cat-light"])
            self.assertEqual([s["group"] for s in steps], ["The big shapes"] * 3 + ["Shadows and lights"] * 2)
            shadows = steps[3]
            self.assertEqual(shadows["name"], "Glaze the shadows")  # the painter's name for it
            self.assertEqual(shadows["lines"], ["The rug: Where rug.", "The cat: Where cat.", "Brush: 1/2 inch flat."])
            self.assertEqual(shadows["tip"], "Shade both.")
            self.assertEqual([c["name"] for c in shadows["paints"]], ["rug-2"])  # one paint, said once
            self.assertEqual(shadows["brushes"], "1/2 inch flat")
            # its picture is the canvas after its last v2 step (the fifth)
            self.assertEqual(Image.open(shadows["image"]).getpixel((0, 0)), (120, 0, 0))
            data = json.loads((folded / "lesson.json").read_text())
            self.assertEqual(data["stages"][3]["v2_steps"], ["v-shade-rug", "v-shade-cat"])
            self.assertEqual(data["stages"][3]["summary"], "Summary of v-shade-rug")
            self.assertTrue((folded / "99_finish.png").exists())

    def test_fold_refuses_a_fit_that_left_the_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson = self.lesson(Path(tmp))
            plan = fitted()
            plan["stages"][1]["steps"].pop(2)
            (lesson / "plan.json").write_text(json.dumps(plan))
            with self.assertRaises(SystemExit):
                pf.fold(lesson)

    def test_fold_refuses_a_lesson_published_for_another_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            lesson = self.lesson(Path(tmp))
            data = json.loads((lesson / "lesson.json").read_text())
            data["stages"].pop()
            (lesson / "lesson.json").write_text(json.dumps(data))
            with self.assertRaises(SystemExit):
                pf.fold(lesson)


class StartTests(unittest.TestCase):
    def test_start_seeds_the_baselines_layers_and_no_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            run = tmp / "runs" / "made-up_skill_1"
            (run / "parts").mkdir(parents=True)
            (run / "parts" / "owner.png").write_bytes(b"png")
            (run / "98_background.png").write_bytes(b"png")
            base = {**fitted(), "technique": pf.TECHNIQUE, "subject": "a cat", "photo": "output/x/photo.png",
                    "paints": [{"id": "sky-1", "name": "Sky blue", "hex": "#88aacc"}]}
            (run / "plan.json").write_text(json.dumps(base))
            (tmp / "painter.json").write_text(json.dumps(painter()))

            def build(picture, into, name=None, **_):
                folder = Path(into) / name
                folder.mkdir(parents=True)
                (folder / "bench.json").write_text(json.dumps({"picture": picture, "plan_photo": "bench/photo.jpg"}))
                return folder

            with mock.patch("bench.build", build), mock.patch.object(pf, "baseline_run", lambda p, runs: run), \
                    mock.patch.object(pf, "painter_problems", lambda p: []):
                folder = pf.start("made-up", tmp / "painter.json", tmp / "out", tmp / "runs")
            self.assertEqual(folder.name, "made-up_skill_1-plan-first")
            plan = json.loads((folder / "plan.json").read_text())
            self.assertEqual(plan["stages"], [])
            self.assertEqual([p["id"] for p in plan["parts"]], ["sky", "rug", "cat", "chest"])
            self.assertEqual(plan["paints"], base["paints"])
            self.assertEqual(plan["photo"], "bench/photo.jpg")  # the bench's photo, not the baseline run's
            self.assertEqual(json.loads((folder / "painter.json").read_text()), painter())
            self.assertTrue((folder / "parts" / "owner.png").exists() and (folder / "98_background.png").exists())

    def test_start_refuses_a_painters_plan_with_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = painter()
            bad["things"] = []
            (Path(tmp) / "painter.json").write_text(json.dumps(bad))
            with self.assertRaises(SystemExit):
                pf.start("made-up", Path(tmp) / "painter.json", Path(tmp) / "out")


class DifferTests(unittest.TestCase):
    def test_a_plan_is_the_same_as_itself(self):
        a = pf.shape(painter())
        d = pf.differ(a, a)
        self.assertEqual((d["things"], d["order"], d["sequence"], d["moves"]), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(d["a"], {"steps": 5, "stages": 2, "crossing": 1})

    def test_a_fitted_plan_has_its_painters_shape(self):
        names = {"chest": "cat"}  # the fit's extra part is the painter's cat
        fit = pf.shape(fitted(), names)
        self.assertEqual([s["things"] for s in fit], [["sky"], ["rug"], ["cat"], ["cat", "rug"], ["cat"]])
        d = pf.differ(pf.shape(painter()), fit)
        self.assertEqual((d["things"], d["order"], d["sequence"], d["moves"]), (1.0, 1.0, 1.0, 1.0))

    def test_a_v2_plan_is_one_thing_a_step(self):
        v2 = copy.deepcopy(fitted())
        for s in (s for st in v2["stages"] for s in st["steps"]):
            s.pop("of")
        shape = pf.shape(v2, {"chest": "cat"})
        self.assertEqual(len(shape), 6)
        d = pf.differ(pf.shape(painter()), shape)
        self.assertEqual((d["a"]["crossing"], d["b"]["crossing"]), (1, 0))
        self.assertEqual((d["things"], d["order"]), (1.0, 1.0))
        self.assertLess(d["sequence"], 1.0)

    def test_order_and_names(self):
        a = pf.shape(painter())
        b = copy.deepcopy(painter())
        b["stages"][0]["steps"].reverse()  # cat, rug, sky
        d = pf.differ(a, pf.shape(b))
        self.assertEqual(d["order"], -1.0)
        c = copy.deepcopy(painter())
        for t in c["things"]:
            t["id"] = "x-" + t["id"]
        for s in pf.painter_steps(c):
            for lay in s["lays"]:
                lay["thing"] = "x-" + lay["thing"]
        d = pf.differ(a, pf.shape(c))
        self.assertEqual((d["things"], d["order"]), (0.0, None))
        d = pf.differ(a, pf.shape(c, {"x-sky": "sky", "x-rug": "rug", "x-cat": "cat"}))
        self.assertEqual((d["things"], d["order"], d["moves"]), (1.0, 1.0, 1.0))
        c["things"].append({"id": "sun", "name": "Sun", "element": "simple-shape"})
        c["stages"][1]["steps"][1]["lays"].append({"thing": "sun", "what": "x"})
        d = pf.differ(a, pf.shape(c, {"x-sky": "sky", "x-rug": "rug", "x-cat": "cat"}))
        self.assertEqual((d["things"], d["only_b"]), (0.75, ["sun"]))


if __name__ == "__main__":
    unittest.main()
