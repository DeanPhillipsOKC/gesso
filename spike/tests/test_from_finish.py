"""Tests for step pictures cut from the finished painting (#8)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

import from_finish as ff  # noqa: E402

SKY, FIELD_DARK, FIELD_MID, FIELD_LIGHT, BALL = "#6f92dc", "#262a5a", "#7a50d2", "#c08ae0", "#d83030"


def scene() -> np.ndarray:
    """Sky on top, a field of dark, mid, and light dabs below, and a red ball in the sky."""
    img = np.zeros((120, 160, 3), np.uint8)
    img[:60] = (111, 146, 220)
    rng = np.random.default_rng(1)
    pick = np.kron(rng.integers(0, 3, (15, 40)), np.ones((4, 4), int))  # 4-pixel dabs
    img[60:] = np.array([(38, 42, 90), (122, 80, 210), (192, 138, 224)], np.uint8)[pick]
    yy, xx = np.mgrid[:120, :160]
    img[((yy - 25) ** 2 + (xx - 50) ** 2) < 12 ** 2] = (216, 48, 48)
    return img


STEPS = [
    {"regions": [[0, 0, 1, 0.5]], "colors": [SKY]},
    {"regions": [[0.2, 0.05, 0.45, 0.4]], "colors": [BALL]},
    {"regions": [[0, 0.5, 1, 1]], "colors": [FIELD_MID]},
    {"regions": [[0, 0.5, 1, 1]], "colors": [FIELD_DARK]},
    {"regions": [[0, 0.5, 1, 1]], "colors": [FIELD_MID]},
    {"regions": [[0, 0.5, 1, 1]], "colors": [FIELD_LIGHT]},
]


class FromFinishTests(unittest.TestCase):
    def setUp(self):
        self.finish = scene()
        self.pics, self.owner = ff.build(self.finish, STEPS)

    def test_last_step_is_the_finish_and_nothing_drifts(self):
        np.testing.assert_array_equal(self.pics[-1], self.finish)
        sky = self.owner[:60] == 0
        for p in self.pics:  # once the sky is painted it never changes where the sky owns it
            np.testing.assert_allclose(p[:60][sky], self.finish[:60][sky], atol=2)  # feathered edges

    def test_ball_is_not_in_the_sky_step_but_sky_paint_goes_behind_it(self):
        ball = (slice(20, 30), slice(45, 55))
        self.assertFalse(np.any(np.all(self.pics[0][ball] == (216, 48, 48), axis=-1)))
        self.assertLess(np.abs(self.pics[0][ball].astype(int) - (111, 146, 220)).mean(), 20)

    def test_field_starts_flat_then_passes_go_on_darkest_first(self):
        field = (slice(64, 116), slice(4, 156))
        coat = self.pics[2][field].reshape(-1, 3)
        self.assertLess(coat.std(axis=0).max(), 8)  # flat
        light = [self.pics[k][field].astype(float).mean() for k in (3, 4, 5)]
        self.assertEqual(sorted(set(self.owner[60:].ravel().tolist())), [3, 4, 5])
        dark = self.finish[60:].sum(2) < 200
        self.assertGreater((self.owner[60:][dark] == 3).mean(), 0.8)  # dab edges blur into their neighbors
        self.assertLess(light[0], light[2])


if __name__ == "__main__":
    unittest.main()
