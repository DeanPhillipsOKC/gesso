"""Tests for spike/yaml_files.py: a YAML file is parsed once, again when it changes, and each caller gets its own copy
(#87)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml_files  # noqa: E402


class YamlFilesTests(unittest.TestCase):
    def test_an_edited_file_is_read_again_and_a_changed_answer_stays_the_callers(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "card.yaml"
            path.write_text("id: dabbing\nsources: [a]\n", encoding="utf-8")
            first = yaml_files.read(path)
            self.assertEqual(first, {"id": "dabbing", "sources": ["a"]})
            first["sources"].append("b")  # a caller changing what it got back
            self.assertEqual(yaml_files.read(path)["sources"], ["a"])
            path.write_text("id: dabbing\nsources: [a, c]\n", encoding="utf-8")
            st = path.stat()
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))  # however fast the edit came
            self.assertEqual(yaml_files.read(path)["sources"], ["a", "c"])


if __name__ == "__main__":
    unittest.main()
