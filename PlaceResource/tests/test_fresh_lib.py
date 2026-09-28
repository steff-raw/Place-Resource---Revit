# -*- coding: utf-8 -*-
"""Each click loads the current lib code, so edits need no pyRevit Reload."""

import glob
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.abspath(os.path.join(HERE, "..", "..", "Legends.panel"))


def _finder_source(script_path):
    source = open(script_path, encoding="utf-8").read()
    start = source.index("def _find_lib")
    end = source.index("_find_lib()\n", start + 20)
    return source[start:end]


class FreshLibTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.lib = os.path.join(self.root, "PlaceResource", "lib")
        os.makedirs(self.lib)
        with open(os.path.join(self.lib, "legend_service.py"), "w") as handle:
            handle.write("")
        self.module_path = os.path.join(self.lib, "fresh_probe_module.py")
        self._saved_path = list(sys.path)

    def tearDown(self):
        sys.modules.pop("fresh_probe_module", None)
        sys.path[:] = self._saved_path
        shutil.rmtree(self.root)

    def _write_probe(self, value):
        with open(self.module_path, "w") as handle:
            handle.write("VALUE = {0!r}\n".format(value))

    def _run_finder(self, script_path):
        namespace = {"os": os, "sys": sys, "__file__": os.path.join(self.root, "Legends.panel", "X.pushbutton", "script.py")}
        exec(_finder_source(script_path), namespace)
        old = os.environ.get("PLACE_RESOURCE_HOME")
        os.environ["PLACE_RESOURCE_HOME"] = os.path.join(self.root, "PlaceResource")
        try:
            return namespace["_find_lib"]()
        finally:
            if old is None:
                os.environ.pop("PLACE_RESOURCE_HOME", None)
            else:
                os.environ["PLACE_RESOURCE_HOME"] = old

    def test_every_button_reloads_edited_lib_code(self):
        scripts = glob.glob(os.path.join(PANEL, "*", "script.py")) + glob.glob(os.path.join(PANEL, "*", "config.py"))
        self.assertEqual(len(scripts), 7)
        for script in scripts:
            self._write_probe("first")
            self._run_finder(script)
            import fresh_probe_module
            self.assertEqual(fresh_probe_module.VALUE, "first", script)
            self._write_probe("second")
            self._run_finder(script)
            import fresh_probe_module as reloaded
            self.assertEqual(reloaded.VALUE, "second", script)

    def test_modules_outside_lib_are_kept(self):
        script = glob.glob(os.path.join(PANEL, "*", "script.py"))[0]
        self._run_finder(script)
        self.assertIn("unittest", sys.modules)
        self.assertIn("os", sys.modules)


if __name__ == "__main__":
    unittest.main()
