"""The v4 writer's and finisher's cost cuts (#267): Sonnet's prices, the model and effort a helper is called with,
the lean fact sheet, and the arc asked as the writer's next message; and the paint check on the words (#270). No
network, no Claude."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))

import v4_loop as vl  # noqa: E402
import v4_writer_cost as wc  # noqa: E402

FACTS = """## Step 5 (block-in-frame): Block in the window frame
Part: The window frame. Its first step. Paints: Warm cream.
Where line (kept as it is, word for word): Inside the outlined area. It's about 3 in wide.
This step's area: 3 in (3 1/16) wide, 7 in (6 15/16) tall; its middle 1 3/4 in (1 3/4) from the left edge.
The window frame as the finish shows it: its left side 0 in (0) from the left edge.
Next to it: below The sky, touching (2 in (1 15/16) apart down); above The sill (1/2 in (7/16) apart down) (not painted yet).
Under it, step 6 (Deep wall blue): at the middle row 2 in (2 1/8) to 2 1/4 in (2 3/8) from the left edge."""


class PricesTests(unittest.TestCase):
    def test_sonnet_costs_half_of_opus(self):
        u = {"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 1_000_000,
             "cache_creation": {"ephemeral_5m_input_tokens": 1_000_000, "ephemeral_1h_input_tokens": 0}}
        self.assertAlmostEqual(vl.cost(u), 4 + 2 + 0.20 + 5)
        self.assertAlmostEqual(vl.cost(u, ["claude-sonnet-5-5"]), 2 + 1 + 0.10 + 2.50)

    def test_api_pricing_reads_each_calls_model(self):
        c = {"session": "a", "at": "2026-11-19T10:00:30", "seconds": 30, "turn": 1, "input_tokens": 0,
             "cache_write_tokens": 1_000_000, "cache_read_tokens": 0, "output_tokens": 0}
        [opus, sonnet] = vl.api_costs([c, {**c, "session": "b", "model": ["claude-sonnet-5-5"]}])
        self.assertAlmostEqual(opus, 4.00)
        self.assertAlmostEqual(sonnet, 2.00)


class HelperTests(unittest.TestCase):
    def test_a_helper_passes_its_model_and_effort(self):
        led = wc.Ledger(set="c1", variant="x", picture="p", part="words")
        h = wc.helper("writer", "sys", ["sonnet", "effort-low"], led)
        self.assertEqual((h.model, h.effort), ("sonnet", "low"))
        f = wc.helper("finisher", "sys", ["f-sonnet"], led, "f-")
        self.assertEqual((f.model, f.effort), ("sonnet", None))
        self.assertEqual((wc.helper("w", "s", ["f-sonnet"], led).model), None)  # a finisher's cut isn't the writer's
        got = {}

        def fake(content, system, **kw):
            got.update(kw)
            return {"text": "{}", "session": "s1", "usage": {"input_tokens": 10, "output_tokens": 1},
                    "cli_cost_usd": 0, "seconds": 1, "turns": 1, "model": ["claude-sonnet-5-5"]}

        with mock.patch.object(vl, "call_claude", fake), mock.patch.object(wc, "update", lambda fn: None):
            h.ask(vl.Message().text("hi"), "test")
        self.assertEqual((got["model"], got["effort"]), ("sonnet", "low"))


class LeanFactsTests(unittest.TestCase):
    def test_lean_facts_drop_what_the_lines_do_not_use(self):
        out = wc.lean_facts(FACTS)
        self.assertNotIn("Where line", out)
        self.assertNotIn("as the finish shows it", out)
        self.assertNotIn("not painted yet", out)
        self.assertNotIn("(3 1/16)", out)
        self.assertIn("3 in wide, 7 in tall; its middle 1 3/4 in from the left edge", out)
        self.assertIn("Next to it: below The sky, touching (2 in apart down).", out)
        self.assertIn("Under it, step 6 (Deep wall blue): at the middle row 2 in to 2 1/4 in from the left edge", out)

    def test_a_neighbour_line_with_only_unpainted_things_goes(self):
        out = wc.lean_facts("Next to it: above The sill, touching (not painted yet).\nPart: x.")
        self.assertEqual(out, "Part: x.")


# A made-up lesson of two steps: the block-in lists Cat gray, the shading lists Cat shadow only.
LESSON = {"steps": [
    {"n": 1, "id": "block-cat", "stroke": "flat-fill", "paints": [{"name": "Cat gray"}, {"name": "Light cat gray"}]},
    {"n": 2, "id": "shade-cat", "stroke": "flat-fill", "paints": [{"name": "Cat shadow"}]}]}
PLAN = {"paints": [{"name": n} for n in ("Cat gray", "Light cat gray", "Cat shadow")],
        "stages": [{"id": "cat", "name": "The cat", "steps": [{"id": "block-cat", "stroke": "flat-fill",
                                                               "paints": ["Cat gray", "Light cat gray"]},
                                                              {"id": "shade-cat", "stroke": "flat-fill",
                                                               "paints": ["Cat shadow"]}]}]}


def text(lines: dict) -> dict:
    return {"steps": [{"stage_id": sid, "summary": "", "tip": "", "lines": [dict(x) for x in ls]}
                      for sid, ls in lines.items()]}


class PaintCheckTests(unittest.TestCase):
    def setUp(self):
        for target, value in ((wc.student, "lesson"), (wc.teacher, "plan")):
            pt = mock.patch.object(target, value, lambda pic, v=value: LESSON if v == "lesson" else PLAN)
            pt.start()
            self.addCleanup(pt.stop)

    def test_a_sentence_naming_a_paint_its_step_does_not_list_fails(self):
        t = text({"block-cat": [{"kind": "strokes", "text": "Fill the cat with Cat gray. Add Light cat gray on top."}],
                  "shade-cat": [{"kind": "first", "text": "The Cat gray must be dry. Mix Cat shadow."},
                                {"kind": "leave", "text": "Leave the Light cat gray on the back showing."}]})
        got = [(c["id"], c["field"], c["paint"], c["sentence"]) for c in wc.paint_failures("p", t)]
        self.assertEqual(got, [("shade-cat", "line 1 (first)", "Cat gray", "The Cat gray must be dry."),
                               ("shade-cat", "line 2 (leave)", "Light cat gray",
                                "Leave the Light cat gray on the back showing.")])  # not Cat gray inside it too
        self.assertIn("which isn't one of its paints (Cat shadow)", wc.say_paint(wc.paint_failures("p", t)[0]))

    def test_the_arc_reads_only_its_back_lines(self):
        t = text({"block-cat": [], "shade-cat": [{"kind": "first", "text": "The Cat gray must be dry."},
                                                 {"kind": "back", "step": 1, "text": "Fill flat, as with the Cat gray."}]})
        [c] = wc.paint_failures("p", t, back_only=True)
        self.assertEqual(c["field"], "line 2 (back)")
        self.assertEqual(wc.as_arc_failure(c)["where"], "step shade-cat.back")

    def test_what_still_fails_is_taken_out_and_an_empty_line_goes(self):
        t = text({"block-cat": [], "shade-cat": [{"kind": "first", "text": "The Cat gray must be dry."},
                                                 {"kind": "strokes", "text": "Mix Cat shadow. Glaze it into Cat gray."}]})
        gone = wc.take_out_paints(t, wc.paint_failures("p", t))
        self.assertEqual([g["sentence"] for g in gone], ["The Cat gray must be dry.", "Glaze it into Cat gray."])
        self.assertEqual(t["steps"][1]["lines"], [{"kind": "strokes", "text": "Mix Cat shadow."}])
        self.assertEqual(wc.paint_failures("p", t), [])

    def test_the_writer_gets_one_round_with_only_the_steps_that_change(self):
        """write_words with paint-check: check-text passes, the paint round fixes one step and leaves the other
        naming Cat gray, which is taken out; the arc's back line names it too, goes back with the arc's round,
        and is dropped when it still does."""
        first = {"steps": {"block-cat": {"strokes": "Fill the cat with Cat gray."},
                           "shade-cat": {"first": "The Cat gray must be dry.", "strokes": "Glaze Cat shadow on. "
                                         "Blend it into the Cat gray."}}}
        fixed = {"steps": {"shade-cat": {"first": "The gray from step 1 must be dry.", "strokes": "Glaze Cat "
                                         "shadow on. Blend it into the Cat gray."}}}
        arc_obj = {"opening": {}, "stages": {}, "steps": {"shade-cat": {"back": {"step": 1, "text": "Flat, as with "
                                                                                 "the Cat gray."}}}}
        replies = [first, fixed, arc_obj, arc_obj]
        sent = []

        class FakeHelper:
            def ask_json(self, m, label, **kw):
                sent.append((label, "".join(b.get("text", "") for b in m.blocks)))
                return json.loads(json.dumps(replies.pop(0)))

        saved = {}
        with mock.patch.object(wc, "helper", lambda *a, **k: FakeHelper()), \
                mock.patch.object(wc, "writer_message", lambda *a: vl.Message()), \
                mock.patch.object(wc, "arc_message_same", lambda *a: vl.Message()), \
                mock.patch.object(wc.teacher, "check", lambda pic, t: {"failures": [], "claims": []}), \
                mock.patch.object(wc.arc, "check_arc", lambda pic, obj: []), \
                mock.patch.object(wc, "update", lambda fn: fn(saved.setdefault("st", {"words": {}}))):
            wc.write_words("c1", "lean-paints", "p")
        self.assertEqual([label for label, _ in sent], ["W1 words", "W1 paints", "W2 arc", "W2 arc feedback"])
        self.assertIn("only the steps that change", sent[1][1])
        self.assertIn("A step you leave out keeps its words", sent[1][1])
        self.assertIn("The Cat gray must be dry.", sent[1][1])
        self.assertIn("step shade-cat.back", sent[3][1])
        rec = saved["st"]["words"]["c1"]["lean-paints"]["p"]
        self.assertEqual(rec["final"]["shade-cat"], [{"kind": "first", "text": "The gray from step 1 must be dry."},
                                                     {"kind": "strokes", "text": "Glaze Cat shadow on."}])
        self.assertEqual(rec["final"]["block-cat"], [{"kind": "strokes", "text": "Fill the cat with Cat gray."}])
        c = rec["check"]
        self.assertEqual((c["paints_first"], c["paints_second"], c["arc_paints_first"], c["arc_paints_second"],
                          c["paints_left"]), (2, 1, 1, 1, 0))
        self.assertEqual([g["sentence"] for g in c["paints_taken_out"]], ["Blend it into the Cat gray."])


if __name__ == "__main__":
    unittest.main()
