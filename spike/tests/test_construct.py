import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from construct import strip  # noqa: E402

PAINTS = {"Pumpkin orange": "#e8862a", "Rib brown": "#9a4a1c"}
PUMPKIN = {
    "title": "Build each pumpkin from simple pieces", "paint": "Pumpkin orange",
    "stages": [
        {"caption": "A center oval", "add": [{"ellipse": [50, 55, 13, 20]}]},
        {"caption": "A ( ) on each side", "add": [{"ellipse": [38, 57, 12, 18], "behind": True},
                                                {"ellipse": [62, 57, 12, 18], "behind": True}],
         "arrows": ["M 30 42 Q 24 57 30 72"]},
        {"caption": "Rib lines", "add": [{"line": "M 44 38 Q 40 55 44 74", "paint": "Rib brown"}]},
    ]}


def panels(html: str) -> list[str]:
    return re.findall(r"<svg.*?</svg>", html)


class ConstructTests(unittest.TestCase):
    def test_one_panel_per_stage_and_shapes_carry_forward(self):
        out = panels(strip(PUMPKIN, PAINTS, "p"))
        self.assertEqual(len(out), 3)
        self.assertEqual([p.count("<ellipse") for p in out], [1, 3, 3])
        self.assertIn("#9a4a1c", out[2])

    def test_only_this_stages_pieces_are_outlined(self):
        out = panels(strip(PUMPKIN, PAINTS, "p"))
        self.assertEqual([p.count("stroke-dasharray") for p in out], [1, 2, 0])

    def test_behind_pieces_draw_under_the_center(self):
        second = panels(strip(PUMPKIN, PAINTS, "p"))[1]
        self.assertLess(second.index('cx="38.0"'), second.index('cx="50.0"'))

    def test_arrows_show_only_in_their_stage_with_unique_markers(self):
        html = strip(PUMPKIN, PAINTS, "p")
        out = panels(html)
        self.assertEqual([p.count("marker-end") for p in out], [0, 1, 0])
        ids = re.findall(r'<marker id="([^"]+)"', html)
        self.assertEqual(len(ids), len(set(ids)))

    def test_bad_specs_draw_nothing_instead_of_breaking_the_page(self):
        self.assertEqual(strip({}, PAINTS, "x"), "")
        self.assertEqual(strip(None, PAINTS, "x"), "")
        bad = {"stages": [{"add": [{"path": "M0 0 L10 10\"/><script>alert(1)</script>"}]}]}
        self.assertEqual(strip(bad, PAINTS, "x"), "")
        self.assertEqual(strip({"stages": [{"add": [{"blob": 1}]}]}, PAINTS, "x"), "")

    def test_done_pieces_are_never_outlined(self):
        html = strip({"stages": [{"add": [{"ellipse": [50, 50, 10, 12], "done": True},
                                          {"line": "M 50 40 L 50 60"}]}]}, PAINTS, "x")
        self.assertEqual(html.count("stroke-dasharray"), 0)
        self.assertIn('opacity=".35"', html)  # the new line is still highlighted

    def test_unknown_paint_falls_back_and_hex_is_allowed(self):
        html = strip({"stages": [{"add": [{"circle": [50, 50, 10], "paint": "Mystery"},
                                          {"circle": [20, 20, 5], "paint": "#123456"}]}]}, PAINTS, "x")
        self.assertIn("var(--muted)", html)
        self.assertIn("#123456", html)


if __name__ == "__main__":
    unittest.main()
