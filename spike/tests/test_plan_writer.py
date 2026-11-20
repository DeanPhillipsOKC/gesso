"""What the plan's writer is sent and answers with (pipeline v3.1, section 8; #278): its changes made to plan.json
(`plan_writer.apply_plan_changes`, `tools.py plan-change`) and the library cut into what it can pick
(`tools.py library`). Moved here from test_v4_loop.py, with the tools' own tests. No network, no Claude."""

from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import plan_writer as vl  # noqa: E402
import tools  # noqa: E402

PLANS = HERE / "fixtures" / "plans3"


def plan():
    return {
        "plan_version": 3, "why": "back to front",
        "things": [{"id": "sky", "name": "The sky", "element": "sky-blend", "behind": []},
                   {"id": "cat", "name": "The cat", "element": "furry-animal", "behind": ["sky"]}],
        "paints": [{"name": "Sky blue", "color": "#88aadd", "things": ["sky"]},
                   {"name": "Cat gray", "color": "#777777", "things": ["cat"]},
                   {"name": "Shadow gray", "color": "#555555", "things": ["cat"], "of": "Cat gray"},
                   {"name": "Light gray", "color": "#aaaaaa", "things": ["cat"], "of": "Shadow gray"}],
        "stages": [
            {"id": "the-sky", "name": "The sky", "steps": [
                {"id": "blend-sky", "name": "Blend the sky", "paints": ["Sky blue"], "stroke": "side-to-side-blend"}]},
            {"id": "the-cat", "name": "The cat", "steps": [
                {"id": "block-in-cat", "name": "Block in the cat", "paints": ["Cat gray"], "block_in": True},
                {"id": "shade-cat", "name": "Shade the cat", "paints": ["Shadow gray", "Cat gray"]},
                {"id": "light-cat", "name": "Light the cat", "paints": ["Light gray"]}]}]}


def step_ids(p):
    return [s["id"] for st in p["stages"] for s in st["steps"]]


class PlanChangesTests(unittest.TestCase):
    def test_a_merge_renames_every_mention_and_drops_the_old_paint(self):
        before = plan()
        p = vl.apply_plan_changes(before, {"rename_paints": {"Shadow gray": "Cat gray"}})
        self.assertEqual([x["name"] for x in p["paints"]], ["Sky blue", "Cat gray", "Light gray"])
        self.assertEqual(p["stages"][1]["steps"][1]["paints"], ["Cat gray"])  # no paint named twice
        self.assertEqual(p["paints"][2]["of"], "Cat gray")
        self.assertNotIn("of", p["paints"][1])
        self.assertEqual(before, plan())  # the plan it was given is untouched

    def test_a_rename_to_a_new_name_keeps_the_paint(self):
        p = vl.apply_plan_changes(plan(), {"rename_paints": {"Sky blue": "Pale sky blue"}})
        self.assertEqual(p["paints"][0]["name"], "Pale sky blue")
        self.assertEqual(p["stages"][0]["steps"][0]["paints"], ["Pale sky blue"])

    def test_fields_set_removed_and_added(self):
        p = vl.apply_plan_changes(plan(), {
            "top": {"why": "new why"},
            "steps": {"shade-cat": {"unit": "The cat's shading", "paints": ["Shadow gray"]},
                      "block-in-cat": {"block_in": None}},
            "things": {"cat": {"plain": "the plain gray cat"}, "blanket": {"name": "The blanket", "behind": []}},
            "paints": {"Light gray": None}, "stages": {"the-sky": {"name": "The window"}}})
        self.assertEqual(p["why"], "new why")
        shade = p["stages"][1]["steps"][1]
        self.assertEqual((shade["unit"], shade["paints"]), ("The cat's shading", ["Shadow gray"]))
        self.assertNotIn("block_in", p["stages"][1]["steps"][0])
        self.assertEqual(p["things"][1]["plain"], "the plain gray cat")
        self.assertEqual(p["things"][2], {"id": "blanket", "name": "The blanket", "behind": []})
        self.assertEqual(len(p["paints"]), 3)
        self.assertEqual(p["stages"][0]["name"], "The window")

    def test_steps_added_moved_and_removed(self):
        p = vl.apply_plan_changes(plan(), {
            "add_steps": [{"stage": "the-cat", "after": "shade-cat", "step": {"id": "patch-cat", "name": "Patch"}},
                          {"stage": "the-sky", "after": None, "step": {"id": "first", "name": "First"}}],
            "move_steps": [{"step": "light-cat", "stage": "the-sky", "after": "blend-sky"}],
            "steps": {"block-in-cat": None},
            "add_stages": [{"after": "the-cat", "stage": {"id": "the-face", "steps": [{"id": "eyes"}]}}]})
        self.assertEqual(step_ids(p), ["first", "blend-sky", "light-cat", "shade-cat", "patch-cat", "eyes"])

    def test_a_stage_left_empty_goes(self):
        p = vl.apply_plan_changes(plan(), {"steps": {"blend-sky": None}})
        self.assertEqual([st["id"] for st in p["stages"]], ["the-cat"])

    def test_a_whole_plan_is_taken_as_it_is(self):
        whole = copy.deepcopy(plan())
        whole["why"] = "sent whole"
        self.assertIs(vl.apply_plan_changes(plan(), whole), whole)

    def test_what_does_not_apply_is_named(self):
        for ch, says in (({"steps": {"nope": {"name": "x"}}}, "nope"),
                         ({"rename_paints": {"Teal": "Sky blue"}}, "Teal"),
                         ({"add_steps": [{"stage": "the-cat", "after": "gone", "step": {"id": "x"}}]}, "gone"),
                         ({"stages": {"the-cat": {"steps": []}}}, "add_steps"),
                         ({"paints": {"Teal": None}}, "Teal"),
                         ({"whole": True}, "unknown keys")):
            with self.subTest(ch=ch), self.assertRaisesRegex(ValueError, says):
                vl.apply_plan_changes(plan(), ch)


