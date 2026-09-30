# -*- coding: utf-8 -*-
"""The crash step log writes each step and never raises."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import trail


class TrailTests(unittest.TestCase):
    def test_steps_are_written_in_order(self):
        folder = tempfile.mkdtemp()
        try:
            path = os.path.join(folder, "logs", "last_run.txt")
            with mock.patch.object(trail, "PATH", path):
                trail.start("Legend Setup")
                trail.step("placing symbol IWS-105")
                trail.start("Legend Setup")
                trail.step("arranging rows")
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].endswith("Legend Setup"))
            self.assertTrue(lines[1].endswith("arranging rows"))
        finally:
            shutil.rmtree(folder)

    def test_bad_path_is_ignored(self):
        with mock.patch.object(trail, "PATH", os.path.join(os.devnull, "x", "last_run.txt")):
            trail.start("x")
            trail.step("y")


if __name__ == "__main__":
    unittest.main()
