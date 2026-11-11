"""Tests for the render tool (#9): refusals spend nothing, and repeat calls come from the cache.

    python -m unittest discover spike/tests
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

import tools  # noqa: E402


class FakeUsage:
    def model_dump(self):
        # Close to a real low-quality edit: about $0.025 at the spike's rates.
        return {"input_tokens_details": {"text_tokens": 200, "image_tokens": 1000}, "output_tokens": 500}


class FakeImages:
    def __init__(self):
        self.calls = 0

    def edit(self, **kwargs):
        self.calls += 1
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (self.calls * 20 % 255, 100, 150)).save(buf, format="PNG")
        data = type("D", (), {"b64_json": base64.b64encode(buf.getvalue()).decode()})()
        return type("R", (), {"data": [data], "usage": FakeUsage()})()


class FakeClient:
    def __init__(self):
        self.images = FakeImages()


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = tools.CACHE_DIR
        tools.CACHE_DIR = self.tmp / "cache"
        self.lesson = self.tmp / "lesson"
        self.photo = self.tmp / "photo.png"
        Image.new("RGB", (30, 20), (10, 20, 30)).save(self.photo)
        self.client = FakeClient()

    def tearDown(self):
        tools.CACHE_DIR = self.cache

    def run_tool(self, *extra, step="sky", prompt="Paint the sky", reason="needs a soft gradient"):
        argv = ["render", "--lesson", str(self.lesson), "--step", step, "--inputs", str(self.photo), "--prompt", prompt]
        if reason is not None:
            argv += ["--why-not-filter", reason]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = tools.main(argv + list(extra), client=self.client)
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_missing_reason_refuses_without_calling(self):
        code, result = self.run_tool(reason=None)
        self.assertEqual(code, 2)
        self.assertIn("why-not-filter", result["refused"])
        self.assertEqual(self.client.images.calls, 0)

    def test_blank_reason_refuses(self):
        code, _ = self.run_tool(reason="   ")
        self.assertEqual(code, 2)
        self.assertEqual(self.client.images.calls, 0)

    def test_render_records_reason_and_cost(self):
        code, result = self.run_tool()
        self.assertEqual(code, 0)
        self.assertFalse(result["cached"])
        self.assertGreater(result["cost_usd"], 0)
        self.assertTrue(Path(result["out"]).exists())
        ledger = json.loads((self.lesson / "ledger.json").read_text())
        self.assertEqual(ledger["calls"][0]["reason"], "needs a soft gradient")

    def test_repeat_call_is_cached_and_free(self):
        self.run_tool()
        code, result = self.run_tool()
        self.assertEqual(code, 0)
        self.assertTrue(result["cached"])
        self.assertEqual(result["cost_usd"], 0)
        self.assertEqual(self.client.images.calls, 1)
        ledger = json.loads((self.lesson / "ledger.json").read_text())
        self.assertEqual(ledger["calls"][1]["cost_usd"], 0)

    def test_fresh_skips_cache(self):
        self.run_tool()
        _, result = self.run_tool("--fresh")
        self.assertFalse(result["cached"])
        self.assertEqual(self.client.images.calls, 2)

    def test_redo_cap_refuses(self):
        for i in range(3):  # first render plus 2 redos, each with a different prompt so none is cached
            code, _ = self.run_tool(prompt=f"try {i}")
            self.assertEqual(code, 0)
        code, result = self.run_tool(prompt="try 3")
        self.assertEqual(code, 2)
        self.assertIn("redos", result["refused"])
        self.assertEqual(self.client.images.calls, 3)

    def test_cached_hits_dont_count_as_redos(self):
        for _ in range(5):
            code, _ = self.run_tool()
            self.assertEqual(code, 0)
        self.assertEqual(self.client.images.calls, 1)

    def test_dollar_cap_refuses(self):
        code, result = self.run_tool("--max-cost", "0.05")  # a low render is estimated at up to $0.07
        self.assertEqual(code, 2)
        self.assertIn("cap", result["refused"])
        self.assertEqual(self.client.images.calls, 0)

    def test_dollar_cap_counts_earlier_steps(self):
        self.run_tool("--max-cost", "0.08", step="sky")
        code, result = self.run_tool("--max-cost", "0.08", step="trees", prompt="Paint the trees")
        self.assertEqual(code, 2)
        self.assertEqual(self.client.images.calls, 1)

    def test_separate_processes_keep_every_entry(self):
        # Two Budgets on one lesson stand in for two tools.py processes; each used to save only its own view.
        from concurrent.futures import ThreadPoolExecutor

        a = tools.Budget(self.lesson, 5.0, 2)
        b = tools.Budget(self.lesson, 5.0, 2)

        def go(i):
            budget = a if i % 2 else b
            return tools.render_one(budget, f"s{i}", [self.photo], f"prompt {i}", self.lesson / f"s{i}.png", "low",
                                    "test", client=self.client)

        with contextlib.redirect_stderr(io.StringIO()), ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(go, range(8)))
        ledger = json.loads((self.lesson / "ledger.json").read_text())
        self.assertEqual(len(ledger["calls"]), 8)


if __name__ == "__main__":
    unittest.main()
