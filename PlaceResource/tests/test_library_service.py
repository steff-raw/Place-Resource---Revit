# -*- coding: utf-8 -*-
"""Library legend checks that run before any transaction, with fake Revit objects."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import collectors
import dialogs
import legend_library as L
import library_legend_service as S
import library_ui
import version_adapter
from errors import LegendOperationError


class _Id(object):
    def __init__(self, value):
        self.Value = value


class _Param(object):
    def __init__(self, value):
        self._value = value

    def AsString(self):
        return self._value


class _Element(object):
    def __init__(self, value, kind, name="", category=None, mark=None, type_id=None, views=()):
        self.Id = _Id(value)
        self.kind = kind
        self.Name = name
        self.category = category
        self._mark = mark
        self._type_id = type_id
        self.views = set(views)

    def get_Parameter(self, parameter):
        return _Param(self._mark) if self._mark is not None else None

    def LookupParameter(self, name):
        return None

    def GetTypeId(self):
        return _Id(self._type_id if self._type_id is not None else -1)


class _Doc(object):
    def __init__(self, elements):
        self.elements = elements

    def GetElement(self, element_id):
        for element in self.elements:
            if element.Id.Value == element_id.Value:
                return element
        return None


class _FilledRegionType(object):
    pass


def _fake_db(doc):
    class _Collector(object):
        def __init__(self, document, view_id=None):
            self._items = list(document.elements)
            if view_id is not None:
                self._items = [item for item in self._items if view_id.Value in item.views]

        def OfClass(self, cls):
            if cls is _FilledRegionType:
                self._items = [item for item in self._items if item.kind == "region_type"]
            return self

        def OfCategory(self, category):
            self._items = [item for item in self._items if item.category == category]
            return self

        def WhereElementIsElementType(self):
            self._items = [item for item in self._items if item.kind == "type"]
            return self

        def WhereElementIsNotElementType(self):
            self._items = [item for item in self._items if item.kind == "instance"]
            return self

        def __iter__(self):
            return iter(self._items)

    return type("DB", (), {
        "FilteredElementCollector": _Collector,
        "FilledRegionType": _FilledRegionType,
        "BuiltInCategory": type("BIC", (), {"OST_Walls": "OST_Walls"}),
        "BuiltInParameter": type("BIP", (), {"ALL_MODEL_TYPE_MARK": "ALL_MODEL_TYPE_MARK"}),
    })


class _TextType(object):
    Id = _Id(900)


def _config(revit_category="OST_Walls", show_heading=True):
    data = L.validate_settings({
        "schema_version": "1.0",
        "library_file": "x.xlsx",
        "categories": [{"name": "Walls", "revit_category": revit_category}],
    })
    config = data["Walls"]
    config["styles"]["show_heading"] = show_heading
    return config


def _model():
    return _Doc([
        _Element(1, "region_type", name="Wall - IWS-105"),
        _Element(10, "type", name="Stud 105", category="OST_Walls", mark="IWS-105"),
        _Element(11, "type", name="Stud 110", category="OST_Walls", mark="IWS-110"),
        _Element(12, "type", name="Stud 110 copy", category="OST_Walls", mark="iws-110"),
        _Element(20, "instance", category="OST_Walls", type_id=10, views=(100,)),
        _Element(21, "instance", category="OST_Walls", type_id=11, views=(101,)),
        _Element(22, "instance", category="OST_Walls", type_id=11, views=(100, 101)),
    ])


class PrepareTests(unittest.TestCase):
    def _prepare(self, doc, config, entries, need_template=True, text_error=None, template_error=None):
        def _text(_doc, name):
            if text_error and name == text_error:
                raise LegendOperationError("Text note type '{0}' was not found.".format(name))
            return _TextType()

        def _template(_doc, name):
            if template_error:
                raise LegendOperationError("Template legend '{0}' was not found.".format(name))
            return "template"

        db = _fake_db(doc)
        with mock.patch.object(S, "get_db", return_value=db), \
                mock.patch.object(version_adapter, "get_db", return_value=db), \
                mock.patch.object(S, "find_text_type", side_effect=_text), \
                mock.patch.object(S, "find_template_legend", side_effect=_template):
            return S.prepare(doc, config, entries, need_template)

    def test_everything_resolves(self):
        entries = [
            L.LibraryEntry("IWS-105", "", "", "region", "Wall - IWS-105", 2),
            L.LibraryEntry("IWS-110", "", "", "component", "", 3),
        ]
        resolved = self._prepare(_model(), _config(), entries)
        self.assertEqual(resolved["problems"], [])
        self.assertEqual(resolved["region_types"]["Wall - IWS-105"].Name, "Wall - IWS-105")
        self.assertEqual(resolved["component_types"]["IWS-110"].Name, "Stud 110")
        self.assertIn("2 types have Type Mark 'IWS-110'", resolved["warnings"][0])
        self.assertEqual(resolved["template"], "template")

    def test_all_problems_are_reported_together(self):
        entries = [
            L.LibraryEntry("FR-60", "", "", "region", "Fire - 60 min", 2),
            L.LibraryEntry("IWS-999", "", "", "component", "", 3),
        ]
        resolved = self._prepare(_model(), _config(), entries, text_error="2.5mm Arial", template_error=True)
        problems = "\n".join(resolved["problems"])
        self.assertIn("Text note type '2.5mm Arial'", problems)
        self.assertIn("Fire - 60 min", problems)
        self.assertIn("Available: Wall - IWS-105", problems)
        self.assertIn("no Walls type in this model has Type Mark 'IWS-999'", problems)
        self.assertIn("Template legend", problems)

    def test_component_rows_need_a_revit_category(self):
        entries = [L.LibraryEntry("X", "", "", "component", "", 2)]
        resolved = self._prepare(_model(), _config(revit_category=None), entries, need_template=False)
        self.assertIn("no revit_category", resolved["problems"][0])

    def test_region_only_update_needs_no_template_or_heading_type(self):
        entries = [L.LibraryEntry("IWS-105", "", "", "region", "Wall - IWS-105", 2)]
        resolved = self._prepare(_model(), _config(show_heading=False), entries, need_template=False,
                                 text_error="2.5mm Arial Bold x", template_error=True)
        self.assertEqual(resolved["problems"], [])
        self.assertIsNone(resolved["template"])
        self.assertNotIn("heading_text_type", resolved["text_types"])

    def test_hash_changes_with_rows_and_layout(self):
        config = _config()
        entries = [L.LibraryEntry("A", "", "d", "region", "R", 2)]
        first = S.library_hash("Walls", config, entries)
        self.assertEqual(first, S.library_hash("Walls", config, list(entries)))
        changed = [L.LibraryEntry("A", "", "new description", "region", "R", 2)]
        self.assertNotEqual(first, S.library_hash("Walls", config, changed))
        config["layout"]["row_gap_mm"] = 9
        self.assertNotEqual(first, S.library_hash("Walls", config, entries))


class TypeMarkTests(unittest.TestCase):
    def test_marks_from_views_on_a_sheet(self):
        doc = _model()
        sheet = object()
        views = [_Element(100, "view"), _Element(101, "view")]
        db = _fake_db(doc)
        with mock.patch.object(version_adapter, "get_db", return_value=db), \
                mock.patch.object(collectors, "is_sheet", return_value=True), \
                mock.patch.object(collectors, "sheet_source_views", return_value=views):
            marks = collectors.type_marks_for_source(doc, sheet, "OST_Walls", ["FloorPlan"])
        self.assertEqual(marks, ["IWS-105", "IWS-110"])

    def test_type_mark_blank_when_missing(self):
        self.assertEqual(collectors.type_mark(None), "")
        with mock.patch.object(version_adapter, "get_db", return_value=_fake_db(_Doc([]))):
            self.assertEqual(collectors.type_mark(_Element(1, "type", mark=" W1 ")), "W1")
            self.assertEqual(collectors.type_mark(_Element(2, "type")), "")


class RowChoiceTests(unittest.TestCase):
    def test_preselection_maps_codes_to_indexes(self):
        entries = [
            L.LibraryEntry("IWS-105", "", "", "region", "R", 2),
            L.LibraryEntry("IWS-110", "", "", "region", "R", 3),
            L.LibraryEntry("EWS-01", "", "", "region", "R", 4),
        ]
        captured = {}

        def _fake_many(title, labels, preselected=None, prompt=None, button_text="OK"):
            captured["preselected"] = preselected
            return [0, 2]

        with mock.patch.object(dialogs, "choose_many_from_list", side_effect=_fake_many):
            chosen = library_ui.choose_rows("Walls", entries, ["ews-01", "IWS-110", "OLD"], "prompt")
        self.assertEqual(captured["preselected"], [1, 2])
        self.assertEqual([entry.code for entry in chosen], ["IWS-105", "EWS-01"])

    def test_checked_indexes_are_clean(self):
        self.assertEqual(dialogs.checked_indexes([3, 1, 1, -1, 9], 4), [1, 3])
        self.assertEqual(dialogs.checked_indexes(None, 4), [])


if __name__ == "__main__":
    unittest.main()
