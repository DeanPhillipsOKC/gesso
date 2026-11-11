"""Tests for the step review packets (#24)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import step_review  # noqa: E402


class StepReviewTests(unittest.TestCase):
    def test_no_change_means_empty_mask(self):
        rng = np.random.default_rng(1)
        img = (rng.random((120, 160, 3)) * 30 + 100).astype(np.uint8)  # grainy, like canvas
        self.assertEqual(step_review.changed_mask(img, img).sum(), 0)

    def test_painted_block_is_found_where_it_is(self):
        before = np.full((120, 160, 3), 240, np.uint8)
        after = before.copy()
        after[60:120, 80:160] = (200, 120, 30)  # paint the lower right quarter
        mask = step_review.changed_mask(before, after)
        self.assertGreater(mask[90, 120], 0)
        self.assertEqual(mask[20, 20], 0)
        self.assertAlmostEqual(float(mask.mean()), 0.25, delta=0.05)

    def test_sheet_has_three_panels(self):
        a = np.full((80, 120, 3), 240, np.uint8)
        img = step_review.sheet(a, a, step_review.changed_mask(a, a), "Step 1")
        self.assertGreater(img.width, 3 * 120)


if __name__ == "__main__":
    unittest.main()
