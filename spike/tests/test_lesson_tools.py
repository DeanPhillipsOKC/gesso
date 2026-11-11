"""Tests for render-step and publish (#10), with a fake image client.

    python -m unittest discover spike/tests
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PIL import Image  # noqa: E402

import tools  # noqa: E402
from test_render import FakeClient  # noqa: E402


def step(id_, covers=False):
    return {"id": id_, "name": f"Paint the {id_}", "paints": id_, "looks_like": f"{id_} painted", "covers_canvas": covers,
            "colors": ["Sky blue"], "brushes": "1 inch flat", "how": ["Paint it"], "watch_out": ["Don't rush"]}


class LessonToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cache = tools.CACHE_DIR
        tools.CACHE_DIR = self.tmp / "cache"
        self.lesson = self.tmp / "lesson"
        self.lesson.mkdir()
        Image.new("RGB", (40, 60), (90, 140, 220)).save(self.lesson / "99_finish.png")
        plan = {
            "photo": "photos/does-not-matter.jpg", "technique": "techniques/acrylic-paint-along-beginner.yaml",
            "quality": "low", "subject": "a sky", "focal_point": "the sun", "light": "from the left",
            "components": ["sky", "hill", "tree"],
            "paints": [{"name": "Sky blue", "recipe": "white and blue", "hex": "#5a8cdc", "used_for": "sky",
                        "sample_x": 0.5, "sample_y": 0.2}],
            "steps": [step("sky"), step("hill"), step("tree", True)],
        }
        (self.lesson / "plan.json").write_text(json.dumps(plan))
        self.client = FakeClient()

    def tearDown(self):
        tools.CACHE_DIR = self.cache

    def run_tool(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = tools.main(list(argv), client=self.client)
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_parallel_renders_each_step_and_makes_canvas(self):
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill",
                                "--why-not-filter", "no filter removes later parts yet")
        self.assertEqual(code, 0)
        self.assertEqual(self.client.images.calls, 2)
        self.assertTrue((self.lesson / "01_sky.png").exists())
        self.assertTrue((self.lesson / "02_hill.png").exists())
        self.assertTrue((self.lesson / "00_canvas.png").exists())

    def test_requires_reason(self):
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky")
        self.assertEqual(code, 2)
        self.assertEqual(self.client.images.calls, 0)

    def test_last_step_and_unknown_ids_refuse(self):
        for ids in (["tree"], ["nope"]):
            code, _ = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", *ids, "--why-not-filter", "x")
            self.assertEqual(code, 2)
        self.assertEqual(self.client.images.calls, 0)

    def test_parallel_cap_is_shared(self):
        # $0.10 fits one low render (estimated $0.07) but not two at once.
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill",
                                "--why-not-filter", "x", "--max-cost", "0.10")
        self.assertEqual(code, 0)
        self.assertEqual(self.client.images.calls, 1)
        self.assertEqual(sum(1 for s in r["steps"] if "refused" in s), 1)

    def test_anchored_needs_next_step(self):
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "--mode", "anchored",
                                "--why-not-filter", "x")
        self.assertIn("refused", r["steps"][0])
        code, r = self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--mode", "anchored",
                                "--why-not-filter", "x")
        self.assertTrue(all("refused" not in s for s in r["steps"]))  # hill first (from the finish), then sky from hill

    def test_publish_builds_html_with_sources(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        text = {"steps": [{"stage_id": "sky", "what_to_do": ["Blend the sky"], "mixes": [], "watch_out": [], "paint_notes": [],
                           "made_with": "render", "reason": "x"},
                          {"stage_id": "hill", "what_to_do": ["Block the hill"], "mixes": [], "watch_out": [], "paint_notes": [],
                           "made_with": "filter:simplify", "reason": "flat shape"}]}
        (self.lesson / "text.json").write_text(json.dumps(text))
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        html = (self.lesson / "lesson.html").read_text(encoding="utf-8")
        self.assertIn("Blend the sky", html)
        self.assertEqual(r["steps_by_source"], {"render": 2, "filter": 1})
        self.assertEqual(r["paid_renders"], 2)

    def test_publish_shows_the_reasoning_folded_away(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "no mask yet")
        notes = {"read": "Mostly sky.", "order": "Back to front.", "steps": {"sky": "The sky is behind everything."},
                 "technique": {"why": "Simple layers.", "considered": [{"name": "Block in", "why_not": "Too few values."}]},
                 "filters": [{"label": "Reference", "tool": "simplify", "image": "00_canvas.png", "why": "flatten it",
                              "verdict": "kept"}],
                 "learned": ["Composite the sky."]}
        (self.lesson / "notes.json").write_text(json.dumps(notes))
        (self.lesson / "review.json").write_text(json.dumps({"review_issues": [
            {"round": 1, "step_id": "sky", "problem": "A smudge.", "action": "left"}]}))
        code, _ = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        html = (self.lesson / "lesson-artifact.html").read_text(encoding="utf-8")
        self.assertIn('id="behind"', html)
        for text in ("The sky is behind everything.", "Too few values.", "no mask yet", "Composite the sky.", "A smudge."):
            self.assertIn(text, html)
        self.assertEqual(html.count('<details class="why">'), 2)  # sky and hill; the finish has nothing logged
        self.assertNotIn("<details open", html)  # nothing unfolds on its own

    def test_publish_explains_diagrams_and_flags_unexplained_ones(self):
        self.run_tool("render-step", "--lesson", str(self.lesson), "--steps", "sky", "hill", "--why-not-filter", "x")
        shape = {"stages": [{"caption": "An oval", "add": [{"ellipse": [50, 50, 20, 30]}]}]}
        text = {"steps": [{"stage_id": "sky", "what_to_do": ["Blend"], "construct": shape},
                          {"stage_id": "hill", "what_to_do": ["Block"], "construct": shape}]}
        (self.lesson / "text.json").write_text(json.dumps(text))
        notes = {"beginner_check": {"summary": "One shaped object.",
                                    "diagrams": {"sky": {"noticed": "The lumpy outline.", "pieces": "An oval first.",
                                                         "source": "beginner check"}},
                                    "no_diagram": {}}}
        (self.lesson / "notes.json").write_text(json.dumps(notes))
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 0)
        self.assertEqual(r["diagrams"], 2)
        self.assertEqual(r["undocumented_diagrams"], ["hill"])
        html = (self.lesson / "lesson-artifact.html").read_text(encoding="utf-8")
        for text in ("The lumpy outline.", "An oval first.", "Where Claude drew diagrams", "Diagrams (1)"):
            self.assertIn(text, html)

    def test_publish_refuses_missing_images(self):
        code, r = self.run_tool("publish", "--lesson", str(self.lesson))
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