class LibraryTests(unittest.TestCase):
    def test_every_stroke_card_is_listed(self):
        lines = vl.stroke_list().splitlines()
        cards = sorted(p.stem for p in (vl.ROOT / "techniques" / "strokes").glob("*.yaml"))
        self.assertEqual([ln[2:].split(":")[0] for ln in lines], cards)

    def test_the_research_is_cut_at_its_headings(self):
        r = vl.research_sections()
        self.assertIn("For Gesso", r)
        self.assertTrue(r["For Gesso"].startswith("## For Gesso"))
        self.assertFalse(any("Sources" in k for k in r))
        subs = [k for k in r if k.startswith("  ### ")]
        self.assertTrue(subs)
        top = next(k for k in r if k.startswith("## 2."))
        self.assertIn(r[subs[0]].strip(), r[next(k for k in r if k.startswith("## 1."))])
        self.assertIn(r["  ### Dabbing and stippling"].strip(), r[top])
        self.assertEqual(vl.heading("### Dabbing and Stippling"), vl.heading("  ### Dabbing and stippling"))
        self.assertEqual(vl.heading("Mixing"), vl.heading("## 6. Mixing"))




def run(*argv) -> dict:
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = tools.main([str(a) for a in argv])
    out = json.loads(buf.getvalue().strip().splitlines()[-1])
    out["_code"] = code
    return out


class Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gesso-plan-writer-"))
        self.lesson = self.tmp / "lesson"
        self.lesson.mkdir()
        shutil.copyfile(PLANS / "sleeping-cat.json", self.lesson / "plan.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def plan(self) -> dict:
        return json.loads((self.lesson / "plan.json").read_text())

    def write(self, name: str, obj) -> Path:
        p = self.tmp / name
        p.write_text(obj if isinstance(obj, str) else json.dumps(obj))
        return p


class PlanChangeToolTests(Folder):
    def test_a_changed_step_is_made_and_plan_check_runs(self):
        r = run("plan-change", "--lesson", self.lesson, "--changes",
                self.write("c.json", {"steps": {"dab-dark-trees": {"name": "Dab the dark far trees"}}}))
        self.assertTrue(r["applied"])
        self.assertFalse(r["whole_plan"])
        self.assertIn("units", r)  # plan-check's own output
        step = next(s for st in self.plan()["stages"] for s in st["steps"] if s["id"] == "dab-dark-trees")
        self.assertEqual(step["name"], "Dab the dark far trees")
        [log] = json.loads((self.lesson / "plan-changes.json").read_text())
        self.assertEqual(log["changes"]["steps"]["dab-dark-trees"]["name"], "Dab the dark far trees")

    def test_a_removed_paint_merged_into_another(self):
        names = [p["name"] for p in self.plan()["paints"]]
        old, into = names[1], names[0]
        r = run("plan-change", "--lesson", self.lesson, "--changes",
                self.write("c.json", {"rename_paints": {old: into}}))
        self.assertTrue(r["applied"])
        p = self.plan()
        self.assertNotIn(old, [x["name"] for x in p["paints"]])
        self.assertFalse(any(old in (s.get("paints") or []) for st in p["stages"] for s in st["steps"]))

    def test_a_paint_removed_outright(self):
        p = self.plan()
        p["paints"].append({"name": "Unused teal", "color": "#118888", "things": []})
        (self.lesson / "plan.json").write_text(json.dumps(p))
        r = run("plan-change", "--lesson", self.lesson, "--changes",
                self.write("c.json", {"paints": {"Unused teal": None}}))
        self.assertTrue(r["applied"])
        self.assertNotIn("Unused teal", [x["name"] for x in self.plan()["paints"]])

    def test_a_whole_plan_as_the_reply_replaces_it(self):
        whole = self.plan()
        whole["why"] = "sent whole"
        r = run("plan-change", "--lesson", self.lesson, "--changes", self.write("c.json", whole))
        self.assertTrue(r["applied"] and r["whole_plan"])
        self.assertEqual(self.plan(), whole)
        self.assertIsNone(json.loads((self.lesson / "plan-changes.json").read_text())[0]["changes"])

    def test_changes_that_do_not_apply_leave_the_plan(self):
        before = (self.lesson / "plan.json").read_text()
        for ch in ({"steps": {"no-such-step": {"name": "x"}}}, "{not json"):
            with self.subTest(ch=ch):
                r = run("plan-change", "--lesson", self.lesson, "--changes", self.write("c.json", ch))
                self.assertFalse(r["applied"])
                self.assertTrue(r["problems"])
                self.assertEqual((self.lesson / "plan.json").read_text(), before)
        self.assertFalse((self.lesson / "plan-changes.json").exists())


class LibraryToolTests(Folder):
    def test_the_list(self):
        r = run("library", "--lesson", self.lesson)
        self.assertTrue(r["elements"])
        self.assertEqual(len(r["strokes"]), len(list((tools.ROOT / "techniques" / "strokes").glob("*.yaml"))))
        self.assertTrue(r["for_gesso"].startswith("## For Gesso"))
        self.assertIn("## 3. Acrylic behavior that trips beginners", r["research"])
        self.assertIn("  ### Dry brushing", r["research"])
        self.assertNotIn("For Gesso", r["research"])

    def test_the_picks_are_copied_and_a_heading_matches_without_its_number(self):
        el = sorted(p.stem for p in (tools.ROOT / "techniques" / "elements").glob("*.yaml"))[0]
        card = sorted(p.stem for p in (tools.ROOT / "techniques" / "strokes").glob("*.yaml"))[0]
        r = run("library", "--lesson", self.lesson, "--picks", self.write("p.json", {
            "elements": [el], "strokes": [f"techniques/strokes/{card}.yaml"],
            "research": ["acrylic behavior that trips beginners", "### Dry Brushing", "For Gesso"]}))
        self.assertEqual(r["problems"], [])
        lib = self.lesson / "library"
        self.assertTrue((lib / "elements" / f"{el}.yaml").exists())
        self.assertTrue((lib / "strokes" / f"{card}.yaml").exists())
        md = (lib / "research.md").read_text()
        self.assertLess(md.index("## For Gesso"), md.index("## 3. Acrylic behavior that trips beginners"))
        self.assertIn("### Dry brushing", md)
        self.assertNotIn("### Glazing", md)  # not picked

    def test_a_subsection_inside_a_picked_section_is_sent_once(self):
        got = vl.resolve({"research": ["2. Stroke and brush vocabulary", "Dabbing and stippling"]})
        self.assertEqual([k.strip() for k in got["research"]], ["## 2. Stroke and brush vocabulary"])

    def test_an_unknown_pick_is_a_problem_and_the_rest_is_kept(self):
        card = sorted(p.stem for p in (tools.ROOT / "techniques" / "strokes").glob("*.yaml"))[0]
        r = run("library", "--lesson", self.lesson, "--picks",
                self.write("p.json", {"strokes": [card, "no-such-card"], "research": ["No such heading"]}))
        self.assertEqual(len(r["problems"]), 2)
        self.assertTrue((self.lesson / "library" / "strokes" / f"{card}.yaml").exists())

    def test_a_second_ask_adds_to_the_first(self):
        cards = sorted(p.stem for p in (tools.ROOT / "techniques" / "strokes").glob("*.yaml"))[:2]
        run("library", "--lesson", self.lesson, "--picks", self.write("p.json", {"strokes": [cards[0]]}))
        r = run("library", "--lesson", self.lesson, "--picks", self.write("p.json", {"strokes": [cards[1]]}))
        self.assertEqual(sorted(p.name for p in (self.lesson / "library" / "strokes").iterdir()),
                         [f"{c}.yaml" for c in cards])
        self.assertEqual(r["added"]["strokes"], [cards[1]])

    def test_a_lessons_drafted_element_can_be_picked(self):
        (self.lesson / "elements").mkdir()
        (self.lesson / "elements" / "drafted-thing.yaml").write_text("name: A drafted thing\n")
        got = vl.resolve({"elements": ["drafted-thing"]}, self.lesson)
        self.assertIn("drafted-thing", got["elements"])

    def test_picks_of_the_wrong_shape_write_nothing(self):
        r = run("library", "--lesson", self.lesson, "--picks", self.write("p.json", {"cards": ["x"]}))
        self.assertTrue(r["problems"])
        self.assertFalse((self.lesson / "library").exists())


class BriefTests(unittest.TestCase):
    def test_the_briefs_changes_shape_is_the_codes(self):
        import re
        brief = (tools.ROOT / ".claude" / "skills" / "paint-lesson" / "v3" / "plan-brief.md").read_text()
        block = brief[brief.index("## Fixing the plan"):]
        block = block[block.index("```json") + 7:]
        block = block[:block.index("```")]
        self.assertEqual(set(re.findall(r'^\s*[{ ]"(\w+)":', block, re.M)), vl.CHANGE_KEYS)
        for tool in ("library --lesson", "--picks", "plan-change --lesson"):
            self.assertIn(tool, brief)


if __name__ == "__main__":
    unittest.main()
