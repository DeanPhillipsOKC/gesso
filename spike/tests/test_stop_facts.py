"""Pipeline v4's second build step (#296; docs/design/pipeline-v4.md, sections 6 and 13): the fact sheet says where a
stopped layer's lower edge is (`stop`) and what each step's paint goes onto (`onto`), and check-text holds a length
from the top or bottom edge said of a stopped step's own paint to its line.

On a made-up scene: a sky that stops at a wavy line about 1 in past the top of the hills that cover it. Then (slow)
the cow's and the birch grove's bench chains: the design's section 6 table, the issue's sentences, and planted
faults in a stop distance caught at #173's rate; and the fixture lessons, whose sheets without --stops are what they
were before, with `onto` added."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "experiments"))
sys.path.insert(0, str(HERE))

import facts  # noqa: E402
import lesson3  # noqa: E402
import lessons  # noqa: E402
import steps3  # noqa: E402
import stops  # noqa: E402

PX = 20  # pixels an inch
CANVAS = {"w_in": 16, "h_in": 12}
WHITE, BLUE, GREEN = (250, 249, 245), (120, 160, 220), (60, 120, 50)
HILLS_TOP = 7.0
ROW = {"unit": 0, "id": "sky", "steps": [1], "covered_by": {"unit": 1, "id": "hills", "step": 2},
       "line": {"highest": 7.5, "most": 8.0, "lowest": 8.5, "left": 8.0, "right": 8.0,
                "past_cover": {"most": 1.0, "least": 0.5, "greatest": 1.5}}}


def scene(stopped: bool = True) -> dict:
    """A sky, then hills from 7 in down to the bottom edge. Stopped, the sky's picture ends at a line 8 in down that
    wobbles half an inch either way, and the canvas below it stays bare until the hills; unstopped, the sky is the
    whole canvas."""
    h, w = 12 * PX, 16 * PX
    ys, xs = np.indices((h, w))
    line = (8 + 0.5 * np.sin(2 * np.pi * xs / w)) * PX
    whole = np.ones((h, w), bool)
    sky = ys < line if stopped else whole
    hills = ys >= HILLS_TOP * PX
    plan = {"parts": [{"id": "sky", "name": "The sky", "kind": "area", "unit": 0},
                      {"id": "hills", "name": "The far hills", "kind": "area", "unit": 1}],
            "paints": [{"id": "blue", "name": "Sky blue", "hex": "#78a0dc"},
                       {"id": "green", "name": "Hill green", "hex": "#3c7832"}],
            "stages": [{"id": "sky", "name": "Sky", "steps": [{"id": "lay-sky", "name": "Lay the sky", "part": "sky",
                                                                "show": "full", "paints": ["blue"]}]},
                       {"id": "land", "name": "Land", "steps": [{"id": "lay-hills", "name": "Lay the far hills",
                                                                  "part": "hills", "show": "full",
                                                                  "paints": ["green"]}]}]}
    one = np.empty((h, w, 3), np.uint8)
    one[:] = WHITE
    one[sky] = BLUE
    two = one.copy()
    two[hills] = GREEN
    owner = np.where(hills, 1, 0).astype(np.int32)
    return facts.make_sheet(plan, [one, two], [sky, hills], owner, None, CANVAS, shapes=[whole, hills],
                            stops={"stopped": [ROW]} if stopped else None, full=[whole, hills] if stopped else None)


def check(sheet: dict, step_id: str, words: str) -> list[dict]:
    return facts.check_text(sheet, {"steps": [{"stage_id": step_id, "tip": words}]}, strict=True)["failures"]


class SheetTests(unittest.TestCase):
    def setUp(self):
        self.sheet = scene()

    def test_stop_is_copied_from_build_json(self):
        sky, hills = self.sheet["steps"]
        self.assertEqual(sky["stop"], {"highest": 7.5, "most": 8.0, "lowest": 8.5, "left": 8.0, "right": 8.0,
                                       "next": {"step": 2, "name": "Lay the far hills",
                                                "covers": ROW["line"]["past_cover"]}})
        self.assertNotIn("stop", hills)
        # its part is what its picture shows: it no longer reaches the bottom edge
        self.assertEqual(self.sheet["parts"]["sky"]["edges"], ["left", "right", "top"])
        self.assertEqual(scene(stopped=False)["parts"]["sky"]["edges"], ["left", "right", "top", "bottom"])

    def test_onto(self):
        sky, hills = self.sheet["steps"]
        self.assertEqual((sky["onto"]["bare"], sky["onto"]["over"]), (1.0, []))
        self.assertAlmostEqual(hills["onto"]["bare"], 0.8, delta=0.02)
        self.assertEqual([o["part"] for o in hills["onto"]["over"]], ["sky"])
        self.assertAlmostEqual(hills["onto"]["over"][0]["share"], 0.2, delta=0.02)
        # without the rule the hills go on the sky, all of them
        self.assertEqual(scene(stopped=False)["steps"][1]["onto"]["bare"], 0.0)

    def test_the_sentences(self):
        sky, hills = self.sheet["steps"]
        text = facts.facts_text(self.sheet, {}, sky)
        self.assertIn("It stops short. Its lower edge is a loose, uneven line: about 8 in (8) from the top edge for "
                      "most of its width, 7 1/2 in (7 1/2) at its highest and 8 1/2 in (8 1/2) at its lowest (8 in (8) "
                      "at the left edge, 8 in (8) at the right edge). The rest of the canvas stays bare. Step 2 (Lay the "
                      "far hills) paints there next, and its top covers this edge by about 1 in (1).", text)
        self.assertIn("All of what it paints goes on bare canvas.", text)
        lean = facts.lean(facts.facts_text(self.sheet, {}, hills))
        self.assertIn("Of what it paints, about a fifth goes over The sky and the rest on bare canvas.", lean)
        self.assertIn("about 8 in from the top edge for most of its width, 7 1/2 in at its highest",
                      facts.lean(text))

    def test_onto_words(self):
        self.assertEqual(facts.onto_words({"bare": 0.0, "over": [{"name": "The sky", "share": 0.97}]}),
                         "Nearly all of what it paints goes over The sky.")
        self.assertEqual(facts.onto_words({"bare": 0.6, "over": [{"name": "The sky", "share": 0.3},
                                                                 {"name": "The clouds", "share": 0.1}]}),
                         "Of what it paints, about a third goes over The sky, about a tenth over The clouds, and "
                         "the rest on bare canvas.")
        self.assertEqual(facts.onto_words({"bare": 0.01, "over": []}), "")


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.sheet = scene()

    def test_a_length_from_an_edge_is_held_to_the_line(self):
        for words in ("Stop the sky about 8 in from the top edge, with a soft, wavy lower edge.",
                      "Stop the sky about 7 1/2 in from the top edge.", "Its lower edge is 8 1/2 in from the top edge.",
                      "Take it down to about 4 in from the bottom edge.", "Its bottom is about 8 in from the top edge."):
            self.assertEqual(check(self.sheet, "lay-sky", words), [], words)
        for words in ("Stop the sky about 9 1/2 in from the top edge.",  # 1 in below its lowest point
                      "Stop the sky about 6 1/2 in from the top edge.",  # 1 in above its highest
                      "Take it down to about 2 1/2 in from the bottom edge."):
            self.assertEqual(len(check(self.sheet, "lay-sky", words)), 1, words)

    def test_reaching_the_bottom_edge_fails_on_a_stopped_step(self):
        for words in ("Pull the sky down until it reaches the bottom edge.", "Cover all four edges."):
            self.assertEqual(len(check(self.sheet, "lay-sky", words)), 1, words)
            self.assertEqual(check(scene(stopped=False), "lay-sky", words), [], words)

    def test_a_step_that_doesnt_stop_is_checked_as_before(self):
        self.assertEqual(check(self.sheet, "lay-hills", "Its top is about 7 in from the top edge."), [])
        self.assertEqual(len(check(self.sheet, "lay-hills", "Its top is about 8 in from the top edge.")), 1)


def bench_sheet(pic: str) -> dict:
    """The fact sheet of a bench chain (spike/experiments/bench/v31-gate/) built with the rule, as build-steps
    --stops and make_sheet would make it: the chain keeps only each unit's picture and shape, so the plan's v2 shape
    is made from the shapes."""
    import cover_margin as cm
    from test_stops import BENCH

    L = cm.load(pic)
    base = cm.baseline(L)
    c = json.loads((BENCH / pic / "data" / "canvas.json").read_text())
    z = np.load(BENCH / pic / "chain" / "masks.npz")
    shapes = [z[f"s{n:02d}"] for n in range(len(L["units"]))]
    view = steps3.as_v2(L["plan"], L["units"], [{"core": s, "D": s} for s in shapes], L["hexes"], L["owner_png"],
                        L["P"][-1])
    fr = stops.frame(L["P"][0].shape, c["canvas_box"], c["canvas"])
    worked = stops.work_out(L["plan"], L["units"], L["m"], L["owner_png"], fr)
    laid = stops.lay(base, L["m"], L["units"], worked["want"])
    said = stops.report(L["plan"], L["units"], L["m"], worked, laid, fr)
    shown = [f & ~(h > stops.HIDDEN) for f, h in zip(L["m"], laid["hidden"])]
    shown = [s if s.any() else f for s, f in zip(shown, L["m"])]
    return facts.make_sheet(view, laid["pictures"], shown, L["owner_png"], c["canvas_box"], c["canvas"], shapes,
                            said["stops"], L["m"])


FORMS = ["Stop it about {} in from the {} edge.", "Its lower edge sits about {} in from the {} edge.",
         "Take it down to about {} in from the {} edge."]


@lessons.slow
class BenchTests(unittest.TestCase):
    def test_the_bench_chains(self):
        """One test, so the runner builds the two sheets once (about a minute)."""
        self.sheets = {pic: bench_sheet(pic) for pic in ("highland-cow", "birch-grove")}
        for part in (self.the_cow_gives_the_design_s_table, self.the_issue_s_sentences,
                     self.a_fault_planted_in_a_stop_distance_is_caught):
            with self.subTest(part.__name__):
                part()

    def the_cow_gives_the_design_s_table(self):
        """Section 6: the sky's area and paint end at its line; the far hills' paint is about 4 in down and reaches
        only the left and right edges; both say where they stop and for what."""
        sky, hills = self.sheets["highland-cow"]["steps"][0], self.sheets["highland-cow"]["steps"][3]
        self.assertEqual(facts.ruler(sky["area"]["tall"]), "4 1/4")
        self.assertEqual(sky["area"]["edges"], ["left", "right", "top"])
        self.assertEqual(sky["adds"]["edges"], ["left", "right", "top"])
        self.assertEqual(facts.ruler(sky["adds"]["cy"], 2), "1 1/2")
        self.assertEqual(hills["adds"]["edges"], ["left", "right"])
        self.assertEqual(facts.ruler(hills["adds"]["cy"], 2), "4")
        for st, (hi, most, lo, nxt) in ((sky, (3 + 5 / 16, 3.5, 4 + 1 / 8, 4)), (hills, (4 + 5 / 8, 5.25, 6 + 1 / 16, 7))):
            for k, v in zip(("highest", "most", "lowest"), (hi, most, lo)):
                self.assertAlmostEqual(st["stop"][k], v, delta=1 / 16, msg=(st["id"], k))
            self.assertEqual(st["stop"]["next"]["step"], nxt)
        self.assertEqual([s["n"] for s in self.sheets["highland-cow"]["steps"] if s.get("stop")], [1, 2, 3, 4])
        self.assertEqual(sky["onto"]["bare"], 1.0)
        self.assertGreater(hills["onto"]["bare"], 0.5)  # the far hills go mostly onto bare canvas now

    def the_issue_s_sentences(self):
        sheet = self.sheets["highland-cow"]
        lowest = sheet["steps"][0]["stop"]["lowest"]
        self.assertEqual(check(sheet, "blend-sky", "Stop the sky about 3 1/2 in from the top edge, with a soft, wavy "
                                                   "lower edge."), [])
        self.assertEqual(len(check(sheet, "blend-sky", f"Stop the sky about {facts.ruler(lowest + 1)} in from the top "
                                                       "edge.")), 1)
        self.assertEqual(len(check(sheet, "blend-sky", "The sky reaches the bottom edge.")), 1)
        self.assertEqual(len(check(sheet, "lay-hills", "Bring the hills down to the bottom edge.")), 1)

    def a_fault_planted_in_a_stop_distance_is_caught(self):
        """Each of a stopped step's five distances, said from the top and from the bottom edge in three ways, moved
        by +-1 in and +-1/2 in as #173's `mutate` moved a length. A move that leaves it on the line isn't a fault and
        isn't counted, as #173 counted only mutants wrong by construction. #173 caught 93 to 100% of each kind."""
        caught, alarms = {}, []
        for pic, sheet in self.sheets.items():
            ch = sheet["canvas"]["h_in"]
            for st in [s for s in sheet["steps"] if s.get("stop")]:
                lo, hi = st["stop"]["highest"], st["stop"]["lowest"]
                for v in [st["stop"][k] for k in ("highest", "most", "lowest", "left", "right")
                          if st["stop"][k] is not None]:
                    for edge in ("top", "bottom"):
                        for form in FORMS:
                            def words(x):
                                return form.format(facts.ruler(x if edge == "top" else ch - x), edge)
                            if check(sheet, st["id"], words(v)):
                                alarms.append((pic, st["n"], words(v)))
                            for kind, d in facts.SHIFTS.items():
                                said = round((v + d) * 4) / 4
                                if lo - facts.tol(said) <= said <= hi + facts.tol(said):
                                    continue
                                n = caught.setdefault(kind, [0, 0])
                                n[0] += bool(check(sheet, st["id"], words(v + d)))
                                n[1] += 1
        self.assertEqual(alarms, [])
        self.assertEqual(set(caught), set(facts.SHIFTS))
        for kind, (got, of) in caught.items():
            self.assertGreaterEqual(got / of, 0.97, (kind, got, of))


