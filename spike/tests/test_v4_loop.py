"""The v4 loop's cost cuts (#253): the plan's writer's changes made to plan.json, the bill priced as the API would
charge it, and the library cut into what the writer can pick. No network, no Claude."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))

import v4_loop as vl  # noqa: E402


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


def call(session, at, seconds, turn, inp=0, write=0, read=0, out=0):
    return {"session": session, "at": at, "seconds": seconds, "turn": turn, "input_tokens": inp,
            "cache_write_tokens": write, "cache_read_tokens": read, "output_tokens": out}


class ApiCostTests(unittest.TestCase):
    def test_a_call_nothing_follows_is_plain_input(self):
        [c] = vl.api_costs([call("a", "2026-11-19T10:00:30", 30, 1, write=1_000_000, out=1000)])
        self.assertAlmostEqual(c, 4.00 + 0.02)

    def test_a_conversation_that_goes_on_writes_the_five_minute_cache(self):
        cs = vl.api_costs([call("a", "2026-11-19T10:00:30", 30, 1, write=1_000_000),
                           call("a", "2026-11-19T10:02:00", 30, 2, write=100_000, read=1_000_000)])
        self.assertAlmostEqual(cs[0], 5.00)
        self.assertAlmostEqual(cs[1], 0.40 + 0.20)

    def test_a_cache_older_than_five_minutes_is_sent_again(self):
        cs = vl.api_costs([call("a", "2026-11-19T10:00:30", 30, 1, write=1_000_000),
                           call("a", "2026-11-19T10:10:00", 30, 2, write=100_000, read=1_000_000)])
        self.assertAlmostEqual(cs[0], 4.00)  # nothing read it in time
        self.assertAlmostEqual(cs[1], 4.40)

    def test_a_later_message_sent_uncached_is_priced_as_reading_the_conversation(self):
        first = call("a", "2026-11-19T10:00:30", 30, 1, write=1_000_000)
        late = call("a", "2026-11-19T10:02:00", 30, 2, inp=1_100_000)
        late["cache"] = "none"
        cs = vl.api_costs([first, late])
        self.assertAlmostEqual(cs[0], 5.00)
        self.assertAlmostEqual(cs[1], 0.40 + 0.20)

    def test_without_claude_code_leaves_out_its_first_message_lines(self):
        [c] = vl.api_costs([call("a", "2026-11-19T10:00:30", 30, 1, write=1_000_000)], without_claude_code=True)
        self.assertAlmostEqual(c, (1_000_000 - vl.CLAUDE_CODE_ADDED) * 4.00 / 1e6)

    def test_the_cut_run_pricing_reads_claude_codes_five_minute_split(self):
        u = {"input_tokens": 10, "cache_creation_input_tokens": 1000, "output_tokens": 0,
             "cache_creation": {"ephemeral_5m_input_tokens": 1000, "ephemeral_1h_input_tokens": 0}}
        self.assertAlmostEqual(vl.cost(u), (10 * 4 + 1000 * 5) / 1e6)


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


if __name__ == "__main__":
    unittest.main()


class CheckerCostTests(unittest.TestCase):
    """#268: Haiku's rates, and how a setting's answers are scored against Opus's."""

    def test_haiku_rates(self):
        u = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        self.assertAlmostEqual(vl.cost(u, ["claude-haiku-5-5"]), 0.60)
        self.assertAlmostEqual(vl.cost(u, "sonnet"), 12.00)
        self.assertAlmostEqual(vl.cost(u, ["claude-opus-5-5"]), 24.00)

    def test_compare(self):
        import v4_checker_cost as cc
        ref = [{"look": "U01", "stray": False, "left": True}, {"look": "U02", "stray": False, "left": False},
               {"look": "U03", "stray": True, "left": False}]
        got = [{"look": "U01", "stray": False, "left": True}, {"look": "U02", "stray": True, "left": False},
               {"look": "U03", "stray": False, "left": False}]
        c = cc.compare(ref, got)
        self.assertEqual((c["ref_marks"], c["caught"], c["agree_looks"]), (2, 1, 1))
        self.assertEqual(c["missed"], ["U03:stray"])
        self.assertEqual(c["added"], ["U02:stray"])
