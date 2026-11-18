"""Tests for the version 3 plan (spike/plan3.py, `plan-check`; docs/design/pipeline-v3.md section 5): its problems,
its notes and its units. A made-up plan, and the three plans the v3 spikes ran on (fixtures/plans3/, the painter's
plans of #172 with what #210 and #214 wrote by hand folded in). No renders, no network, no model files."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import plan3  # noqa: E402
import tools  # noqa: E402

TECH = {"v2_step_range": [3, 9], "v2_stage_range": [2, 4], "max_mixes": 4}
ELEMENTS = {"sky-blend": {"steps": [{"strokes": "side-to-side-blend"}]},
            "simple-shape": {"steps": [{"strokes": ["build-from-pieces", "glazing"]}]},
            "furry-animal": {"steps": [{"strokes": ["build-from-pieces"]}, {"strokes": ["glazing", "dabbing"]}]}}
STROKES = {"side-to-side-blend", "build-from-pieces", "glazing", "dabbing", "liner-lines"}
PLANS = HERE / "fixtures" / "plans3"


def plan() -> dict:
    """A sky, a rug and a cat. The rug and the cat are blocked in, one shadow step crosses both, then the cat's
    lights and its eyes."""

    def step(i, name, things, paints, stroke, **more):
        return {"id": i, "name": name, "lays": [{"thing": t, "what": f"the {t}"} for t in things], "paints": paints,
                "stroke": stroke, "brush": "1/2 inch flat", "after": f"{name} is done.", **more}

    return {"plan_version": 3, "technique": "techniques/acrylic-paint-along-beginner.yaml",
            "things": [{"id": "sky", "name": "The sky", "element": "sky-blend", "why": "blended wet", "behind": []},
                       {"id": "rug", "name": "The rug", "element": "simple-shape", "why": "one flat shape",
                        "behind": [], "plain": "the plain red rug"},
                       {"id": "cat", "name": "The cat", "element": "furry-animal", "why": "fur", "behind": ["rug", "sky"],
                        "plain": "the plain gray cat shape"}],
            "paints": [{"name": "Sky blue", "looks": "a light blue", "color": "#9cc4e8"},
                       {"name": "Rug red", "looks": "a dull red", "color": "#a3352c"},
                       {"name": "Cat gray", "looks": "a middle gray", "color": "#8a8a8a"},
                       {"name": "Shadow", "looks": "a dark brown", "color": "#3a2a22"},
                       {"name": "Pale gray", "looks": "Cat gray with white", "color": "#c9c9c9", "of": "Cat gray"}],
            "stages": [
                {"id": "the-sky", "name": "The sky", "steps": [
                    step("blend-sky", "Blend the sky", ["sky"], ["Sky blue"], "side-to-side-blend", blend=True)]},
                {"id": "the-shapes", "name": "The shapes", "steps": [
                    step("block-rug", "Block in the rug", ["rug"], ["Rug red"], "build-from-pieces", block_in=True),
                    step("block-cat", "Block in the cat", ["cat"], ["Cat gray"], "build-from-pieces", block_in=True)]},
                {"id": "the-finish", "name": "Shadows and lights", "steps": [
                    step("shadows", "Glaze the shadows", ["rug", "cat"], ["Shadow"], "glazing", unit="The shadows"),
                    step("light-cat", "Light the cat", ["cat"], ["Pale gray"], "dabbing"),
                    step("cat-eyes", "Dot the eyes", ["cat"], ["Shadow"], "dabbing", unit="The cat's eyes")]}]}


def check(p: dict, tech: dict | None = TECH) -> list[str]:
    return plan3.problems(p, tech, elements=ELEMENTS, strokes=STROKES)


def step(p: dict, sid: str) -> dict:
    return next(s for st in p["stages"] for s in st["steps"] if s["id"] == sid)


class UnitsTests(unittest.TestCase):
    def test_the_made_up_plan_has_no_problems(self):
        self.assertEqual(check(plan()), [])

    def test_one_unit_a_run_of_steps_on_a_thing_a_block_in_alone_and_a_step_with_no_new_paint_alone(self):
        us = plan3.units(plan())
        self.assertEqual([(u["id"], u["kind"], u["steps"]) for u in us],
                         [("sky", "first", [0]), ("rug", "bare", [1]), ("cat", "behind", [2]),
                          ("the-shadows", "back", [3, 4]), ("the-cat-s-eyes", "back", [5])])
        self.assertEqual(us[3]["things"], ["rug", "cat"])
        self.assertEqual(us[2]["name"], "The cat")

    def test_a_step_that_comes_back_to_a_thing_takes_the_units_between_with_it(self):
        p = plan()
        p["stages"][1]["steps"].append(dict(step(p, "light-cat"), id="rug-fringe", lays=[{"thing": "rug", "what": "x"}],
                                            paints=["Pale gray"]))
        del step(p, "block-cat")["block_in"]
        us = plan3.units(p)
        # the rug's block-in is alone; the cat's coat and the rug's fringe are one run, since the stage came back
        # to the rug after the cat
        self.assertEqual([u["steps"] for u in us][:3], [[0], [1], [2, 3]])
        self.assertEqual(us[2]["things"], ["cat", "rug"])
        self.assertEqual(us[2]["kind"], "back")

    def test_a_thing_new_on_things_already_painted_is_behind_and_on_canvas_is_bare(self):
        p = plan()
        self.assertEqual({u["id"]: u["kind"] for u in plan3.units(p)}["cat"], "behind")
        p["things"][2]["behind"] = []
        self.assertEqual({u["id"]: u["kind"] for u in plan3.units(p)}["cat"], "bare")

    def test_things_of_names_each_thing_once(self):
        self.assertEqual(plan3.things_of({"lays": [{"thing": "a"}, {"thing": "b"}, {"thing": "a"}]}), ["a", "b"])


class ProblemsTests(unittest.TestCase):
    def one(self, p: dict, *words: str, tech: dict | None = TECH) -> str:
        """The plan's only problem, which says every one of `words`."""
        found = check(p, tech)
        self.assertEqual(len(found), 1, found)
        for w in words:
            self.assertIn(w, found[0])
        return found[0]

    def test_a_thing_must_say_what_is_behind_it(self):
        p = plan()
        del p["things"][0]["behind"]
        self.one(p, "sky", "`behind`", "[]")

    def test_what_is_behind_a_thing_is_painted_before_it(self):
        p = plan()
        p["things"][1]["behind"] = ["cat"]
        self.one(p, "rug", "cat", "step 3", "Back to front")
        p["things"][1]["behind"] = ["floor"]
        self.one(p, "rug", "'floor'", "isn't another thing")

    def test_a_block_in_is_a_things_first_coat(self):
        p = plan()
        step(p, "light-cat")["block_in"] = True
        self.assertTrue(any("first coat" in x and "light-cat" in x for x in check(p)))

    def test_a_block_in_is_not_a_blend(self):
        p = plan()
        step(p, "block-rug")["blend"] = True
        self.one(p, "block-rug", "blend")

    def test_a_block_in_needs_a_step_that_finishes_the_thing(self):
        p = plan()
        p["stages"][2]["steps"] = [dict(step(p, "light-cat"), unit="The cat's lights")]
        p["paints"] = [x for x in p["paints"] if x["name"] != "Shadow"]
        del p["things"][1]["plain"]
        self.one(p, "block-rug", "never look finished", tech=None)

    def test_a_unit_that_is_not_one_new_thing_needs_a_name(self):
        p = plan()
        del step(p, "shadows")["unit"]
        self.one(p, "shadows", "`unit`", "comes back to rug, cat")
        p = plan()
        step(p, "cat-eyes")["unit"] = "The cat"
        self.one(p, "cat-eyes", "already the name")
        step(p, "cat-eyes")["unit"] = "the shadows"
        self.one(p, "cat-eyes", "already the name")
        p = plan()
        step(p, "light-cat")["unit"] = "The cat's lights"
        self.one(p, "light-cat", "never read", "shadows")

    def test_a_thing_painted_in_several_units_says_how_it_looks_plain(self):
        p = plan()
        del p["things"][2]["plain"]
        self.one(p, "cat", "`plain`", "3 units")
        p["things"][2]["plain"] = " "
        self.assertTrue(any("short phrase" in x for x in check(p)))

    def test_a_paint_needs_a_rough_color_and_a_step(self):
        p = plan()
        p["paints"][0]["color"] = "blue"
        self.one(p, "'Sky blue'", "`color`", "hex")
        p = plan()
        p["paints"].append({"name": "Spare", "looks": "x", "color": "#112233"})
        self.one(p, "'Spare'", "no step uses it", tech=None)

    def test_a_version_of_a_paint_names_a_paint_that_is_not_a_version(self):
        p = plan()
        p["paints"][3]["of"] = "Pale gray"
        self.one(p, "'Shadow'", "'Pale gray'")

    def test_a_steps_paints_are_in_the_plan_and_at_most_three_unless_blended(self):
        p = plan()
        step(p, "light-cat")["paints"] = ["Pale gray", "Cat gray", "Shadow", "Rug red"]
        self.one(p, "light-cat", "4 paints", "blend")
        step(p, "light-cat")["paints"] = ["Cream"]
        self.assertTrue(any("'Cream' isn't in the plan's paints" in x for x in check(p)))

    def test_a_stroke_is_a_card_its_things_element_lists(self):
        p = plan()
        step(p, "light-cat")["stroke"] = "liner-lines"
        self.one(p, "light-cat", "'liner-lines'", "furry-animal", "build-from-pieces, dabbing, glazing")
        step(p, "light-cat")["stroke"] = "scumble"
        self.one(p, "light-cat", "isn't a card")

    def test_the_techniques_ranges(self):
        found = check(plan(), {"v2_step_range": [12, 24], "v2_stage_range": [4, 9]})
        self.assertEqual(found, ["the plan has 6 steps; the technique wants 12 to 24",
                                 "the plan has 3 stages; the technique wants 4 to 9"])

    def test_above_the_mix_target_two_close_paints_are_a_problem_and_far_ones_are_a_note(self):
        p = plan()
        self.assertEqual(plan3.notes(p, TECH)["mixes"], 4)  # Pale gray is a version of Cat gray: not counted
        self.assertEqual(plan3.notes(p, TECH)["versions"], 1)
        del p["paints"][4]["of"]
        self.assertEqual(check(p), [])  # five mixes over a target of four, and none close: allowed
        self.assertIn("above the target of 4", plan3.notes(p, TECH)["over_target"])
        p["paints"][4]["color"] = "#8f8d8a"
        self.one(p, "5 paints to mix", "'Cat gray' and 'Pale gray'", "`of`")
        self.assertNotIn("over_target", plan3.notes(p, TECH))
        self.assertEqual(check(p, None), [])  # no technique, no target

    def test_a_paint_used_again_after_it_dried_is_listed(self):
        again = plan3.notes(plan(), TECH)["mix_again"]
        self.assertEqual(again, [])  # Shadow is used in steps 4 and 6: two apart
        p = plan()
        step(p, "cat-eyes")["paints"] = ["Rug red"]
        self.assertEqual(plan3.notes(p, TECH)["mix_again"], [{"paint": "Rug red", "steps": [2, 6], "mix_again_at": [6]}])

    def test_ids_things_and_steps(self):
        self.assertEqual(check({"plan_version": 3}), ["the plan lists no things"])
        p = plan()
        p["stages"] = []
        self.assertEqual(check(p), ["the plan has no stages with steps"])
        p = plan()
        step(p, "light-cat")["id"] = "the-sky"
        step(p, "cat-eyes")["lays"] = [{"thing": "dog", "what": "x"}]
        del step(p, "block-rug")["after"]
        found = check(p)
        self.assertTrue(any("'the-sky' must be a lowercase slug no other" in x for x in found))
        self.assertTrue(any("lays on 'dog'" in x for x in found))
        self.assertTrue(any("block-rug: no `after`" in x for x in found))


