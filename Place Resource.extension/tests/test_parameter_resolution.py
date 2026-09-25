# -*- coding: utf-8 -*-
"""Parameter fallback order and compound-structure formatting."""

import os
import sys
import unittest

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
CONFIG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "legends.json"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from configuration import load_settings
from parameter_service import LookupReader, ParameterResolver, format_layers
from units import format_millimetres


class ParameterResolutionTests(unittest.TestCase):
    def setUp(self):
        self.aliases = load_settings(CONFIG)["aliases"]
        self.resolver = ParameterResolver(self.aliases, {"blank_label": "–", "unmapped_parameter": "warn_and_blank"})

    def test_builtin_wins_over_guid_and_name(self):
        reader = LookupReader(
            builtins={"ALL_MODEL_TYPE_MARK": "W1"},
            guids={"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee": "GUID"},
            names={"Type Mark": "NAME"},
        )
        resolved = self.resolver.resolve("Type Mark", reader, required=True)
        self.assertEqual(resolved.raw_value, "W1")
        self.assertEqual(resolved.source, "builtin:ALL_MODEL_TYPE_MARK")
        self.assertIsNone(resolved.warning)

    def test_guid_is_used_when_builtin_is_blank(self):
        reader = LookupReader(
            builtins={"FIRE_RATING": ""},
            guids={"11111111-2222-3333-4444-555555555555": "120/120/120"},
            names={"Fire Rating": "from-name"},
        )
        aliases = {
            "Fire Rating": {
                "builtin": "FIRE_RATING",
                "guid": "11111111-2222-3333-4444-555555555555",
                "names": ["Fire Rating"],
            }
        }
        resolved = ParameterResolver(aliases).resolve("Fire Rating", reader, required=True)
        self.assertEqual(resolved.raw_value, "120/120/120")
        self.assertTrue(resolved.source.startswith("guid:"))

    def test_exact_name_fallback(self):
        reader = LookupReader(names={"Acoustic Rating": "STC 45"})
        resolved = self.resolver.resolve("Acoustic Rating", reader, required=False)
        self.assertEqual(resolved.display_value, "STC 45")
        self.assertEqual(resolved.source, "name:Acoustic Rating")
        self.assertIn("exact name", resolved.notice)

    def test_required_missing_uses_default_and_warns(self):
        reader = LookupReader()
        resolved = self.resolver.resolve("Type Mark", reader, required=True, default="UNMARKED")
        self.assertEqual(resolved.raw_value, "UNMARKED")
        self.assertEqual(resolved.source, "default")
        self.assertIn("Required parameter", resolved.warning)

    def test_optional_missing_is_blank_without_warning(self):
        reader = LookupReader()
        resolved = self.resolver.resolve("Fire Rating", reader, required=False)
        self.assertTrue(resolved.missing)
        self.assertIsNone(resolved.warning)
        self.assertEqual(resolved.display_value, "–")

    def test_unmapped_parameter_warns(self):
        reader = LookupReader()
        resolved = self.resolver.resolve("Custom Office Field", reader, required=False)
        self.assertIsNotNone(resolved.warning)
        self.assertIn("not mapped", resolved.warning)

    def test_width_formats_as_millimetres(self):
        reader = LookupReader(builtins={"WALL_ATTR_WIDTH_PARAM": 100.0 / 304.8})
        resolved = self.resolver.resolve("Width", reader, required=False, value_format="millimetres", decimals=0)
        self.assertEqual(resolved.display_value, "100")
        self.assertEqual(format_millimetres(1.0, 0), "305")

    def test_layer_formatter(self):
        text = format_layers(
            [
                {"material": "Plasterboard", "width_feet": 12.5 / 304.8},
                {"material": "Stud", "width_feet": 90.0 / 304.8},
            ],
            decimals=1,
        )
        self.assertEqual(text, "Plasterboard 12.5 mm / Stud 90.0 mm")


if __name__ == "__main__":
    unittest.main()
