# -*- coding: utf-8 -*-
"""Long dashes stay out of the plugin, its settings and the README."""

import io
import os
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FOLDERS = ("Legends.panel", os.path.join("PlaceResource", "lib"), os.path.join("PlaceResource", "config"))
DASHES = (u"—", u"–")


def _files():
    readme = os.path.join(ROOT, "README.md")
    if os.path.isfile(readme):
        yield readme
    for folder in FOLDERS:
        for base, _dirs, names in os.walk(os.path.join(ROOT, folder)):
            for name in names:
                if name.endswith((".py", ".json", ".yaml", ".md")):
                    yield os.path.join(base, name)


class PlainTextTests(unittest.TestCase):
    def test_no_long_dashes(self):
        found = []
        for path in _files():
            with io.open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    if any(dash in line for dash in DASHES):
                        found.append("{0}:{1}".format(os.path.relpath(path, ROOT), number))
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
