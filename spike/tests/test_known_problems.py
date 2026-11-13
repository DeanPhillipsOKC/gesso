"""Tests for the Known problems section on lesson pages."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import known_problems as kp  # noqa: E402

DATA = {"stages": [{"id": "sky", "name": "Paint the sky"}, {"id": "water", "name": "Paint the water"}],
        "review_issues": [{"step_id": "water", "problem": "Patches in the water.", "action": "left"},
                          {"step_id": "sky", "problem": "Fixed thing.", "action": "redone"}],
        "text_issues": [{"step_id": "sky", "problem": "Sky stops short.", "action": "left: cap used up"},
                        {"step_id": "sky", "problem": "A diagram idea.", "action": "skipped: not needed"}]}
ISSUES = [{"number": 56, "title": "Lock leaves patches", "state": "OPEN", "url": "https://example.test/56"},
          {"number": 40, "title": "Old bug", "state": "CLOSED", "url": "https://example.test/40"}]


class KnownProblemsTests(unittest.TestCase):
    def test_only_problems_left_as_they_are_in_step_order(self):
        self.assertEqual([(p["step"], p["problem"]) for p in kp.left(DATA)],
                         [(1, "Sky stops short."), (2, "Patches in the water.")])

    def test_section_links_issues_and_marks_fixed_ones(self):
        html = kp.section(kp.left(DATA), ISSUES)
        self.assertIn('id="known-problems"', html)
        self.assertIn("<b>Step 2, Paint the water:</b>", html)
        self.assertIn('href="https://example.test/56">#56 Lock leaves patches', html)
        self.assertIn('class="state closed">fixed', html)

    def test_inject_puts_it_before_the_footer_then_replaces_it(self):
        page = '<main>steps</main><footer class="made">Made with Gesso</footer></body>'
        once = kp.inject(page, kp.section(kp.left(DATA), []))
        self.assertLess(once.index("Known problems"), once.index('<footer class="made">'))
        twice = kp.inject(once, kp.section([], []))
        self.assertNotIn("Known problems", twice)
        self.assertEqual(twice.count(kp.START), 1)

    def test_filed_uses_the_rest_search(self):  # `gh issue list` needs GraphQL, which cloud sessions can't reach
        import json
        import subprocess
        from unittest import mock
        reply = {"items": [{"number": 40, "title": "Old bug", "state": "closed", "html_url": "https://example.test/40"},
                           {"number": 56, "title": "Lock leaves patches", "state": "open",
                            "html_url": "https://example.test/56"}]}
        done = subprocess.CompletedProcess([], 0, json.dumps(reply), "")
        with mock.patch.object(kp, "gh", return_value="gh"), \
                mock.patch.object(kp.subprocess, "run", return_value=done) as run:
            self.assertEqual(kp.filed("sky_skill_1"), ISSUES)
        self.assertEqual(run.call_args[0][0][:4], ["gh", "api", "-X", "GET"])
        self.assertIn('"sky_skill_1" in:body', " ".join(run.call_args[0][0]))

    def test_page_keeps_its_count_when_github_cant_be_asked(self):
        import json
        import tempfile
        from unittest import mock
        d = Path(tempfile.mkdtemp())
        (d / "lesson.json").write_text(json.dumps(DATA), encoding="utf-8")
        page = d / "index.html"
        page.write_text(kp.inject("<body></body>", kp.section(kp.left(DATA), ISSUES)), encoding="utf-8")
        before = page.read_text(encoding="utf-8")
        with mock.patch.object(kp, "filed", return_value=None):
            r = kp.refresh_page(page, d)
        self.assertEqual((r["left"], r["issues_open"]), (2, ["56"]))
        self.assertEqual(page.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
