import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from construct import lookup, problems, strip  # noqa: E402

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

    def test_a_paint_id_draws_in_that_paint(self):  # #91
        paints = lookup([{"id": "c1", "name": "Pumpkin orange", "hex": "#e8862a"}])
        html = strip({"paint": "c1", "stages": [{"add": [{"circle": [50, 50, 10]},
                                                         {"line": "M 0 0 L 9 9", "paint": "c1"}]}]}, paints, "x")
        self.assertEqual(html.count("#e8862a"), 2)
        self.assertNotIn("var(--muted)", html)
        self.assertEqual(problems({"paint": "c1", "stages": [{"add": [{"circle": [50, 50, 10]}]}]}, paints, "s1"), [])

    def test_an_unknown_paint_is_listed_in_problems(self):  # #91
        spec = {"title": "Build the balloon", "stages": [
            {"add": [{"circle": [50, 50, 10], "paint": "Pumpkin orange"}]},
            {"add": [{"ellipse": [50, 50, 10, 12], "paint": "Mystery"}, {"line": "M 0 0 L 9 9"},
                     {"rect": [0, 0, 5, 5], "paint": "#123456"}]}]}
        out = problems(spec, PAINTS, "s3")
        self.assertEqual(len(out), 2)
        self.assertIn("s3", out[0])
        self.assertIn("Build the balloon", out[0])
        self.assertIn("panel 2, shape 1 (ellipse)", out[0])
        self.assertIn("'Mystery'", out[0])
        self.assertIn("panel 2, shape 2 (line) has no paint", out[1])
        self.assertEqual(problems(None, PAINTS, "s3"), [])

    def test_a_broken_spec_draws_nothing_and_problems_never_crashes(self):  # review of #127
        for bad in ({"stages": [{"add": 5}]}, {"stages": [{"add": True}]}, {"stages": ["A center oval"]},
                    {"stages": [None, {"add": [7, "x"]}]}, {"stages": 3}, "a string", ["a list"]):
            self.assertEqual(strip(bad, PAINTS, "x"), "", bad)
            self.assertEqual(problems(bad, PAINTS, "s1"), [], bad)


if __name__ == "__main__":
    unittest.main()
