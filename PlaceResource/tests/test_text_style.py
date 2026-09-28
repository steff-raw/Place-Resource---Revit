# -*- coding: utf-8 -*-
"""Project settings and the legend text style. No Revit needed."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import legend_component_service
import project_settings
import ui_service
from errors import LegendOperationError


class ProjectSettingsTests(unittest.TestCase):
    def test_normalize_keeps_only_text_type(self):
        data = project_settings.normalize({"text_type": "  2.5mm Arial ", "masters": {"Walls": "abc"}})
        self.assertEqual(data, {"text_type": "2.5mm Arial"})
        self.assertEqual(project_settings.normalize(None), {"text_type": None})
        self.assertIn("not set", project_settings.describe({}))


class TextStyleTests(unittest.TestCase):
    def test_saved_style_wins_then_settings_file(self):
        def _find(doc, name):
            if name == "Missing":
                raise LegendOperationError("missing")
            return name

        with mock.patch.object(legend_component_service, "find_text_type", side_effect=_find), \
                mock.patch.object(project_settings, "text_type_name", return_value="Office Text"):
            self.assertEqual(legend_component_service.resolve_text_type(None, "2.5mm Arial"), "Office Text")
        with mock.patch.object(legend_component_service, "find_text_type", side_effect=_find), \
                mock.patch.object(project_settings, "text_type_name", return_value="Missing"):
            self.assertEqual(legend_component_service.resolve_text_type(None, "2.5mm Arial"), "2.5mm Arial")

    def test_picker_only_when_needed(self):
        with mock.patch.object(legend_component_service, "text_types_resolve", return_value=True), \
                mock.patch.object(ui_service, "choose_text_type") as picker:
            self.assertTrue(ui_service.ensure_text_style(None, ["2.5mm Arial"]))
            picker.assert_not_called()
        with mock.patch.object(legend_component_service, "text_types_resolve", return_value=False), \
                mock.patch.object(ui_service, "choose_text_type", return_value=None):
            self.assertFalse(ui_service.ensure_text_style(None, ["2.5mm Arial"]))


if __name__ == "__main__":
    unittest.main()
