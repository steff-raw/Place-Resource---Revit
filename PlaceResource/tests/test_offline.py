# -*- coding: utf-8 -*-
"""The deployed tool must not reach the internet or start processes."""

import importlib.util
import os
import shutil
import tempfile
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CHECKER = os.path.join(REPO, ".claude", "skills", "offline-security", "scripts", "check_offline.py")


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_offline", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checker = _load_checker()

    def test_repository_is_offline(self):
        self.assertEqual(self.checker.scan(REPO), [])

    def test_violations_are_caught(self):
        root = tempfile.mkdtemp()
        try:
            lib = os.path.join(root, "PlaceResource", "lib")
            os.makedirs(lib)
            samples = {
                "a.py": "import urllib.request\n",
                "b.py": "from subprocess import run\n",
                "c.py": "import clr\nclr.AddReference('System.Net.Http')\n",
                "d.py": "import os\nos.startfile('x')\n",
                "e.py": "URL = 'https://example.com'\n",
                "f.py": "from System.Net import WebClient\n",
                "g.py": "eval('1+1')\n",
                "ok.py": "# see https://example.com in a comment only\nimport json\n",
            }
            for name, text in samples.items():
                with open(os.path.join(lib, name), "w", encoding="utf-8") as handle:
                    handle.write(text)
            findings = self.checker.scan(root)
            flagged = {item.split(":")[0].split(os.sep)[-1] for item in findings}
            self.assertEqual(flagged, {"a.py", "b.py", "c.py", "d.py", "e.py", "f.py", "g.py"})
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