class BenchPlansTests(unittest.TestCase):
    """The three plans the spikes' chains were made from."""

    def test_they_fit_every_rule_but_the_mix_target(self):
        import yaml

        tech = yaml.safe_load((tools.ROOT / "techniques" / "acrylic-paint-along-beginner.yaml").read_text())
        for path in sorted(PLANS.glob("*.json")):
            p = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(plan3.problems(p, {k: v for k, v in tech.items() if k != "max_mixes"}), [], path.name)
            # written before the plan was held to a count (#219, open): 13 to 22 mixes, two of them close
            found = plan3.problems(p, tech)
            self.assertEqual(len(found), 1, path.name)
            self.assertIn("above the technique's target of 10", found[0])

    def test_their_units(self):
        want = {"highland-cow": 16, "sleeping-cat": 15, "birch-grove": 19}
        for name, n in want.items():
            us = plan3.units(json.loads((PLANS / f"{name}.json").read_text(encoding="utf-8")))
            self.assertEqual(len(us), n, name)
            self.assertTrue(all(u["id"] and u["name"] for u in us), name)
            self.assertEqual(len({u["id"] for u in us}), n, name)
            self.assertEqual(sorted(i for u in us for i in u["steps"]), list(range(sum(len(u["steps"]) for u in us))))
        cat = plan3.units(json.loads((PLANS / "sleeping-cat.json").read_text(encoding="utf-8")))
        self.assertEqual([u["kind"] for u in cat], ["first", "behind", "bare", "behind", "back", "bare", "back", "behind",
                                                    "back", "back", "behind", "back", "back", "back", "back"])


