# -*- coding: utf-8 -*-
"""Configuration loading and wall-inclusion rules."""

import os
import sys
import unittest

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
CONFIG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "legends.json"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from category_adapter import generic_is_included, wall_is_included
from configuration import (
    apply_name_pattern,
    load_settings,
    migrate_settings,
    sanitize_view_name,
)
from errors import ConfigurationError
from identity import content_hash


class ConfigurationTests(unittest.TestCase):
    def test_sample_file_loads(self):
        settings = load_settings(CONFIG)
        ids = [item["id"] for item in settings["data"]["legend_definitions"]]
        self.assertEqual(
            ids,
            ["wall_type_legend", "fire_rated_wall_legend", "acoustic_wall_legend", "door_type_legend"],
        )
        self.assertIn("Type Mark", settings["aliases"])
        self.assertEqual(settings["aliases"]["Fire Rating"]["builtin"], "FIRE_RATING")
        wall = settings["data"]["legend_definitions"][0]
        self.assertFalse(wall["include"]["curtain_walls"])
        self.assertEqual(wall["template_legend_name"], "_TEMPLATE - WALL LEGEND")
        self.assertFalse(wall["representation"]["fallback_detail_lines"])

    def test_unknown_schema_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            migrate_settings({"schema_version": "9.0", "legend_definitions": []})

    def test_duplicate_definition_id_is_rejected(self):
        settings = load_settings(CONFIG)
        broken = settings["data"]
        broken["legend_definitions"].append(dict(broken["legend_definitions"][0]))
        with self.assertRaises(ConfigurationError):
            migrate_settings(broken)
            from configuration import _validate_settings
            _validate_settings(broken, CONFIG)

    def test_missing_spacing_is_rejected(self):
        settings = load_settings(CONFIG)
        broken = settings["data"]
        del broken["legend_definitions"][0]["layout"]["row_height_mm"]
        from configuration import _validate_settings
        with self.assertRaises(ConfigurationError):
            _validate_settings(broken, CONFIG)

    def test_door_definition_has_no_wall_flags(self):
        settings = load_settings(CONFIG)
        door = settings["data"]["legend_definitions"][3]
        self.assertEqual(door["category"], "OST_Doors")
        self.assertNotIn("basic_walls", door["include"])
        self.assertNotIn("stacked_wall_members", door["include"])
        self.assertFalse(door["include"]["in_place"])

    def test_wall_flag_on_generic_definition_is_rejected(self):
        settings = load_settings(CONFIG)
        broken = settings["data"]
        broken["legend_definitions"][3]["include"]["curtain_walls"] = False
        from configuration import _validate_settings
        with self.assertRaises(ConfigurationError):
            _validate_settings(broken, CONFIG)

    def test_wall_definition_still_requires_wall_flags(self):
        settings = load_settings(CONFIG)
        broken = settings["data"]
        del broken["legend_definitions"][0]["include"]["curtain_walls"]
        from configuration import _validate_settings
        with self.assertRaises(ConfigurationError):
            _validate_settings(broken, CONFIG)

    def test_generic_in_place_flag(self):
        self.assertEqual(generic_is_included(True, False, False, {})[1], "in_place")
        self.assertTrue(generic_is_included(True, False, False, {"in_place": True})[0])

    def test_name_pattern_and_sanitiser(self):
        name = apply_name_pattern(
            "WALL LEGEND - {source_view_name}",
            {"source_view_name": "Level 01 / Core"},
        )
        self.assertEqual(name, "WALL LEGEND - Level 01 - Core")
        self.assertEqual(sanitize_view_name("A:B"), "A-B")

    def test_content_hash_is_stable(self):
        records = [{"type_id": 2, "display": {"Type Mark": "W2"}}, {"type_id": 1, "display": {"Type Mark": "W1"}}]
        layout = {"row_height_mm": 18}
        first = content_hash("wall_type_legend", "1.0", records, layout)
        second = content_hash("wall_type_legend", "1.0", list(reversed(records)), layout)
        self.assertEqual(first, second)
        self.assertNotEqual(first, content_hash("wall_type_legend", "1.0", records, {"row_height_mm": 20}))

    def test_wall_inclusion_defaults(self):
        include = {
            "basic_walls": True,
            "curtain_walls": False,
            "stacked_walls": False,
            "in_place_walls": False,
            "linked_models": False,
        }
        self.assertTrue(wall_is_included("basic", False, False, False, False, False, include)[0])
        self.assertEqual(
            wall_is_included("curtain", False, False, False, False, False, include)[1],
            "curtain_wall",
        )
        self.assertEqual(
            wall_is_included("stacked", False, False, False, False, False, include)[1],
            "stacked_wall",
        )
        self.assertEqual(
            wall_is_included("basic", True, False, False, False, False, include)[1],
            "in_place",
        )
        self.assertEqual(
            wall_is_included("basic", False, True, False, False, False, include)[1],
            "linked_model",
        )
        self.assertEqual(
            wall_is_included("basic", False, False, True, False, False, include)[1],
            "demolished",
        )
        self.assertEqual(
            wall_is_included("basic", False, False, False, True, False, include)[1],
            "stacked_member",
        )


if __name__ == "__main__":
    unittest.main()
