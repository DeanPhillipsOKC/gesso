"""Tests for element techniques (spike/elements.py, the elements tool), issue #12: the library, how a part's steps
fit its element, the value check, a drafted element, and what the page and draft-text take from them.
No renders, no network, no model files."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

import elements as el  # noqa: E402
import tools  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "plans"
NAMES = ("chickadee", "red-sailboat", "lavender-balloon")


def plan(name: str) -> dict:
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def step(sid: str, show: str, stroke: str, paints=("p",)) -> dict:
    return {"id": sid, "show": show, "stroke": stroke, "paints": list(paints)}


def run_tool(*argv) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tools.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


ROWS = [step("rows", "flat", "horizontal-strokes", ["dark"]), step("paths", "pass", "toward-vanishing-point", ["soil"]),
        step("deep", "pass", "stamp", ["deep"]), step("mid", "pass", "stamp", ["mid"]),
        step("tips", "full", "stamp", ["light"])]
LIGHT = {"dark": 20.0, "soil": 50.0, "deep": 25.0, "mid": 45.0, "light": 75.0}


class LibraryTests(unittest.TestCase):
    def test_the_library_has_no_problems_and_names_only_real_cards(self):
        lib = el.library()
        self.assertGreaterEqual(len(lib), 10)
        self.assertEqual(el.problems(lib), [])
        cards = {p.stem for p in el.STROKES.glob("*.yaml")}
        for e_ in lib.values():
            for s in e_["steps"]:
                self.assertTrue(set(s["strokes"]) <= cards, (e_["id"], s["strokes"]))
            # every line cites the research or the technique file, or says plainly that it goes past them
            self.assertTrue(all("docs/research" in x or "techniques/" in x or x.startswith("general practice")
                                for x in e_["sources"]), e_["id"])
            self.assertTrue(any("docs/research" in x for x in e_["sources"]), e_["id"])  # never practice alone
            self.assertIs(e_["checked"], False)  # the owner checks them

    def test_a_broken_element_is_reported(self):
        bad = {"x": {"id": "x", "_file": "techniques/elements/y.yaml", "name": "X", "for": "x", "kinds": ["blob"],
                     "medium": "acrylic", "levels": ["beginner"], "sources": ["s"],
                     "steps": [{"name": "a", "show": ["smear"], "strokes": ["nope"], "value": "bright", "optional": True,
                                "mistake": {"mistake": "m"}}]}}
        out = " | ".join(el.problems(bad, {"dabbing"}))
        for want in ("no checked", "file name and the id", "kind 'blob'", "show must", "'nope' has no card",
                     "value must", "'mistake' and 'fix'", "every step is optional"):
            self.assertIn(want, out)

    def test_a_drafted_element_must_say_so_and_stay_unchecked(self):
        d = copy.deepcopy(el.library()["foliage"])
        d.update(id="fur", checked=True)
        d.pop("_file")
        out = el.problems({"fur": d}, draft=True)
        self.assertTrue(any("drafted: true" in x for x in out))
        self.assertTrue(any("stays checked: false" in x for x in out))

    def test_the_page_lists_every_element(self):
        page = el.page()
        for k in el.library():
            self.assertIn(f"id='element-{k}'", page)
        self.assertIn("Not checked yet", page)


class MatchTests(unittest.TestCase):
    rows = el.library()["flower-rows"]

    def test_lavender_rows_fit_with_and_without_the_optional_paths(self):
        self.assertEqual(el.match(ROWS, self.rows, LIGHT), ([0, 1, 3, 4, 5], []))
        where, wrong = el.match([ROWS[0]] + ROWS[2:], self.rows, LIGHT)
        self.assertEqual((where, wrong), ([0, 3, 4, 5], []))

    def test_a_missing_pass_or_another_stroke_is_refused_with_the_recipe(self):
        _, wrong = el.match(ROWS[:3] + ROWS[4:], self.rows)  # no mid pass
        self.assertEqual(len(wrong), 1)
        self.assertIn("don't follow the flower-rows technique", wrong[0])
        self.assertIn("Stamp the middle value", wrong[0])
        dabbed = copy.deepcopy(ROWS)
        dabbed[3]["stroke"] = "dabbing"
        _, wrong = el.match(dabbed, self.rows)
        self.assertIn("mid (pass, dabbing) doesn't fit", wrong[0])

    def test_values_out_of_order_are_reported(self):
        _, wrong = el.match(ROWS, self.rows, {**LIGHT, "mid": 10.0})
        self.assertTrue(wrong)
        self.assertIn("mid is where", wrong[0])
        _, close = el.match(ROWS, self.rows, {**LIGHT, "mid": LIGHT["deep"] - el.VALUE_SLACK + 0.5})
        self.assertEqual(close, [])  # within the slack

    def test_repeat_takes_one_step_per_stripe_and_the_paints_pick_the_slot(self):
        ball = el.library()["round-object"]
        steps = [step("base", "flat", "build-from-pieces", ["gold"])] + \
                [step(f"s{i}", "pass", "curved-strokes", [c]) for i, c in enumerate(["red", "blue"])] + \
                [step("shade", "pass", "curved-strokes", ["dark"]), step("light", "pass", "curved-strokes", ["pale"])]
        L = {"gold": 60.0, "red": 45.0, "blue": 35.0, "dark": 20.0, "pale": 85.0}
        where, wrong = el.match(steps, ball, L)
        self.assertEqual(wrong, [])
        # the stripes repeat the sections step; the shade goes on the shade step (the fit using the most of the
        # element's steps), so its value is checked too; the pale paint is the light step
        self.assertEqual(where, [0, 1, 1, 2, 3])
        # stripes and no lit side (the gate run's balloon): a stripe has to be the light step, it's darker than the
        # base, and the message says the part is missing a step
        _, wrong = el.match(steps[:3], ball, L)
        self.assertEqual(len(wrong), 1)
        self.assertIn("missing that one", wrong[0])

    def test_a_pass_lands_on_the_step_whose_value_it_has_not_on_a_detail_step(self):
        ball = el.library()["round-object"]
        steps = [step("base", "flat", "curved-strokes", ["b"]), step("s0", "pass", "curved-strokes", ["s"]),
                 step("light", "pass", "curved-strokes", ["l"])]
        self.assertEqual(el.match(steps, ball, {"b": 60.0, "s": 70.0, "l": 85.0}), ([0, 1, 3], []))
        shaped = el.library()["shaped-object"]
        one = [step("base", "flat", "build-from-pieces", ["b"]), step("shade", "pass", "press-and-lift", ["d"])]
        self.assertEqual(el.match(one, shaped, {"b": 60.0, "d": 30.0})[0], [0, 1])
        two = one + [step("shade2", "pass", "press-and-lift", ["e"])]
        self.assertEqual(el.match(two, shaped, {"b": 60.0, "d": 30.0, "e": 20.0})[0], [0, 1, 1])

    def test_a_light_grass_pass_is_texture_and_a_dark_one_darkens_the_front(self):
        grass = el.library()["field-grass"]
        coat = step("coat", "flat", "horizontal-strokes", ["c"])
        self.assertEqual(el.match([coat, step("t", "pass", "dry-brush", ["l"])], grass, {"c": 60.0, "l": 80.0})[0], [0, 2])
        self.assertEqual(el.match([coat, step("d", "pass", "dry-brush", ["d"])], grass, {"c": 60.0, "d": 40.0})[0], [0, 1])

    def test_a_darken_step_shown_full_is_told_to_change_its_show_not_its_paint(self):
        # the hands-off lavender run of 2026-11-14 (#140): a "Darken" step with show full can only land on the
        # light texture step (the dark step is pass only), so its darker paint clashed. The fix is the show.
        L = {"c": 60.0, "d": 40.0}
        for eid, coat, darken in (("field-grass", step("coat", "flat", "horizontal-strokes", ["c"]),
                                   step("darken", "full", "dry-brush", ["d"])),
                                  ("soil-rows", step("coat", "flat", "toward-vanishing-point", ["c"]),
                                   step("darken", "full", "dry-brush", ["d"]))):
            e_ = el.library()[eid]
            where, wrong = el.match([coat, darken], e_, L)
            self.assertEqual(where, [0, 2], eid)
            self.assertEqual(len(wrong), 1, eid)
            self.assertIn("Change darken's show from full to pass, and keep its paints", wrong[0])
            self.assertIn(f"\"{e_['steps'][1]['name']}\" (dark)", wrong[0])
            self.assertNotIn("swap the two steps' paints", wrong[0])
            # and the named show does fit, with nothing left to say
            self.assertEqual(el.match([coat, dict(darken, show="pass")], e_, L), ([0, 1], []))

    def test_the_shows_offered_are_the_ones_plan2_allows(self):
        # a middle step may be flat or a pass; only the last may be full or blend, and never flat (PR #142 review)
        self.assertEqual(el._shows_allowed(0, 1), ("full", "blend"))  # a part's only step is its last
        self.assertEqual(el._shows_allowed(0, 3), ("flat",))
        self.assertEqual(el._shows_allowed(1, 3), ("pass", "flat"))
        self.assertEqual(el._shows_allowed(2, 3), ("pass", "full", "blend"))

    def test_a_clash_no_show_can_fix_still_points_at_the_paints(self):
        _, wrong = el.match(ROWS, self.rows, {**LIGHT, "mid": 10.0})
        self.assertIn("swap the two steps' paints", wrong[0])
        self.assertNotIn("show", wrong[0])
        ball = el.library()["round-object"]
        steps = [step("base", "flat", "build-from-pieces", ["gold"]), step("s0", "pass", "curved-strokes", ["red"])]
        _, wrong = el.match(steps, ball, {"gold": 60.0, "red": 45.0})
        self.assertIn("missing that one", wrong[0])

    def test_elements_lesson_says_to_change_the_show_on_the_lavender_plan(self):
        # the lavender fixture with its fields' darken pass set to show full, as the hands-off run had it
        p = plan("lavender-balloon")
        shade = next(s for st in p["stages"] for s in st["steps"] if s["id"] == "fields-shade")
        with tempfile.TemporaryDirectory() as d:
            # the tools want the name; the picture isn't read for this, and PIL reads a JPEG by its bytes
            (Path(d) / "99_finish.png").write_bytes((FIX.parent / "finishes" / "lavender-balloon.jpg").read_bytes())
            for show in ("pass", "full"):
                shade["show"] = show
                (Path(d) / "plan.json").write_text(json.dumps(p), encoding="utf-8")
                code, out = run_tool("elements", "--lesson", d)
                self.assertEqual(code, 0, out)
                said = [x for x in out["problems"] if x.startswith("fields:")]
                if show == "pass":
                    self.assertEqual(said, [])
            self.assertEqual(len(said), 1, out["problems"])
            self.assertIn("Change fields-shade's show from full to pass, and keep its paints", said[0])

    def test_a_ripple_pass_is_the_ripple_step_and_shows_its_mistake(self):
        water = el.library()["water"]
        steps = [step("base", "flat", "horizontal-strokes", ["d"]), step("light", "pass", "horizontal-strokes", ["l"]),
                 step("rip", "pass", "horizontal-dashes", ["l"])]
        self.assertEqual(el.match(steps, water, {"d": 30.0, "l": 70.0})[0], [0, 1, 2])
        p = {"parts": [{"id": "water", "kind": "area", "element": "water"}],
             "paints": [{"id": "d", "hex": "#123456"}, {"id": "l", "hex": "#a0c0e0"}],
             "stages": [{"id": "w", "steps": [{**s, "part": "water"} for s in steps]}]}
        marked = el.step_elements(p, el.library())
        self.assertEqual(marked["rip"]["mistake"]["mistake"], "Ripple lines the same length everywhere.")

    def test_check_and_the_page_use_the_same_fit(self):
        for name in NAMES:
            p = plan(name)
            light = el.plan_lightness(p)
            marked = el.step_elements(p, el.library())
            for part in p["parts"]:
                steps = [s for st in p["stages"] for s in st["steps"] if s["part"] == part["id"]]
                where, _ = el.match(steps, el.library()[part["element"]], light)
                self.assertEqual([marked[s["id"]]["slot"] for s in steps], where, (name, part["id"]))

    def test_the_same_plan_gives_the_same_fit(self):
        a = el.match(ROWS, self.rows, LIGHT)
        self.assertEqual(a, el.match(copy.deepcopy(ROWS), self.rows, LIGHT))


class PlanTests(unittest.TestCase):
    def test_every_fixture_part_names_an_element_with_a_reason(self):
        lib = el.library()
        for name in NAMES:
            p = plan(name)
            self.assertTrue(p["technique_why"])
            for part in p["parts"]:
                self.assertIn(part["element"], lib, (name, part["id"]))
                self.assertTrue(part["element_why"])

    def test_the_fixture_findings(self):
        """The chickadee and sailboat follow their elements. The lavender fixture doesn't, as the owner found
        (#12): its rows are dabbed, not stamped, with no separate dark bloom pass; its balloon goes straight to the
        stripes and basket. Its fields, a coat then a darker front, follow field-grass."""
        self.assertEqual(el.plan_problems(plan("chickadee"), el.library()), [])
        self.assertEqual(el.plan_problems(plan("red-sailboat"), el.library()), [])
        out = el.plan_problems(plan("lavender-balloon"), el.library())
        self.assertEqual([x.split(":")[0] for x in out], ["lavender", "balloon"])

    def test_no_element_no_reason_wrong_kind_and_unknown(self):
        p = plan("red-sailboat")
        p.pop("technique_why")
        parts = {x["id"]: x for x in p["parts"]}
        parts["sky"].pop("element")
        parts["sun"].pop("element_why")
        parts["hill"]["element"] = "reflection"  # a marks element on an area
        parts["mast"]["element"] = "rigging"
        out = " | ".join(el.plan_problems(p, el.library()))
        for want in ("no technique_why", "sky: no element", "sun: no element_why", "hill: element reflection is for marks",
                     "mast: element 'rigging' isn't in"):
            self.assertIn(want, out)

    def test_a_drafted_element_counts_once_filed(self):
        p = plan("chickadee")
        p["parts"][6]["element"] = "scaled-body"  # the bird
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp)
            (lesson / "elements").mkdir()
            draft = {k: v for k, v in el.library()["shaped-object"].items() if not k.startswith("_")}
            draft.update(id="scaled-body", name="A scaled body", drafted=True, checked=False,
                         sources=["general painting practice; the research has no section on scales"])
            path = lesson / "elements" / "scaled-body.yaml"
            path.write_text(yaml.safe_dump(draft), encoding="utf-8")
            out = el.plan_problems(p, lesson=lesson)
            self.assertEqual(len(out), 1)
            self.assertIn("isn't filed for the owner yet", out[0])
            draft["filed"] = "https://github.com/DeanPhillipsOKC/gesso/issues/999"
            path.write_text(yaml.safe_dump(draft), encoding="utf-8")
            self.assertEqual(el.plan_problems(p, lesson=lesson), [])
            marked = el.step_elements(p, el.known(lesson))
            self.assertTrue(marked["bird-body"]["drafted"])
            self.assertFalse(marked["sky-blend"]["drafted"])
            # a draft no part uses is reported
            (lesson / "elements" / "spare.yaml").write_text(yaml.safe_dump({**draft, "id": "spare"}), encoding="utf-8")
            self.assertTrue(any("spare.yaml was drafted but no part uses it" in x for x in el.plan_problems(p, lesson=lesson)))
            (lesson / "elements" / "spare.yaml").unlink()
            # a new id missing drafted: true is told so, not blamed on an id clash
            nodraft = {**draft, "id": "scales"}
            nodraft.pop("drafted")
            (lesson / "elements" / "scales.yaml").write_text(yaml.safe_dump(nodraft), encoding="utf-8")
            p["parts"][5]["element"] = "scales"  # the leaves
            out = el.plan_problems(p, lesson=lesson)
            self.assertTrue(any("needs drafted: true" in x for x in out))
            self.assertFalse(any("library element's id" in x for x in out))
            (lesson / "elements" / "scales.yaml").unlink()
            p["parts"][5]["element"] = "shaped-object"
            # a draft can't take a library id
            clash = lesson / "elements" / "foliage.yaml"
            clash.write_text(yaml.safe_dump({**draft, "id": "foliage"}), encoding="utf-8")
            p["parts"][3]["element"] = "foliage"
            self.assertTrue(any("library element's id" in x for x in el.plan_problems(p, lesson=lesson)))

    def test_a_draft_later_added_to_the_library_as_it_was_is_no_clash(self):
        p = plan("chickadee")
        with tempfile.TemporaryDirectory() as tmp:
            lesson = Path(tmp)
            (lesson / "elements").mkdir()
            same = {k: v for k, v in el.library()["foliage"].items() if not k.startswith("_")}
            same.update(drafted=True, filed="https://github.com/DeanPhillipsOKC/gesso/issues/999")
            (lesson / "elements" / "foliage.yaml").write_text(yaml.safe_dump(same), encoding="utf-8")
            self.assertEqual(el.plan_problems(p, lesson=lesson), [])
            same["rules"] = ["changed since"]
            (lesson / "elements" / "foliage.yaml").write_text(yaml.safe_dump(same), encoding="utf-8")
            out = el.plan_problems(p, lesson=lesson)
            self.assertEqual(len(out), 1)
            self.assertIn("library element's id", out[0])

    def test_an_elements_mistake_is_the_watch_line_and_picks_are_listed(self):
        marked = el.step_elements(plan("lavender-balloon"), el.library())
        self.assertEqual(marked["sky-blend"]["mistake"]["mistake"], "Blending after the paint has started to drag.")
        picks = el.picks(plan("chickadee"))
        self.assertEqual([x["part"] for x in picks], [x["id"] for x in plan("chickadee")["parts"]])
        self.assertTrue(all(x["element"] and x["why"] for x in picks))

    def test_the_tool_lists_the_library_and_writes_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, r = run_tool("elements", "--out", str(Path(tmp) / "elements.html"))
            self.assertEqual(code, 0)
            self.assertEqual(r["problems"], [])
            self.assertEqual({x["id"] for x in r["elements"]}, set(el.library()))
            self.assertTrue((Path(tmp) / "elements.html").exists())


if __name__ == "__main__":
    unittest.main()
