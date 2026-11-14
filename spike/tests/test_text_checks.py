"""Tests for step text drafted from data (spike/draft_text.py, the draft-text tool) and the measured checks
(spike/checks.py, the check tool, and publish running it), issue #51, docs/design/pipeline-v2.md sections 10 and 12.
No renders, no network, no model files: the three fixtures' saved outlines are enough."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import yaml  # noqa: E402
from PIL import Image  # noqa: E402

import aids  # noqa: E402
import build_steps as bs  # noqa: E402
import cards  # noqa: E402
import checks  # noqa: E402
import draft_text as dt  # noqa: E402
import lessons  # noqa: E402
import loads  # noqa: E402
import publish2  # noqa: E402
import tools  # noqa: E402
from test_pipeline_v2 import CANVAS, NAMES, fixture  # noqa: E402

TECHNIQUE = yaml.safe_load((tools.ROOT / "techniques" / "acrylic-paint-along-beginner.yaml").read_text(encoding="utf-8"))
PERCENT = re.compile(r"%|percent", re.I)


def run_tool(*argv) -> tuple[int, dict]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = tools.main(list(argv))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


def by_id(entries: list[dict]) -> dict[str, dict]:
    return {e["stage_id"]: e for e in entries}


def kinds(entry: dict) -> list[str]:
    return [x["kind"] for x in entry["lines"]]


@lessons.slow
class DraftTests(unittest.TestCase):
    """draft_text.draft on the three fixtures, built once."""
    whole = True  # tests/suite.py runs it as one job: its setUpClass drafts every fixture's text

    @classmethod
    def setUpClass(cls):
        cls.built, cls.owners = {}, {}
        for name in NAMES:
            plan, pictures, _, masks = lessons.built(name)
            cls.owners[name] = lessons.fixture(name)[2]
            cls.built[name] = (plan, pictures, masks, dt.draft(plan, pictures, masks, None, CANVAS, owner=cls.owners[name]))

    def test_every_step_has_lines_in_the_tables_order_none_long_none_with_percentages(self):
        rank = {k: n for n, k in enumerate(dt.KINDS)}
        for name, (plan, _, _, drafted) in self.built.items():
            self.assertEqual([d["stage_id"] for d in drafted], [s["id"] for s in bs.flat_steps(plan)])
            for d in drafted:
                ks = kinds(d)
                self.assertEqual(ks, sorted(ks, key=rank.get), f"{name} {d['stage_id']}")
                self.assertIn("where", ks)
                self.assertIn("paints", ks)
                self.assertIn("how", ks)
                for x in d["lines"]:
                    self.assertLessEqual(len(x["text"].split()), dt.MAX_WORDS, x)
                    self.assertNotRegex(x["text"], PERCENT)
                    self.assertIs(x["edited"], False)
                self.assertEqual(d["made_with"], "composite:from-finish")

    def test_the_same_input_gives_the_same_lines(self):
        plan, pictures, masks, drafted = self.built["chickadee"]
        self.assertEqual(json.dumps(dt.draft(plan, pictures, masks, None, CANVAS,
                                                  owner=self.owners["chickadee"])), json.dumps(drafted))

    def test_let_it_dry_follows_the_paint_underneath(self):
        d = by_id(self.built["chickadee"][3])
        self.assertNotIn("dry", kinds(d["sky-blend"]))  # nothing under the first step
        self.assertEqual(d["sun"]["lines"][0]["text"], dt.DRY.format(what="the misty sunset sky"))  # this stage: the part
        self.assertEqual(d["trunks"]["lines"][0]["text"], dt.DRY.format(what="the misty sky"))  # another stage: its name
        self.assertIn("the black cap and bib", d["bird-cheek"]["lines"][0]["text"])  # inside a stage: the part's name
        self.assertIn("the branch", d["bird-feet"]["lines"][0]["text"])  # the feet cross the branch and the bird
        self.assertIn("the chickadee", d["bird-feet"]["lines"][0]["text"])

    def test_rinse_before_a_far_color_or_the_lightest_yet(self):
        d = by_id(self.built["chickadee"][3])
        self.assertEqual([x["text"] for x in d["sun"]["lines"] if x["kind"] == "rinse"], [dt.RINSE_LIGHT])
        self.assertEqual([x["text"] for x in d["bird-cheek"]["lines"] if x["kind"] == "rinse"], [dt.RINSE])  # black, then white
        self.assertNotIn("rinse", kinds(d["branch-mid"]))  # bark brown to bark tan

    def test_chalk_only_where_an_object_with_no_parent_starts(self):
        for name, (plan, _, _, drafted) in self.built.items():
            parts = {p["id"]: p for p in plan["parts"]}
            seen = set()
            for s, d in zip(bs.flat_steps(plan), drafted):
                p = parts[s["part"]]
                want = p["kind"] == "object" and not p.get("parent") and s["part"] not in seen
                self.assertEqual("chalk" in kinds(d), want, f"{name} {s['id']}")
                seen.add(s["part"])

    def test_where_is_the_outline_in_words_inches_with_a_canvas(self):
        plan, pictures, masks, drafted = self.built["chickadee"]
        for d, m in zip(drafted, bs.visible(plan, self.owners["chickadee"], masks)):
            self.assertTrue(" ".join(x["text"] for x in d["lines"] if x["kind"] == "where").startswith(
                aids.where_words(m, CANVAS)))  # what the finish shows of it, then why the outline is bigger if it is
        sized = by_id(drafted)
        where = next(x["text"] for x in sized["bird-body"]["lines"] if x["kind"] == "where")
        self.assertRegex(where, r"\d in from the (top|left) edge")
        self.assertNotIn("the whole canvas", " ".join(x["text"] for x in sized["branch-dark"]["lines"]))  # thin, all 4 edges

    def test_paints_go_darkest_first_and_a_blend_top_to_bottom(self):
        plan = self.built["red-sailboat"][0]
        d = by_id(self.built["red-sailboat"][3])
        names = publish2.paint_names(plan)
        self.assertEqual(next(x["text"] for x in d["sky-blend"]["lines"] if x["kind"] == "paints"),
                         f"Paints, top to bottom: {names['sky-1']}, {names['sky-2']}, then {names['sky-3']}.")
        leaves = by_id(self.built["chickadee"][3])["leaves-shape"]
        names = publish2.paint_names(self.built["chickadee"][0])
        self.assertIn(f"darkest first: {names['leaves-1']}, then {names['foliage-1']}", leaves["lines"][3]["text"])

    def test_a_paint_used_again_is_mixed_once_for_all_its_steps(self):
        plan, _, _, drafted = self.built["chickadee"]
        names = publish2.paint_names(plan)
        mix = [x["text"] for x in by_id(drafted)["branch-dark"]["lines"] if x["kind"] == "mix"]
        self.assertEqual(mix, [f"Mix enough {names['branch-1']} for this step and step 18; cover it between them."])
        self.assertNotIn("mix", kinds(by_id(drafted)["bird-feet"]))  # its second use: the page says "from step 5"

    def test_how_result_and_watch_out_are_the_cards_own_words(self):
        import elements

        known = cards.strokes()
        for name, (plan, _, _, drafted) in self.built.items():
            picked = elements.step_elements(plan, elements.library())
            for s, d in zip(bs.flat_steps(plan), drafted):
                card = known[s["stroke"]]
                how = " ".join(x["text"] for x in d["lines"] if x["kind"] == "how")
                self.assertIn(f"Brush: {s['brush']}.", how)
                if card.get("load"):
                    self.assertIn(f"Load: {loads.text(card['load'])}", how)  # the fixed terms first (#99)
                if card.get("motion"):
                    self.assertIn(card["motion"].strip(), how)
                result = [x["text"] for x in d["lines"] if x["kind"] == "result"]
                self.assertEqual(result[0][len("It should leave "):].lower(), card["result"].lower())
                watch = " ".join(x["text"] for x in d["lines"] if x["kind"] == "watch")
                own = (picked.get(s["id"]) or {}).get("mistake")  # the element step's mistake comes first (#12)
                if own:
                    self.assertIn(own["mistake"], watch)
                elif card.get("mistakes"):
                    self.assertIn(card["mistakes"][0]["mistake"], watch)
                else:
                    self.assertEqual(watch, "")

    def test_a_layer_left_showing_and_light_over_dark_are_measured(self):
        d = by_id(self.built["chickadee"][3])
        self.assertIn(dt.LEAVE_SHOWING.format(steps="step 5"), [x["text"] for x in d["branch-mid"]["lines"]])
        self.assertIn("coats", kinds(d["bird-cheek"]))  # cheek white over the black cap
        self.assertNotIn("coats", kinds(d["bird-body"]))  # a mid value over the background
        self.assertNotIn("coats", kinds(d["sky-blend"]))  # over white canvas

    def test_step_back_at_the_end_of_every_stage(self):
        for name, (plan, _, _, drafted) in self.built.items():
            last = {st["steps"][-1]["id"] for st in plan["stages"]}
            self.assertEqual({d["stage_id"] for d in drafted if "step-back" in kinds(d)}, last)

    def test_left_out_names_each_card_field_the_research_lacks(self):
        gaps = dt.left_out(self.built["chickadee"][0])
        self.assertIn("card x-stroke has no mistakes, so no watch-out line", gaps["sky-blend"])
        plan = copy.deepcopy(self.built["chickadee"][0])
        plan["stages"][0]["steps"][0]["stroke"] = "no-such-card"
        self.assertIn("no stroke card", dt.left_out(plan)["sky-blend"][0])

    def test_a_long_card_text_is_split_between_sentences(self):
        text = " ".join(["One two three four five six seven eight nine ten."] * 5)
        lines = dt.split(text, "how")
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(x["text"].split()) <= dt.MAX_WORDS and x["text"].endswith(".") for x in lines))

    def where_line(self, name: str, step: str) -> str:
        d = by_id(self.built[name][3])[step]
        return " ".join(x["text"] for x in d["lines"] if x["kind"] == "where")

    def test_where_gives_the_visible_horizon_not_the_paint_under_later_parts(self):
        # #126: the sky is painted past the horizon on purpose (covers), the water's coat lays the hill's rim back,
        # and both used to be measured whole, so the inches were off. On a 14 x 11 canvas the lines must place the
        # horizon the finished painting shows, within 1/2 in.
        plan, _, _, _ = self.built["red-sailboat"]
        owner = self.owners["red-sailboat"]
        idx = {p["id"]: i for i, p in enumerate(plan["parts"])}
        h = owner.shape[0]
        sky_rows = np.flatnonzero(np.isin(owner, bs._family(plan["parts"], idx["sky"])).any(1))
        water_rows = np.flatnonzero(np.isin(owner, bs._family(plan["parts"], idx["water"])).any(1))
        sky_bottom, water_top = (sky_rows.max() + 1) / h * CANVAS["h_in"], water_rows.min() / h * CANVAS["h_in"]

        def inches_down(line: str, what: str) -> float:
            m = re.search(rf"Its {what} is about (\d+)(?: (\d)/(\d))? in from the (top|bottom) edge", line)
            self.assertIsNotNone(m, line)
            v = int(m[1]) + (int(m[2]) / int(m[3]) if m[2] else 0)
            return v if m[4] == "top" else CANVAS["h_in"] - v

        sky = self.where_line("red-sailboat", "sky-blend")
        self.assertLessEqual(abs(inches_down(sky, "bottom") - sky_bottom), 0.5, sky)
        self.assertIn("Paint a little past its bottom, under where the far hill and shore, and the water will go.", sky)
        for step in ("water-coat", "water-light"):
            water = self.where_line("red-sailboat", step)
            self.assertLessEqual(abs(inches_down(water, "top") - water_top), 0.5, water)
        # an object is placed by its own outline, not its soft rim or the paint run under the hill
        self.assertIn("about 3/4 in wide and 3/4 in tall", self.where_line("red-sailboat", "sun"))


class VisibleTests(unittest.TestCase):
    """build_steps.visible and draft_text.past_words on a made-up scene (#126)."""

    def scene(self):
        parts = [{"id": "sky", "name": "The sky", "kind": "area", "box": [0, 0, 1, 0.6], "covers": [[0, 0, 1, 0.8]]},
                 {"id": "sun", "name": "The sun", "kind": "object", "parent": "sky", "box": [0.1, 0.1, 0.2, 0.2]},
                 {"id": "water", "name": "The water", "kind": "area", "box": [0, 0.5, 1, 1]},
                 {"id": "boat", "name": "The boat", "kind": "object", "box": [0.6, 0.2, 0.8, 0.7]}]
        plan = {"parts": parts, "stages": [{"id": "all", "steps": [
            {"id": "sky", "part": "sky"}, {"id": "sun", "part": "sun"}, {"id": "water", "part": "water"},
            {"id": "boat", "part": "boat"}]}]}
        owner = np.zeros((100, 140), np.int32)
        owner[10:20, 14:28] = 1  # the sun, on the sky
        owner[50:] = 2
        owner[20:70, 84:112] = 3  # the boat, in front of both
        return plan, owner

    def test_the_visible_part_leaves_out_paint_a_later_part_covers(self):
        plan, owner = self.scene()
        sky = np.zeros_like(owner, bool)
        sky[:80] = True  # the covers overrun, under the water and the boat
        sun = owner == 1
        nothing = np.zeros_like(sky)
        seen = bs.visible(plan, owner, [sky, sun, owner >= 2, nothing])
        self.assertTrue(np.array_equal(seen[0], (owner <= 1)))  # the sun's place counts until the sun is painted
        self.assertTrue(np.array_equal(seen[1], sun))
        self.assertTrue(np.array_equal(seen[2], owner == 2))  # not the boat it's painted behind
        self.assertFalse(seen[3].any())  # nothing painted: nothing seen

    def test_the_line_says_why_the_outline_reaches_further(self):
        plan, owner = self.scene()
        canvas = {"w_in": 14, "h_in": 10}
        sky_part, water_part = plan["parts"][0], plan["parts"][2]
        later = {2: "The water", 3: "The boat"}
        painted = np.zeros_like(owner, bool)
        painted[:80] = True
        seen = painted & (owner <= 1)
        self.assertEqual(dt.past_words(sky_part, seen, painted, owner, later, canvas),
                         "Paint a little past its bottom, under where the water and the boat will go.")
        # behind an object, with no covers: the painter paints straight through where the boat goes
        painted = (owner == 2) | (owner == 3)
        self.assertEqual(dt.past_words(water_part, owner == 2, painted, owner, {3: "The boat"}, canvas),
                         "The outline also runs under where the boat will go: paint straight through there.")
        # under 1/2 in further (the usual run under the next part's edge) says nothing
        painted = owner == 2
        painted[47:50, :80] = True  # 3 rows of 100 on a 10 in canvas: 0.3 in
        self.assertEqual(dt.past_words(water_part, owner == 2, painted, owner, {3: "The boat"}, canvas), "")
        # paint over an earlier part (a hill's rim laid back) isn't paint a later part covers: no reason to give
        painted = owner == 2
        painted[30:50, :80] = True
        self.assertEqual(dt.past_words(water_part, owner == 2, painted, owner, {3: "The boat"}, canvas), "")


class MergeTests(unittest.TestCase):
    def drafted(self):
        return [{"stage_id": "a", "lines": [{"kind": "where", "text": "Inside.", "edited": False},
                                            {"kind": "how", "text": "Brush: liner.", "edited": False},
                                            {"kind": "how", "text": "Pull.", "edited": False}],
                 "brushes": [{"brush": "liner", "use": "A"}], "stroke_cards": ["liner"],
                 "made_with": "composite:from-finish", "reason": "cut"}]

    def test_summary_tip_and_edited_lines_are_kept_and_twice_is_the_same(self):
        once = dt.merge(None, self.drafted())
        step = once["steps"][0]
        step.update(summary="Pull the twigs.", tip="Thin at the tips.", construct={"title": "x"})
        step["lines"][2] = {"kind": "how", "text": "Pull from the trunk out.", "edited": True}
        step["lines"].append({"kind": "watch", "text": "Mine.", "edited": True})  # a line Claude added
        step["lines"].insert(0, {"kind": "where", "text": "", "edited": True})  # emptied: takes out drafted 'where'
        again = dt.merge(json.loads(json.dumps(once)), self.drafted())
        lines = again["steps"][0]["lines"]
        self.assertEqual(lines[0], {"kind": "where", "text": "", "edited": True})
        self.assertEqual(lines[2], {"kind": "how", "text": "Pull from the trunk out.", "edited": True})
        self.assertEqual(lines[-1]["text"], "Mine.")
        for key in ("summary", "tip", "construct"):
            self.assertEqual(again["steps"][0][key], step[key])
        self.assertEqual(dt.merge(json.loads(json.dumps(again)), self.drafted()), again)

    def test_steps_follow_the_plan_and_a_changed_brush_is_redrafted(self):
        old = {"steps": [{"stage_id": "gone", "summary": "x"},
                         {"stage_id": "a", "brushes": [{"brush": "#6 round", "use": "old"}]}]}
        out = dt.merge(old, self.drafted())
        self.assertEqual([s["stage_id"] for s in out["steps"]], ["a"])
        self.assertEqual(out["steps"][0]["brushes"], [{"brush": "liner", "use": "A"}])
        mine = {"steps": [{"stage_id": "a", "brushes": [{"brush": "liner", "use": "the twigs"}]}]}
        self.assertEqual(dt.merge(mine, self.drafted())["steps"][0]["brushes"], [{"brush": "liner", "use": "the twigs"}])


class CheckPartsTests(unittest.TestCase):
    """Each check on its own, with a plan or text built to fail it."""

    def plan(self, name="red-sailboat"):
        return fixture(name)[1]

    def test_step_and_stage_counts_and_parts_against_the_technique(self):
        self.assertEqual(checks.counts(self.plan(), TECHNIQUE), [])
        plan = self.plan()
        plan["stages"] = plan["stages"][:2]  # 3 steps in 2 stages
        out = " ".join(checks.counts(plan, TECHNIQUE))
        self.assertIn("3 steps; the technique wants 12 to 24. Split", out)
        self.assertIn("2 stages; the technique wants 4 to 9", out)
        plan = self.plan()
        plan["stages"] = [{"id": f"s{i}", "name": "x", "steps": [s]} for i, s in
                          enumerate(s for st in plan["stages"] for s in st["steps"])]  # 14 stages
        plan["stages"][0]["steps"] *= 12  # 25 steps
        out = " ".join(checks.counts(plan, TECHNIQUE))
        self.assertIn("25 steps; the technique wants 12 to 24. Merge", out)
        self.assertIn("14 stages; the technique wants 4 to 9. Group", out)
        plan = self.plan()
        plan["parts"] += [{"id": f"extra-{i}", "kind": "object", "box": [0, 0, 0.1, 0.1]} for i in range(3)]
        self.assertIn("parts with no parent", " ".join(checks.counts(plan, TECHNIQUE)))

    def test_a_stroke_with_no_card_an_unknown_brush_and_a_brush_the_card_doesnt_use(self):
        known = cards.strokes()
        self.assertEqual(checks.strokes_and_brushes(self.plan(), known), [])
        plan = self.plan()
        steps = [s for st in plan["stages"] for s in st["steps"]]
        steps[0]["stroke"] = "swoosh"
        steps[1]["brush"] = "my favorite brush"
        steps[2]["stroke"] = "press-and-lift"  # a round brush's stroke, with a 3/4 inch flat
        steps[3].pop("stroke")
        out = checks.strokes_and_brushes(plan, known)
        self.assertIn("sky-blend: stroke 'swoosh' has no card", out[0])
        self.assertIn("sun: brush 'my favorite brush' isn't one spike/brushes.py knows", out[1])
        self.assertIn("hill: stroke press-and-lift is done with a round brush (its card), not a flat", out[2])
        self.assertIn("water-coat: no stroke", out[3])

    def test_a_paint_no_step_uses(self):
        for name in ("chickadee", "lavender-balloon", "red-sailboat"):
            self.assertEqual(checks.unused_paints(self.plan(name)), [], name)
        plan = self.plan("chickadee")
        plan["paints"].append({**plan["paints"][0], "id": "bird-9", "added": True, "of": None})
        out = checks.unused_paints(plan)
        self.assertEqual(len(out), 1)
        self.assertIn("paint bird-9: no step uses it. Take it out of paints in plan.json, or add it to the step", out[0])

    def test_a_base_only_its_tint_uses_counts_as_used(self):
        plan = self.plan("chickadee")
        used = plan["stages"][0]["steps"][0]["paints"][0]
        base = {**next(c for c in plan["paints"] if c["id"] == used), "id": "base-9", "of": None}
        plan["paints"].append(base)
        next(c for c in plan["paints"] if c["id"] == used)["of"] = "base-9"
        self.assertEqual(checks.unused_paints(plan), [])

    def test_unnamed_paints(self):
        self.assertEqual(checks.paint_names(self.plan()), [])
        plan = self.plan()
        plan["paints"][0].pop("name")
        self.assertIn("paint sky-1: no name in plan.json", checks.paint_names(plan)[0])

    def test_text_for_claude_percentages_long_lines_and_stale_drafts(self):
        plan = self.plan()
        sid = plan["stages"][0]["steps"][0]["id"]
        lines = [{"kind": "where", "text": "Inside.", "edited": False}]
        ok = {"summary": "Blend the sky.", "tip": "Keep the glow low.", "lines": lines}
        text = {s["id"]: dict(ok) for st in plan["stages"] for s in st["steps"]}
        self.assertEqual(checks.text_problems(plan, text, None), [])
        self.assertEqual(checks.text_problems(plan, {**text, sid: {**ok, "summary": "", "tip": ""}}, None),
                         [f"{sid}: no summary in text.json. Write one plain sentence, under 90 characters.",
                          f"{sid}: no tip in text.json. Write one to three sentences only this photo needs (which way "
                          "the strokes run here, which side the light is on, what to leave showing)."])
        bad = {**ok, "summary": "x" * 91, "tip": "At 30% across.",
               "lines": [{"kind": "how", "text": " ".join(["word"] * 41)}, {"kind": "where", "text": "37 percent down"}]}
        out = " ".join(checks.text_problems(plan, {**text, sid: bad}, None))
        self.assertIn("summary is 91 characters", out)
        self.assertIn("its tip gives a percentage", out)
        self.assertIn("its line 2 gives a percentage", out)
        self.assertIn("line 1 is 41 words. A long line is two moves", out)
        stale = {sid: [{"kind": "where", "text": "Somewhere else.", "edited": False}]}
        self.assertIn("Run draft-text again", checks.text_problems(plan, text, stale)[0])
        missing = {k: v for k, v in text.items() if k != sid}
        self.assertIn(f"{sid}: no drafted lines in text.json. Run draft-text.", checks.text_problems(plan, missing, None))
        plan["stages"][0]["steps"][0].pop("name")
        self.assertIn("no name in plan.json", checks.text_problems(plan, text, None)[0])

    def test_a_tape_mark_in_a_tip_summary_or_line_is_a_problem(self):
        # #122: the painter has no tape; steps say where in inches from an edge.
        plan = self.plan()
        sid = plan["stages"][0]["steps"][0]["id"]
        ok = {"summary": "Blend the sky.", "tip": "Keep the glow low.",
              "lines": [{"kind": "where", "text": "Inside.", "edited": False}]}
        text = {s["id"]: dict(ok) for st in plan["stages"] for s in st["steps"]}
        tip = {**ok, "tip": "Stop the glow at the 3/4 mark on the top tape."}
        self.assertEqual(checks.text_problems(plan, {**text, sid: tip}, None),
                         [f"{sid}: its tip places things by tape marks, and the painter has no tape. Say where in inches "
                          "from an edge."])
        line = {**ok, "summary": "Paint down to the tape marks.", "paint_notes": ["Mix it by the middle of the side Tape."],
                "lines": [{"kind": "where", "text": "Below the middle mark on the top tape."}]}
        out = " ".join(checks.text_problems(plan, {**text, sid: line}, None))
        self.assertIn("its summary places things by tape marks", out)
        self.assertIn("its line 1 places things by tape marks", out)
        self.assertIn("its paint note 1 places things by tape marks", out)
        for said in ("Stop at the 1/4 mark on your tape.", "Line it up with the tape.", "Paint to the middle of the tape."):
            self.assertTrue(checks.text_problems(plan, {**text, sid: {**ok, "tip": said}}, None), said)
        for fine in ("Taper each branch to a point.", "Masking tape along the horizon gives a crisp edge."):
            self.assertEqual(checks.text_problems(plan, {**text, sid: {**ok, "tip": fine}}, None), [], fine)
        pct = {**ok, "tip": "At 30% across."}
        self.assertNotIn("tape", " ".join(checks.text_problems(plan, {**text, sid: pct}, None)))

    def test_the_technique_has_version_2_keys_and_version_1_keeps_its_own(self):
        self.assertEqual((TECHNIQUE["v2_step_range"], TECHNIQUE["v2_stage_range"], TECHNIQUE["max_mixes"]),
                         ([12, 24], [4, 9], 10))
        self.assertEqual(TECHNIQUE["step_range"], [5, 12])
        changed = [(a, b) for a, b in zip(TECHNIQUE["rules"], TECHNIQUE["v2_rules"]) if a != b]
        self.assertEqual(len(TECHNIQUE["rules"]), len(TECHNIQUE["v2_rules"]))
        self.assertEqual(len(changed), 1)
        self.assertIn("2 to 5 short instructions per step", json.dumps(changed[0][0]))
        self.assertIn("one move per step", changed[0][1])


@lessons.slow
class TextToolTests(unittest.TestCase):
    """build-steps, step-aids, mix, draft-text, and check on the three fixtures, as the skill runs them."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.old_history = os.environ.get("GESSO_HISTORY")
        os.environ["GESSO_HISTORY"] = str(cls.root / "history")
        cls.lessons, cls.results = {}, {}
        for name in NAMES:  # built once per run and shared (tests/lessons.py)
            cls.lessons[name] = lessons.lesson(name, "checked", cls.root / "base")
            for tool, r in lessons.results(name, "checked").items():
                cls.results[(name, tool)] = r

    @classmethod
    def tearDownClass(cls):
        if cls.old_history is None:
            os.environ.pop("GESSO_HISTORY", None)
        else:
            os.environ["GESSO_HISTORY"] = cls.old_history
        cls.tmp.cleanup()

    def copy(self, name: str) -> Path:
        dst = Path(tempfile.mkdtemp(dir=self.root)) / self.lessons[name].name
        shutil.copytree(self.lessons[name], dst)
        return dst

    def text(self, lesson: Path) -> dict:
        return json.loads((lesson / "text.json").read_text(encoding="utf-8"))

    def write_text(self, lesson: Path, text: dict) -> None:
        (lesson / "text.json").write_text(json.dumps(text), encoding="utf-8")

    def fill_in(self, lesson: Path) -> dict:
        """What Claude writes: a summary and a tip for every step."""
        text = self.text(lesson)
        for t in text["steps"]:
            t.update(summary=f"Paint {t['stage_id']}.", tip="Follow the picture.")
        self.write_text(lesson, text)
        return text

    # Real findings on the fixtures, reported by check rather than hidden (see the issue's close-out):
    # the sailboat's lighter water and the lavender's mid dabs each turn over 10% of the picture from flat to
    # textured in one step, and the lavender's balloon teal can't be mixed from the five tubes with no paint note.
    # The lavender fixture's rows and balloon don't follow their element techniques (#12; see
    # test_elements.PlanTests.test_the_fixture_findings).
    KNOWN = {"chickadee": [], "red-sailboat": [],
             "lavender-balloon": ["lavender: ", "balloon: ", "paint Balloon teal can't be mixed"]}

    def test_after_draft_text_check_leaves_only_summary_and_tip_and_the_known_findings(self):
        for name in NAMES:
            r = self.results[(name, "check")]
            self.assertEqual(r["problems"], r["failures"])  # "every tool prints problems"; failures stays for publish
            plan = fixture(name)[1]
            n = len(bs.flat_steps(plan))
            rest = [f for f in r["failures"] if not re.match(r"^[a-z0-9-]+: no (summary|tip) in text.json", f)]
            self.assertEqual(len(r["failures"]) - len(rest), 2 * n, name)
            self.assertEqual(len(rest), len(self.KNOWN[name]), (name, rest))
            for f, want in zip(rest, self.KNOWN[name]):
                self.assertTrue(f.startswith(want), (name, f))
            d = self.results[(name, "draft-text")]
            self.assertEqual(len(d["for_claude"]), n)
            self.assertEqual(d["cost_usd"], 0.0)

    def test_a_steps_load_line_links_each_term_to_the_card_and_shows_its_two_pictures(self):
        # #99: published after draft-text, every step whose card names a thickness and an amount links both words to
        # the paint-load card and shows both pictures in the line; one with only one of them shows one
        lesson = self.copy("chickadee")
        self.fill_in(lesson)
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        html = (lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("id='basic-paint-load'"), 1)  # the card, in Before you start
        plan = fixture("chickadee")[1]
        known = cards.strokes()
        seen = 0
        for i, s in enumerate(bs.flat_steps(plan)):
            load = known[s["stroke"]].get("load") or {}
            terms = [t for t in (load.get("thickness"), load.get("amount")) if t]
            step = html.split(f'id="step-{i + 1}"', 1)[1].split("</article>", 1)[0]
            line = next(x for x in step.split("<li>") if "Load: " in x) if terms else ""
            for t in terms:
                words = loads.TERMS[t][1]
                self.assertRegex(line, rf'<a class="loadword" href="#basic-paint-load">{words.split()[0] if t in loads.THICKNESS else ""}', s["id"])
                self.assertIn(loads.LABELS[t], line, s["id"])  # its picture, in the line
            if terms:
                self.assertEqual(line.count('class="loadword"'), len(terms), s["id"])
                self.assertEqual(line.count('class="loadpic sm"'), len(terms), s["id"])
                seen += len(terms) == 2
        self.assertGreater(seen, 0)  # the fixture has steps with both

    def test_draft_text_twice_gives_the_same_file_and_keeps_what_claude_wrote(self):
        lesson = self.copy("chickadee")
        before = (lesson / "text.json").read_bytes()
        run_tool("draft-text", "--lesson", str(lesson))
        self.assertEqual((lesson / "text.json").read_bytes(), before)
        text = self.fill_in(lesson)
        lines = text["steps"][4]["lines"]
        at = kinds(text["steps"][4]).index("where")
        lines[at] = {"kind": "where", "text": "Along the arch of the branch.", "edited": True}
        self.write_text(lesson, text)
        run_tool("draft-text", "--lesson", str(lesson))
        after = self.text(lesson)
        self.assertEqual(after, text)
        r = run_tool("check", "--lesson", str(lesson))[1]
        self.assertEqual(r["failures"], [])
        self.assertTrue(r["ok"])

    def test_a_plan_change_makes_the_drafted_lines_stale(self):
        lesson = self.copy("red-sailboat")
        self.fill_in(lesson)
        plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
        plan["stages"][0]["steps"][1]["brush"] = "#8 round"
        (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        out = run_tool("check", "--lesson", str(lesson))[1]["failures"]
        self.assertIn("sun: its drafted lines don't match the plan and pictures any more. Run draft-text again "
                      "(lines marked \"edited\": true are kept).", out)

    def test_outline_and_step_picture_problems_are_gathered(self):
        lesson = self.copy("red-sailboat")
        self.fill_in(lesson)
        plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
        stats = [{"id": p["id"], "kind": p["kind"], "confidence": 0.5 if p["id"] == "sail" else None, "share": 0.1,
                  "pieces": 1, "box_fill": 0.5} for p in plan["parts"]]
        (lesson / "parts" / "stats.json").write_text(json.dumps(stats), encoding="utf-8")
        Image.fromarray(np.zeros((786, 1000, 3), np.uint8)).save(lesson / "05_water-light.png")
        out = run_tool("check", "--lesson", str(lesson))[1]["failures"]
        self.assertIn("sail: the outline model is unsure (confidence 0.5)", " ".join(out))
        self.assertIn("05_water-light.png doesn't match the plan: run build-steps, then step-aids, again", out)
        # a step that adds nothing: the sun path's dark dashes again, right after them
        plan["stages"][2]["steps"].insert(3, dict(plan["stages"][2]["steps"][2], id="path-again"))
        (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        out = run_tool("check", "--lesson", str(lesson))[1]["failures"]
        self.assertIn("path-again: changes almost nothing", " ".join(out))
        self.assertIn("path-again: no drafted lines in text.json. Run draft-text.", out)

    def test_a_paint_name_inside_a_longer_paint_name_is_not_that_paint(self):
        paints = {"Sea turquoise": {}, "Light sea turquoise": {}, "Hull red": {}}
        stage = {"id": "sea-light", "colors": [{"name": "Light sea turquoise"}], "values": [],
                 "steps": ["Streak Light sea turquoise across the water."]}
        self.assertEqual(tools.paints_not_listed([stage], paints), [])
        stage["steps"] = ["Streak Light sea turquoise, then a little Sea turquoise, and dot Hull red."]
        self.assertEqual([x["paint"] for x in tools.paints_not_listed([stage], paints)], ["Sea turquoise", "Hull red"])

    def test_a_texture_jump_is_for_a_whole_part_in_one_step_not_for_a_coat_or_a_pass(self):
        for name in NAMES:  # the fixtures' passes and coats cover a lot at once, and that's how texture is taught
            self.assertFalse(any(": turns " in f for f in self.results[(name, "check")]["failures"]), name)
        plan = {"stages": [{"id": "s", "steps": [{"id": "coat", "part": "p", "show": "flat"},
                                                 {"id": "dabs", "part": "p", "show": "pass"},
                                                 {"id": "all", "part": "q", "show": "full"},
                                                 {"id": "sky", "part": "r", "show": "blend"}]}]}
        jumps = [{"step": i, "share": 0.2} for i in ("coat", "dabs", "all", "sky")]
        old, tools.texture_jumps = tools.texture_jumps, lambda lesson, paths: jumps
        try:
            self.assertEqual([j["step"] for j in checks.texture_jumps(Path("."), plan)], ["all"])
        finally:
            tools.texture_jumps = old

    def test_publish_reports_the_same_texture_jumps_as_check(self):
        lesson = self.copy("chickadee")
        plan = fixture("chickadee")[1]
        steps = bs.flat_steps(plan)
        every = tools.texture_jumps(lesson, [lesson / f"{i + 1:02d}_{s['id']}.png" for i, s in enumerate(steps)])
        self.assertIn("branch-dark", [j["step"] for j in every])  # a flat coat measures its new edge, not texture
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        self.assertEqual(r["texture_jumps"], checks.texture_jumps(lesson, plan))
        self.assertNotIn("branch-dark", [j["step"] for j in r["texture_jumps"]])

    def test_what_publish_counts_is_in_the_list(self):
        lesson = self.copy("chickadee")
        text = self.fill_in(lesson)
        names = publish2.paint_names(fixture("chickadee")[1])
        text["steps"][0]["lines"].append({"kind": "how", "text": f"Add a touch of {names['leaves-1']}.", "edited": True})
        text["steps"][1]["construct"] = {"title": "x", "stages": []}
        # a diagram may give a paint's id; one that's no paint's name, id or hex is listed (#91)
        text["steps"][2]["construct"] = {"title": "y", "paint": "leaves-1", "stages": [
            {"add": [{"circle": [50, 50, 10]}, {"circle": [20, 20, 5], "paint": "Mystery"}]}]}
        self.write_text(lesson, text)
        mixes = json.loads((lesson / "mixes.json").read_text(encoding="utf-8"))
        a, b = names["sky-1"], names["sky-2"]
        mixes[b]["parts"] = mixes[a]["parts"]
        mixes[names["sun-1"]]["reachable"] = False
        (lesson / "mixes.json").write_text(json.dumps(mixes), encoding="utf-8")
        shutil.rmtree(lesson / "aids")
        (lesson / "lesson-standalone.html").write_text("x" * 2000, encoding="utf-8")
        old, publish2.MAX_PAGE_BYTES = publish2.MAX_PAGE_BYTES, 1000
        try:
            out = checks.run(lesson)["failures"]
        finally:
            publish2.MAX_PAGE_BYTES = old
        self.assertIn(f"sky-blend: its text names {names['leaves-1']}, which isn't one of its paints", " ".join(out))
        self.assertIn(f"paints {a} and {b} mix to the same color", " ".join(out))
        self.assertIn(f"paint {names['sun-1']} can't be mixed from these tubes and no step's paint_notes says so", " ".join(out))
        self.assertIn("sun: has a diagram that notes.json's beginner_check.diagrams doesn't explain", " ".join(out))
        self.assertIn("aids/aids.json is missing or was made for other steps: run step-aids", out)
        self.assertIn("the page is 0.0 MB, over 0.001 MB", " ".join(out))
        third = text["steps"][2]["stage_id"]
        gray = [x for x in out if "draws gray" in x]
        self.assertEqual(gray, [f"{third}: diagram 'y', panel 1, shape 2 (circle) has paint 'Mystery', so it draws "
                                "gray. Use a paint's name or id from the plan, or a #hex."])
        os.remove(lesson / "mixes.json")
        self.assertIn("mixes.json is missing or was made for other paints: run mix", checks.run(lesson)["failures"])

    def test_a_broken_card_and_a_broken_plan_are_reported(self):
        lesson = self.copy("red-sailboat")
        known = cards.strokes()
        broken = copy.deepcopy(known)
        broken["zigzag"].pop("result")
        old = cards.strokes
        cards.strokes = lambda: broken
        try:
            out = checks.run(lesson)["failures"]
        finally:
            cards.strokes = old
        self.assertIn("techniques/strokes/zigzag.yaml: no result", out)
        plan = json.loads((lesson / "plan.json").read_text(encoding="utf-8"))
        plan["stages"][0]["steps"][0]["paints"] = ["mauve"]
        (lesson / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        out = checks.run(lesson)["failures"]
        self.assertIn("sky-blend: paint 'mauve' isn't in paints", " ".join(out))
        self.assertIn("fix plan.json first", out[-1])

    def test_publish_runs_check_and_final_refuses_while_anything_fails(self):
        lesson = self.copy("red-sailboat")
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        self.assertIn("sun: no tip in text.json. Write one to three sentences only this photo needs (which way the "
                      "strokes run here, which side the light is on, what to leave showing).", r["check"])
        self.assertNotIn("long_steps", json.dumps(r["check"]))
        data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
        sun = data["stages"][1]
        self.assertEqual(sun["lines"], [{"kind": x["kind"], "text": x["text"]} for x in by_id(self.text(lesson)["steps"])["sun"]["lines"]])
        self.assertEqual(sun["stroke_cards"], ["small-circles"])
        html = (lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn(f"<li>{sun['lines'][0]['text']}</li>", html)
        self.assertNotIn('class="where-words"', html)  # the drafted where line says it; not twice
        code, r = run_tool("publish", "--lesson", str(lesson), "--final")
        self.assertEqual(code, 2)
        self.assertIn("sun: no tip in text.json", r["refused"])
        self.assertEqual(r["refused"].count("texture_jumps"), 0)  # said once, in check's words

    def test_publish_outside_output_leaves_the_history_alone(self):
        import history
        lesson = self.copy("chickadee")
        old_env, old_home = os.environ.pop("GESSO_HISTORY"), history.HISTORY
        history.HISTORY = self.root / "real-history"  # where it would have gone, had it recorded
        try:
            self.assertFalse(tools.history_wanted(lesson))
            self.assertTrue(tools.history_wanted(tools.ROOT / "output" / "x_skill_20261113-090000"))
            code, r = run_tool("publish", "--lesson", str(lesson))
        finally:
            os.environ["GESSO_HISTORY"], history.HISTORY = old_env, old_home
        self.assertEqual(code, 0, r)
        self.assertEqual(r["history"], "skipped: not under output/")
        self.assertFalse((self.root / "real-history").exists())
        self.assertTrue(tools.history_wanted(lesson))  # with GESSO_HISTORY set, as the other tests do

    def test_check_refuses_a_version_1_lesson(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "plan.json").write_text(json.dumps({"steps": []}), encoding="utf-8")
            code, r = run_tool("check", "--lesson", d)
        self.assertEqual(code, 2)
        self.assertIn("version 2", r["refused"])


if __name__ == "__main__":
    unittest.main()
