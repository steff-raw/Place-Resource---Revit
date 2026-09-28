# -*- coding: utf-8 -*-
"""Sheets as a legend source: view selection, naming, and one count per wall."""

import os
import sys
import unittest
from unittest import mock

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import collectors
import version_adapter


class _Id(object):
    def __init__(self, value):
        self.Value = value


class _ViewType(object):
    def __init__(self, name):
        self._name = name

    def ToString(self):
        return self._name


class _View(object):
    def __init__(self, value, name, view_type, is_template=False, number=""):
        self.Id = _Id(value)
        self.Name = name
        self.ViewType = _ViewType(view_type)
        self.IsTemplate = is_template
        self.SheetNumber = number
        self.placed = []

    def GetAllPlacedViews(self):
        return [view.Id for view in self.placed]


class _Doc(object):
    def __init__(self, views):
        self._views = {view.Id.Value: view for view in views}

    def GetElement(self, element_id):
        return self._views.get(element_id.Value)


class _Element(object):
    def __init__(self, value, type_value):
        self.Id = _Id(value)
        self._type = _Id(type_value)

    def GetTypeId(self):
        return self._type


class _Adapter(object):
    def describe_instance(self, doc, view, element):
        return {"type_id": element.GetTypeId().Value, "kind": "basic", "type_element": object()}

    def include_instance(self, facts, include):
        return True, None


def _sheet_with_views():
    plan = _View(10, "Level 01", "FloorPlan")
    section = _View(11, "Section A", "Section")
    legend = _View(12, "Key", "Legend")
    schedule = _View(13, "Doors", "Schedule")
    sheet = _View(1, "Plans", "DrawingSheet", number="A101")
    sheet.placed = [section, plan, legend, schedule, plan]
    return sheet, _Doc([sheet, plan, section, legend, schedule])


class SheetSourceTests(unittest.TestCase):
    def test_only_supported_view_types_are_used(self):
        sheet, doc = _sheet_with_views()
        with mock.patch.object(version_adapter, "get_db", return_value=object()):
            views = collectors.sheet_source_views(doc, sheet, ["FloorPlan", "Section", "Elevation"])
        self.assertEqual([view.Name for view in views], ["Level 01", "Section A"])

    def test_sheet_without_matching_views(self):
        sheet, doc = _sheet_with_views()
        with mock.patch.object(version_adapter, "get_db", return_value=object()):
            self.assertEqual(collectors.sheet_source_views(doc, sheet, ["CeilingPlan"]), [])

    def test_names(self):
        sheet, _doc = _sheet_with_views()
        self.assertTrue(collectors.is_sheet(sheet))
        self.assertEqual(collectors.source_display_name(sheet), "A101 - Plans")
        plan = _View(10, "Level 01", "FloorPlan")
        self.assertFalse(collectors.is_sheet(plan))
        self.assertEqual(collectors.source_display_name(plan), "Level 01")

    def test_wall_seen_in_two_views_counts_once(self):
        result = collectors.CollectionResult()
        grouped = {}
        wall = _Element(100, 7)
        other = _Element(101, 7)
        with mock.patch.object(collectors, "_hidden_in_view", return_value=(False, None)):
            for view in (_View(10, "Level 01", "FloorPlan"), _View(11, "Section A", "Section")):
                collectors._consume_instance(None, view, _Adapter(), wall, {}, grouped, result, False, None)
            collectors._consume_instance(None, None, _Adapter(), other, {}, grouped, result, False, None)
        self.assertEqual(result.instance_count, 2)
        self.assertEqual(grouped[7]["instance_ids"], [100, 101])


if __name__ == "__main__":
    unittest.main()
