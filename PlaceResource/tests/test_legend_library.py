# -*- coding: utf-8 -*-
"""Library settings, row parsing, Type Mark matching and layout."""

import copy
import json
import os
import sys
import unittest
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
CONFIG = os.path.abspath(os.path.join(HERE, "..", "config", "library_legends.json"))
for path in (LIB, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

import legend_library as L
from errors import ConfigurationError
from units import mm_to_internal
from xlsx_fixture import SAMPLE_LIBRARY


def _settings():
    with open(CONFIG, encoding="utf-8") as handle:
        return json.load(handle)


def _records(rows):
    header = [cell.lower() for cell in rows[0]]
    records = []
    for number, row in enumerate(rows[1:], 2):
        record = {"__row__": number}
        record.update({key: value for key, value in zip(header, row)})
        records.append(record)
    return records


class SettingsTests(unittest.TestCase):
    def test_shipped_files_load(self):
        loaded = L.load_library_settings(CONFIG)
        self.assertEqual(list(loaded["categories"].keys()), list(SAMPLE_LIBRARY.keys()))
        self.assertEqual(loaded["warnings"], [])
        walls = loaded["categories"]["Walls"]
        self.assertEqual(walls["revit_category"], "OST_Walls")
        self.assertEqual(walls["template_legend_name"], "_TEMPLATE - WALL LEGEND")
        self.assertEqual(walls["layout"]["swatch_width_mm"], 15)
        fire = loaded["categories"]["Fire Strategy"]
        self.assertIsNone(fire["revit_category"])
        self.assertEqual(fire["template_legend_name"], "_TEMPLATE - LIBRARY LEGEND")
        codes = [entry.code for entry in loaded["library"]["Walls"]]
        self.assertEqual(codes, ["IWS-105", "IWS-110"])

    def test_category_override_merges_nested_blocks(self):
        data = _settings()
        data["categories"][0]["layout"] = {"swatch_width_mm": 30}
        merged = L.validate_settings(data)
        first = merged[data["categories"][0]["name"]]
        self.assertEqual(first["layout"]["swatch_width_mm"], 30)
        self.assertEqual(first["layout"]["swatch_height_mm"], 8)

    def test_invalid_settings_are_rejected(self):
        cases = []
        bad = _settings(); bad["schema_version"] = "2.0"; cases.append(bad)
        bad = _settings(); bad["library_file"] = "library.csv"; cases.append(bad)
        bad = _settings(); bad["categories"].append(copy.deepcopy(bad["categories"][0])); cases.append(bad)
        bad = _settings(); bad["categories"][0]["revit_category"] = "Walls"; cases.append(bad)
        bad = _settings(); bad["categories"][0]["scale"] = 0; cases.append(bad)
        bad = _settings(); bad["defaults"]["styles"]["title_text_type"] = ""; cases.append(bad)
        bad = _settings(); bad["defaults"]["layout"]["swatch_height_mm"] = 0; cases.append(bad)
        bad = _settings(); bad["defaults"]["sheet_placement"]["mode"] = "anywhere"; cases.append(bad)
        for data in cases:
            with self.assertRaises(ConfigurationError):
                L.validate_settings(data)


class LibraryRowTests(unittest.TestCase):
    def test_defaults_and_aliases(self):
        rows = [
            ["Type Mark", "Name", "Desc", "Graphic", "Hatch"],
            ["IWS-105", "", "Stud wall", "", "Wall - IWS-105"],
            ["IWS-110", "Wall 110", "", "COMPONENT", ""],
        ]
        entries, problems = L.parse_sheet("Walls", _records(rows))
        self.assertEqual(problems, [])
        first, second = entries
        self.assertEqual((first.code, first.title, first.graphic, first.region_type),
                         ("IWS-105", "IWS-105", "region", "Wall - IWS-105"))
        self.assertEqual((second.title, second.graphic), ("Wall 110", "component"))
        self.assertIn("Stud wall", first.label())

    def test_problems_are_listed_with_rows(self):
        rows = [
            ["Code", "Description", "Graphic", "Filled Region Type"],
            ["", "orphan description", "", ""],
            ["A", "", "Hatch", "X"],
            ["B", "", "Region", ""],
            ["C", "", "", "Y"],
            ["c", "", "", "Y"],
        ]
        entries, problems = L.parse_sheet("Walls", _records(rows))
        self.assertEqual([entry.code for entry in entries], ["C"])
        self.assertEqual(len(problems), 4)
        self.assertTrue(problems[0].startswith("Walls row 2"))
        self.assertIn("Region or Component", problems[1])
        self.assertIn("Filled Region Type is empty", problems[2])
        self.assertIn("Walls row 6: Code 'c' is already used on row 5", problems[3])

    def test_parse_library_raises_with_all_problems_and_warns_missing_sheet(self):
        workbook = OrderedDict([("walls", [["Code", "Graphic"], ["A", "bad"], ["B", "bad"]])])
        with self.assertRaises(ConfigurationError) as caught:
            L.parse_library(workbook, ["Walls"])
        self.assertIn("2 problem(s)", str(caught.exception))
        library, warnings = L.parse_library(OrderedDict(), ["Doors"])
        self.assertEqual(library["Doors"], [])
        self.assertIn("no sheet named 'Doors'", warnings[0])


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.entries = [
            L.LibraryEntry("IWS-105", "", "", "region", "R", 2),
            L.LibraryEntry("IWS-110", "", "", "component", "", 3),
            L.LibraryEntry("EWS-01", "", "", "region", "R", 4),
        ]

    def test_type_marks_match_ignoring_case_and_spaces(self):
        self.assertEqual(L.match_type_marks(self.entries, ["iws-110 ", "EWS-01", "X", None, ""]), ["IWS-110", "EWS-01"])

    def test_codes_keep_library_order(self):
        chosen = L.entries_for_codes(self.entries, ["EWS-01", "iws-105"])
        self.assertEqual([entry.code for entry in chosen], ["IWS-105", "EWS-01"])
        self.assertEqual(L.missing_codes(self.entries, ["IWS-105", "OLD-1"]), ["OLD-1"])


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.layout = {
            "swatch_width": 10.0, "swatch_height": 4.0, "title_width": 20.0, "description_width": 50.0,
            "column_gap": 2.0, "row_gap": 1.0, "heading_gap": 3.0,
        }

    def test_rows_stack_down_and_grow_with_content(self):
        sizes = [
            {"graphic": (10.0, 4.0), "title": (8.0, 2.0), "description": (40.0, 6.0)},
            {"graphic": (12.0, 5.0), "title": (25.0, 2.0), "description": (30.0, 2.0)},
        ]
        result = L.layout_rows(sizes, self.layout, heading_size=(30.0, 2.0))
        self.assertEqual(result["heading"], (0.0, 0.0))
        first, second = result["rows"]
        self.assertEqual(first["graphic"], (0.0, -5.0))
        self.assertEqual(first["height"], 6.0)
        self.assertEqual(second["graphic"][1], -5.0 - 6.0 - 1.0)
        self.assertEqual(first["title"][0], 12.0 + 2.0)
        self.assertEqual(first["description"][0], 14.0 + 25.0 + 2.0)
        self.assertEqual(result["block"]["bottom"], -12.0 - 5.0)
        self.assertEqual(result["block"]["right"], 41.0 + 50.0)

    def test_no_heading_starts_at_origin(self):
        result = L.layout_rows([{"graphic": (1.0, 1.0), "title": (1.0, 1.0), "description": (1.0, 1.0)}], self.layout)
        self.assertIsNone(result["heading"])
        self.assertEqual(result["rows"][0]["graphic"], (0.0, 0.0))
        self.assertEqual(result["rows"][0]["height"], 4.0)

    def test_paper_mm_scale_to_model(self):
        layout_mm = L.DEFAULTS["layout"]
        model = L.layout_to_model(layout_mm, 100, mm_to_internal)
        self.assertAlmostEqual(model["swatch_width"], mm_to_internal(15) * 100)
        self.assertAlmostEqual(model["row_gap"], mm_to_internal(3) * 100)


if __name__ == "__main__":
    unittest.main()
