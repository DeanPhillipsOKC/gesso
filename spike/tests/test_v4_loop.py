"""The v4 loop's bill priced as the API would charge it (#253). The plan's writer's changes and the library's picks
moved into the tools with #278 (test_plan_writer.py). No network, no Claude."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "experiments"))

import v4_loop as vl  # noqa: E402


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
