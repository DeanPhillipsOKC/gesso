"""The v4 writer's and finisher's cost cuts (#267): Sonnet's prices, the model and effort a helper is called with,
the lean fact sheet, and the arc asked as the writer's next message. No network, no Claude."""

from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
