"""Tests for the brush pictures."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import brushes  # noqa: E402


class BrushTests(unittest.TestCase):
    def test_names_from_real_lessons(self):
        cases = {"#8 round": "round", "1 inch flat": "flat", "old stiff flat": "stiff", "Liner (#1 or #0)": "liner",
                 "#10 filbert": "filbert", "fan brush": "fan", "1/2 inch angle": "angle", "palette knife": None}
        for name, want in cases.items():
            self.assertEqual(brushes.kind(name), want, name)

    def test_picture_is_inline_svg_with_a_label(self):
        svg = brushes.picture("#8 round")
        self.assertTrue(svg.startswith("<svg") and "aria-label" in svg and "<title>" in svg)
        self.assertIn('aria-hidden="true"', brushes.picture("#8 round", "small"))
        self.assertEqual(brushes.picture("palette knife"), "")


if __name__ == "__main__":
    unittest.main()