class PlanCheckToolTests(unittest.TestCase):
    def run_tool(self, p: dict) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plan.json").write_text(json.dumps(p), encoding="utf-8")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = tools.main(["plan-check", "--lesson", tmp])
            return code, json.loads(buf.getvalue())

    def test_it_prints_problems_units_and_the_paint_count(self):
        code, r = self.run_tool(json.loads((PLANS / "sleeping-cat.json").read_text(encoding="utf-8")))
        self.assertEqual(code, 0)
        self.assertFalse(r["ok"])
        self.assertEqual((r["steps"], r["stages"], r["renders"], r["mixes"], r["max_mixes"]), (23, 8, 14, 22, 10))
        self.assertEqual(r["units"][7], {"unit": 7, "id": "blanket", "name": "The yellow knitted blanket",
                                         "kind": "behind", "things": ["blanket"], "steps": ["block-the-blanket"]})
        self.assertEqual(r["cost_usd"], 0.0)

    def test_it_refuses_a_version_2_plan_and_a_plan_with_no_technique(self):
        code, r = self.run_tool({"plan_version": 2})
        self.assertEqual(code, 2)
        self.assertIn("isn't a version 3 plan", r["refused"])
        p = plan()
        p["technique"] = "techniques/nope.yaml"
        code, r = self.run_tool(p)
        self.assertEqual(code, 2)
        self.assertIn("technique", r["refused"])

    def test_the_version_2_tools_refuse_a_version_3_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "plan.json").write_text(json.dumps(plan()), encoding="utf-8")
            self.assertEqual(plan3.version(Path(tmp)), 3)
            self.assertTrue(plan3.is_v3(Path(tmp)))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = tools.main(["build-steps", "--lesson", tmp])
            self.assertEqual(code, 2)
            self.assertIn("isn't a version 2 plan", json.loads(buf.getvalue())["refused"])
        self.assertIsNone(plan3.version(Path(tmp)))


if __name__ == "__main__":
    unittest.main()
