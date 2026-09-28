# -*- coding: utf-8 -*-
"""Family builder planning, paths and project settings. No Revit needed."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import family_builder as F
import legend_component_service
import legend_library as L
import project_settings
import ui_service
from errors import LegendOperationError


def _config(**builder):
    item = {"name": "Walls", "revit_category": "OST_Walls"}
    if builder:
        item["builder"] = builder
    return L.validate_settings({"schema_version": "2.0", "categories": [item]})["Walls"]


class PlanTests(unittest.TestCase):
    def test_one_type_per_code_and_one_swatch_per_hatch(self):
        rows = [
            {"code": "IWS-105", "description": "Metal stud"},
            {"code": "IWS-110", "description": "Blockwork"},
            {"code": "IWS-111", "description": "Blockwork 2", "hatch": "IWS-110"},
            {"code": "iws-105", "description": "duplicate"},
            {"code": "IWS-200"},
            {"code": ""},
        ]
        plan = F.plan_family(rows, ["IWS-105", "iws-110", "Other"], "{code}", "Walls")
        self.assertEqual([item["name"] for item in plan["types"]], ["IWS-105", "IWS-110", "IWS-111", "IWS-200"])
        self.assertEqual([item["name"] for item in plan["hatches"]], ["IWS-105", "iws-110"])
        self.assertEqual(plan["missing_hatch"], ["IWS-200"])
        self.assertEqual(plan["duplicates"], ["iws-105"])
        show = {item["name"]: item["show"] for item in plan["types"]}
        self.assertEqual(show["IWS-105"], {"Show IWS-105": 1, "Show iws-110": 0})
        self.assertEqual(show["IWS-110"], {"Show IWS-105": 0, "Show iws-110": 1})
        self.assertEqual(show["IWS-111"], {"Show IWS-105": 0, "Show iws-110": 1})
        self.assertEqual(show["IWS-200"], {"Show IWS-105": 0, "Show iws-110": 0})
        self.assertEqual(plan["types"][0]["description"], "Metal stud")

    def test_hatch_name_pattern(self):
        plan = F.plan_family([{"code": "FR-60"}], ["Hatch - FR-60"], "Hatch - {code}", "Fire Strategy")
        self.assertEqual(plan["types"][0]["hatch"], "Hatch - FR-60")
        self.assertEqual(plan["missing_hatch"], [])

    def test_parameter_names_are_cleaned(self):
        self.assertEqual(F.parameter_name("Show Fire: 60 [min]"), "Show Fire- 60 -min-")
        self.assertEqual(F.parameter_name(""), "Show")


class PathTests(unittest.TestCase):
    def test_family_folder_and_seed(self):
        config = _config()
        folder = F.family_folder(config)
        self.assertTrue(folder.endswith(os.path.join("config", "families")))
        with mock.patch.object(os.path, "isfile", return_value=True):
            self.assertEqual(F.seed_path(config), os.path.join(folder, "PR Legend Seed.rfa"))
        with mock.patch.object(os.path, "isfile", return_value=False):
            self.assertIsNone(F.seed_path(config))
        self.assertIsNone(F.seed_path(_config(seed_family_path="")))

    def test_template_search(self):
        app = mock.Mock()
        app.FamilyTemplatePath = "/templates"
        with mock.patch.object(os, "walk", return_value=[("/templates/Annotations", [], ["Metric Generic Annotation.rft"])]):
            self.assertEqual(F.find_template(app), os.path.join("/templates/Annotations", "Metric Generic Annotation.rft"))
        with mock.patch.object(os, "walk", return_value=[("/templates", [], ["Other.rft"])]):
            self.assertIsNone(F.find_template(app))


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
