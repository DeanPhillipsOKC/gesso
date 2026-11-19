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
from unittest import mock
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
from lessons import CANVAS, NAMES  # noqa: E402

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
            cls.owners[name] = lessons.owner(name)
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
        self.assertNotIn("dry", kinds(d["blend-sky"]))  # nothing under the first step
        self.assertEqual(d["paint-sun"]["lines"][0]["text"], dt.DRY.format(what="the blue and gold sky"))
        self.assertEqual(d["pull-far-trunks"]["lines"][0]["text"], dt.DRY.format(what="the sky and the sun"))
        self.assertIn("the chickadee", d["shade-chickadee"]["lines"][0]["text"])  # inside a stage: the part's name
        self.assertIn("the far woods", d["shade-chickadee"]["lines"][0]["text"])  # and what it sits over

    def test_rinse_before_a_far_color_or_the_lightest_yet(self):
        d = by_id(self.built["chickadee"][3])
        self.assertEqual([x["text"] for x in d["paint-white-patches"]["lines"] if x["kind"] == "rinse"], [dt.RINSE_LIGHT])
        self.assertEqual([x["text"] for x in d["dab-dark-far-leaves"]["lines"] if x["kind"] == "rinse"], [dt.RINSE])
        self.assertNotIn("rinse", kinds(d["paint-sun"]))  # pale yellow again, then sun cream

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
        where = next(x["text"] for x in sized["block-in-chickadee"]["lines"] if x["kind"] == "where")
        self.assertRegex(where, r"\d in from the (top|left) edge")
        self.assertNotIn("the whole canvas", " ".join(x["text"] for x in sized["block-in-branch"]["lines"]))

    def test_where_leaves_out_stray_specks_far_from_the_part(self):
        # #90: two specks of a thing far from it put its words at the canvas's edge. Specks of the bird added to its
        # block-in's area and to its shape leave the words where they were.
        plan, pictures, masks, drafted = self.built["chickadee"]
        i = [s["id"] for s in bs.flat_steps(plan)].index("block-in-chickadee")
        part = [p["id"] for p in plan["parts"]].index(bs.flat_steps(plan)[i]["part"])
        owner, specked = self.owners["chickadee"].copy(), [m.copy() for m in masks]
        h, w = owner.shape
        for y, x in ((h // 2, 0), (h - 4, w // 2)):  # at the left edge, and at the bottom
            specked[i][y:y + 3, x:x + 3] = True
            owner[y:y + 3, x:x + 3] = part
        where = lambda entries: [x["text"] for x in by_id(entries)["block-in-chickadee"]["lines"] if x["kind"] == "where"]
        self.assertEqual(where(dt.draft(plan, pictures, specked, None, CANVAS, owner=owner)), where(drafted))
        self.assertNotIn("at the left edge", " ".join(where(drafted)))

    def test_paints_go_darkest_first_and_a_blend_top_to_bottom(self):
        plan = self.built["red-sailboat"][0]
        d = by_id(self.built["red-sailboat"][3])
        names = publish2.paint_names(plan)
        self.assertEqual(next(x["text"] for x in d["blend-sky"]["lines"] if x["kind"] == "paints"),
                         f"Paints, top to bottom: {names['pale-gold']}, {names['sky-violet']}, {names['sunset-pink']}, "
                         f"then {names['sunset-orange']}.")
        leaves = by_id(self.built["chickadee"][3])["block-in-leaves"]
        names = publish2.paint_names(self.built["chickadee"][0])
        paints = next(x["text"] for x in leaves["lines"] if x["kind"] == "paints")
        self.assertIn(f"darkest first: {names['red-orange']}, then {names['golden-yellow']}", paints)

    def test_a_paint_used_again_is_mixed_once_for_all_its_steps(self):
        plan, _, _, drafted = self.built["chickadee"]
        names = publish2.paint_names(plan)
        mix = [x["text"] for x in by_id(drafted)["shade-branch"]["lines"] if x["kind"] == "mix"]
        self.assertEqual(mix, [f"Mix enough {names['dark-brown']} for this step and step 12; cover it between them."])
        self.assertNotIn("mix", kinds(by_id(drafted)["line-twigs-stems-veins"]))  # its second use: "from step 11"

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
        self.assertIn(dt.LEAVE_SHOWING.format(steps="steps 8 and 9"), [x["text"] for x in d["shade-branch"]["lines"]])
        self.assertIn("coats", kinds(d["light-branch"]))  # warm buff over the dark branch
        self.assertNotIn("coats", kinds(d["block-in-chickadee"]))  # the same buff over the far woods
        self.assertNotIn("coats", kinds(d["blend-sky"]))  # over white canvas

    def test_step_back_at_the_end_of_every_stage(self):
        for name, (plan, _, _, drafted) in self.built.items():
            last = {st["steps"][-1]["id"] for st in plan["stages"]}
            self.assertEqual({d["stage_id"] for d in drafted if "step-back" in kinds(d)}, last)

    def test_left_out_names_each_card_field_the_research_lacks(self):
        gaps = dt.left_out(self.built["chickadee"][0])
        self.assertIn("card x-stroke has no mistakes, so no watch-out line", gaps["blend-sky"])
        plan = copy.deepcopy(self.built["chickadee"][0])
        plan["stages"][0]["steps"][0]["stroke"] = "no-such-card"
        self.assertIn("no stroke card", dt.left_out(plan)["blend-sky"][0])

    def test_a_long_card_text_is_split_between_sentences(self):
        text = " ".join(["One two three four five six seven eight nine ten."] * 5)
        lines = dt.split(text, "how")
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(len(x["text"].split()) <= dt.MAX_WORDS and x["text"].endswith(".") for x in lines))

    def where_line(self, name: str, step: str) -> str:
        d = by_id(self.built[name][3])[step]
        return " ".join(x["text"] for x in d["lines"] if x["kind"] == "where")

    def test_where_gives_the_visible_horizon_not_the_paint_under_later_parts(self):
        # #126: the sky is painted past the horizon on purpose, under the sea, and was measured whole, so the inches
        # were off. The lines must place the horizon the finished painting shows, within 1/2 in.
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

        sky = self.where_line("red-sailboat", "blend-sky")
        self.assertLessEqual(abs(inches_down(sky, "bottom") - sky_bottom), 0.5, sky)
        self.assertIn("The outline also runs under where the sea", sky)
        water = self.where_line("red-sailboat", "lay-in-water")
        self.assertLessEqual(abs(inches_down(water, "top") - water_top), 0.5, water)
        # a small thing is placed by its own shape, not its soft rim
        self.assertIn("about 3/4 in wide", self.where_line("red-sailboat", "paint-sun"))

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
        # paint over an earlier part (a hill's rim laid back) isn't paint a later part covers, but the outline still
        # reaches past the words, so the line says so (PR #142 review); with no earlier parts given, nothing
        painted = owner == 2
        painted[30:50, :80] = True
        self.assertEqual(dt.past_words(water_part, owner == 2, painted, owner, {3: "The boat"}, canvas), "")
        self.assertEqual(dt.past_words(water_part, owner == 2, painted, owner, {3: "The boat"}, canvas,
                                       {0: "The sky"}),
                         "The outline also reaches onto the sky, painted already: there, only soften this paint "
                         "into its edge and leave it showing.")

    def test_a_stray_speck_of_the_outline_isnt_explained(self):
        # #90: the words leave a part's stray specks out, so the outline's own specks don't count as reaching past
        # them: a 2 x 2 speck of the water's outline up on the boat says nothing; a real piece there still does
        plan, owner = self.scene()
        canvas, water_part = {"w_in": 14, "h_in": 10}, plan["parts"][2]
        painted = owner == 2
        painted[22:24, 90:92] = True  # on the boat, 2 1/2 in above the water: under 1% of the outline
        self.assertEqual(dt.past_words(water_part, owner == 2, painted, owner, {3: "The boat"}, canvas), "")
        painted[22:40, 86:110] = True  # 432 px of 6000: a piece of the outline, not a speck
        self.assertEqual(dt.past_words(water_part, owner == 2, painted, owner, {3: "The boat"}, canvas),
                         "The outline also runs under where the boat will go: paint straight through there.")


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


@lessons.slow
class CheckPartsTests(unittest.TestCase):
    """Each check on its own, with a plan (a fixture's, in version 2's shape) or text built to fail it."""

    def plan(self, name="red-sailboat"):
        return lessons.built(name)[0]

    def test_a_stroke_with_no_card_an_unknown_brush_and_a_brush_the_card_doesnt_use(self):
        known = cards.strokes()
        self.assertEqual(checks.strokes_and_brushes(self.plan(), known), [])
        plan = self.plan()
        steps = [s for st in plan["stages"] for s in st["steps"]]
        steps[0]["stroke"] = "swoosh"
        steps[1]["brush"] = "my favorite brush"
        steps[2]["stroke"] = "press-and-lift"  # a round brush's stroke, with a 3/4 inch flat
        steps[3].pop("stroke")
        steps[2]["brush"] = "3/4 inch flat"
        out = checks.strokes_and_brushes(plan, known)
        self.assertIn(f"{steps[0]['id']}: stroke 'swoosh' has no card", out[0])
        self.assertIn(f"{steps[1]['id']}: brush 'my favorite brush' isn't one spike/brushes.py knows", out[1])
        self.assertIn(f"{steps[2]['id']}: stroke press-and-lift is done with a round brush (its card), not a flat", out[2])
        self.assertIn(f"{steps[3]['id']}: no stroke", out[3])

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
        self.assertIn(f"paint {plan['paints'][0]['id']}: no name in plan.json", checks.paint_names(plan)[0])

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

    # Real findings on the fixtures, reported by check rather than hidden: the sailboat's deep teal can't be mixed
    # from the five tubes, and no paint note says so (the run that made the fixture had one)
    # Fitted to what their units moved (#250): the balloon's blue and the lavender's lighter purples are brighter
    # than these tubes mix; the sailboat's light rim and light water aren't in its finish, so they keep the plan's
    # rough colors, and the rim's is the sky's pink
    KNOWN = {"chickadee": [], "lavender-balloon": ["paint Balloon blue can't be mixed", "paint Mid lavender can't be mixed",
                                                   "paint Pale lilac can't be mixed"],
             "red-sailboat": ["paints Sunset pink and Light red mix to the same color", "paint Deep teal can't be mixed",
                              "paint Light teal can't be mixed"]}

    def test_after_draft_text_check_leaves_only_summary_and_tip_and_the_known_findings(self):
        for name in NAMES:
            r = self.results[(name, "check")]
            self.assertEqual(r["problems"], r["failures"])  # "every tool prints problems"; failures stays for publish
            plan = lessons.built(name)[0]
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
        plan = lessons.built("chickadee")[0]
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
        self.assertIn("plan.json or the chain changed since the step pictures were made", out[0])
        code, r = run_tool("build-steps", "--lesson", str(lesson))  # the brush isn't in the chain's requests
        self.assertEqual(code, 0, r)
        out = run_tool("check", "--lesson", str(lesson))[1]["failures"]
        self.assertIn("paint-sun: its drafted lines don't match the plan and pictures any more. Run draft-text again "
                      "(lines marked \"edited\": true are kept).", out)

    def test_a_step_picture_build_steps_didnt_write_is_reported(self):
        lesson = self.copy("red-sailboat")
        self.fill_in(lesson)
        first = sorted(lesson.glob("05_*.png"))[0]
        with Image.open(first) as img:
            size = img.size
        Image.fromarray(np.zeros((size[1], size[0], 3), np.uint8)).save(first)
        out = run_tool("check", "--lesson", str(lesson))[1]["failures"]
        self.assertIn(f"{first.name} isn't the file build-steps wrote", " ".join(out))

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
        plan = lessons.built("chickadee")[0]
        steps = bs.flat_steps(plan)
        full = next(s["id"] for s in steps if s.get("show", "full") == "full")
        blend = next(s["id"] for s in steps if s.get("show") == "blend")
        jumps = [{"step": full, "share": 0.2}, {"step": blend, "share": 0.3}]
        with mock.patch.object(tools, "texture_jumps", lambda lesson, paths: jumps):
            code, r = run_tool("publish", "--lesson", str(lesson))
            self.assertEqual(code, 0, r)
            self.assertEqual(r["texture_jumps"], checks.texture_jumps(lesson, plan))
            self.assertEqual([j["step"] for j in r["texture_jumps"]], [full])  # a blend is one wet move
            notes = checks.run(lesson)["notes"]
        self.assertIn(f"{full}: turns 20% of the picture from flat to textured in one step", notes)  # a note, not a failure

    def test_what_publish_counts_is_in_the_list(self):
        lesson = self.copy("chickadee")
        text = self.fill_in(lesson)
        plan = lessons.built("chickadee")[0]
        names = publish2.paint_names(plan)
        steps = bs.flat_steps(plan)
        other = next(c["id"] for c in plan["paints"] if c["id"] not in steps[0]["paints"])
        one, two = [c["id"] for c in plan["paints"] if not c.get("of")][:2]
        text["steps"][0]["lines"].append({"kind": "how", "text": f"Add a touch of {names[other]}.", "edited": True})
        text["steps"][1]["construct"] = {"title": "x", "stages": []}
        # a diagram may give a paint's id; one that's no paint's name, id or hex is listed (#91)
        text["steps"][2]["construct"] = {"title": "y", "paint": other, "stages": [
            {"add": [{"circle": [50, 50, 10]}, {"circle": [20, 20, 5], "paint": "Mystery"}]}]}
        self.write_text(lesson, text)
        mixes = json.loads((lesson / "mixes.json").read_text(encoding="utf-8"))
        a, b = names[one], names[two]
        mixes[b]["parts"] = mixes[a]["parts"]
        mixes[names[other]]["reachable"] = False
        (lesson / "mixes.json").write_text(json.dumps(mixes), encoding="utf-8")
        shutil.rmtree(lesson / "aids")
        (lesson / "lesson-standalone.html").write_text("x" * 2000, encoding="utf-8")
        old, publish2.MAX_PAGE_BYTES = publish2.MAX_PAGE_BYTES, 1000
        try:
            out = checks.run(lesson)["failures"]
        finally:
            publish2.MAX_PAGE_BYTES = old
        self.assertIn(f"{steps[0]['id']}: its text names {names[other]}, which isn't one of its paints", " ".join(out))
        self.assertIn(f"paints {a} and {b} mix to the same color", " ".join(out))
        self.assertIn(f"paint {names[other]} can't be mixed from these tubes and no step's paint_notes says so", " ".join(out))
        self.assertIn(f"{steps[1]['id']}: has a diagram that notes.json's beginner_check.diagrams doesn't explain", " ".join(out))
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
        self.assertIn("blend-sky: paint 'mauve' isn't in the plan's paints", " ".join(out))
        self.assertIn("fix plan.json first", out[-1])

    def test_publish_runs_check_and_final_refuses_while_anything_fails(self):
        lesson = self.copy("red-sailboat")
        code, r = run_tool("publish", "--lesson", str(lesson))
        self.assertEqual(code, 0, r)
        self.assertIn("paint-sun: no tip in text.json. Write one to three sentences only this photo needs (which way "
                      "the strokes run here, which side the light is on, what to leave showing).", r["check"])
        self.assertNotIn("long_steps", json.dumps(r["check"]))
        data = json.loads((lesson / "lesson.json").read_text(encoding="utf-8"))
        sun = data["stages"][1]
        self.assertEqual(sun["lines"], [{"kind": x["kind"], "text": x["text"]} for x in by_id(self.text(lesson)["steps"])["paint-sun"]["lines"]])
        self.assertEqual(sun["stroke_cards"], ["small-circles"])
        html = (lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn(f"<li>{sun['lines'][0]['text']}</li>", html)
        self.assertNotIn('class="where-words"', html)  # the drafted where line says it; not twice
        code, r = run_tool("publish", "--lesson", str(lesson), "--final")
        self.assertEqual(code, 2)
        self.assertIn("paint-sun: no tip in text.json", r["refused"])
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
        self.assertIn("version 3", r["refused"])


if __name__ == "__main__":
    unittest.main()