SHEETS = {  # each fixture's sheet before #296 (sha256 of its JSON, keys sorted, 16 digits): built without --stops
    "chickadee": "f6afbcf773398d55", "lavender-balloon": "f95006988c2a6d51", "red-sailboat": "ad76ccbff09676c0"}


@lessons.slow
class FixtureTests(unittest.TestCase):
    def test_without_the_rule_the_sheet_is_today_s_with_onto_added(self):
        for name in lessons.NAMES:
            with self.subTest(name):
                sheet, _ = facts.lesson_sheet(lessons.lesson(name, "built"))
                self.assertTrue(all("onto" in s and "stop" not in s for s in sheet["steps"]))
                for s in sheet["steps"]:
                    s.pop("onto")
                self.assertEqual(hashlib.sha256(json.dumps(sheet, sort_keys=True).encode()).hexdigest()[:16],
                                 SHEETS[name])

    def test_with_the_rule_the_stopped_steps_say_so(self):
        """The lavender balloon's layers stop (its sky and clouds, darker ridges, hills and tree's canopy): build-steps --stops, then the sheet
        as check-text reads it has `stop` on exactly their steps."""
        lesson = lessons.lesson("lavender-balloon", "chained")
        code, out = lessons.run_tool("build-steps", "--lesson", str(lesson), "--stops")
        self.assertEqual(code, 0)
        sheet, _ = facts.lesson_sheet(lesson)
        want = sorted(n for r in out["stops"]["stopped"] for n in r["steps"])
        self.assertTrue(want)
        self.assertEqual([s["n"] for s in sheet["steps"] if s.get("stop")], want)
        build = lesson3.read(lesson, pictures=False)["build"]
        self.assertEqual(build["stops"], out["stops"])
        shutil.rmtree(lesson)


if __name__ == "__main__":
    unittest.main()
