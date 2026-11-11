"""Tests for the paint mixer (#22).

    python -m unittest discover spike/tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import mixing  # noqa: E402

PALETTE = ["Titanium white", "Cadmium yellow medium (hue)", "Cadmium red medium (hue)", "Ultramarine blue", "Burnt sienna"]


class MixingTests(unittest.TestCase):
    def test_blue_and_yellow_make_green_like_paint(self):
        r, g, b = mixing.hex_rgb(mixing.mix({"Ultramarine blue": 1, "Cadmium yellow medium (hue)": 1}))
        self.assertGreater(g, r)
        self.assertGreater(g, b)

    def test_known_mix_solves_back_to_itself(self):
        target = mixing.mix({"Titanium white": 3, "Ultramarine blue": 1})
        r = mixing.solve(target, PALETTE)
        self.assertLess(r["delta_e"], 1.0)
        self.assertEqual(r["parts"], {"Titanium white": 3, "Ultramarine blue": 1})
        self.assertTrue(r["reachable"])

    def test_off_palette_color_is_flagged(self):
        r = mixing.solve("#00c8ff", PALETTE)  # a bright cyan: ultramarine can't get there
        self.assertFalse(r["reachable"])
        self.assertGreater(r["delta_e"], mixing.REACHABLE)

    def test_tube_names_match_pigments(self):
        self.assertEqual(mixing.tube_rgb("Cadmium yellow medium (hue)"), mixing.TUBES["cadmium yellow"])
        self.assertEqual(mixing.tube_rgb("Titanium white"), mixing.TUBES["white"])
        with self.assertRaises(mixing.UnknownTube):
            mixing.tube_rgb("Unicorn pink")

    def test_words_are_friendly(self):
        self.assertEqual(mixing.words({"Titanium white": 3, "Ultramarine blue": 1, "Burnt sienna": mixing.TOUCH}),
                         "3 parts white, 1 part ultramarine, a touch of burnt sienna")
        self.assertEqual(mixing.words({"Burnt sienna": 1}), "Burnt sienna, straight from the tube")

    def test_straight_from_the_tube_stays_one_tube(self):
        self.assertEqual(mixing.single_tube("Burnt sienna", "", PALETTE), "Burnt sienna")
        self.assertEqual(mixing.single_tube("Basket brown", "burnt sienna, straight from the tube", PALETTE), "Burnt sienna")
        self.assertIsNone(mixing.single_tube("Trunk brown", "2 parts burnt sienna, 1 part ultramarine", PALETTE))
        self.assertIsNone(mixing.single_tube("Warm sky", "white with a touch of yellow", PALETTE))
        self.assertIsNone(mixing.single_tube("Sky blue", "white and blue", PALETTE))
        r = mixing.straight("Burnt sienna", "#7b4a10")
        self.assertEqual(r["parts"], {"Burnt sienna": 1})
        self.assertEqual(r["text"], "Burnt sienna, straight from the tube")

    def test_no_scaled_duplicates(self):
        for parts in mixing._candidates(PALETTE):
            self.assertFalse(parts.get("Titanium white") == 2 and parts.get("Ultramarine blue") == 2 and len(parts) == 2)

    def test_delta_e_reference_pair(self):
        # Loose sanity checks: identical is 0, a tiny nudge is under 2, red against blue is huge
        self.assertEqual(mixing.delta_e("#808080", "#808080"), 0.0)
        self.assertLess(mixing.delta_e((128, 128, 128), (130, 128, 128)), 2.0)
        self.assertGreater(mixing.delta_e("#ff0000", "#0000ff"), 40)


if __name__ == "__main__":
    unittest.main()
