# -*- coding: utf-8 -*-
"""Symbol-family library: settings, family reading, pre-transaction checks, Type Marks."""

import copy
import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
CONFIG = os.path.abspath(os.path.join(HERE, "..", "config", "library_legends.json"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import collectors
import dialogs
import legend_library as L
import library_legend_service as S
import library_ui
import symbol_library
import version_adapter
from errors import ConfigurationError, LegendOperationError


class _Id(object):
    def __init__(self, value):
        self.Value = value


class _Param(object):
    def __init__(self, value):
        self._value = value

    def AsString(self):
        return self._value

    def AsValueString(self):
        return self._value


class _Category(object):
    def __init__(self, value, name):
        self.Id = _Id(value)
        self.Name = name


class _Element(object):
    def __init__(self, value, kind, name="", category=None, mark=None, type_id=None, views=(),
                 params=None, symbol_ids=(), family_category=None):
        self.Id = _Id(value)
        self.UniqueId = "u{0}".format(value)
        self.kind = kind
        self.Name = name
        self.category = category
        self._mark = mark
        self._type_id = type_id
        self.views = set(views)
        self._params = params or {}
        self._symbol_ids = [_Id(item) for item in symbol_ids]
        self.FamilyCategory = family_category

    def get_Parameter(self, parameter):
        return _Param(self._mark) if self._mark is not None else None

    def LookupParameter(self, name):
        return _Param(self._params[name]) if name in self._params else None

    def GetTypeId(self):
        return _Id(self._type_id if self._type_id is not None else -1)

    def GetFamilySymbolIds(self):
        return self._symbol_ids


class _Doc(object):
    def __init__(self, elements):
        self.elements = elements

    def GetElement(self, element_id):
        for element in self.elements:
            if element.Id.Value == element_id.Value:
                return element
        return None


class _Family(object):
    pass


GENERIC_ANNOTATION = -2000150
WALLS = -2000011


def _fake_db(doc):
    class _Collector(object):
        def __init__(self, document, view_id=None):
            self._items = list(document.elements)
            if view_id is not None:
                self._items = [item for item in self._items if view_id.Value in item.views]

        def OfClass(self, cls):
            if cls is _Family:
                self._items = [item for item in self._items if item.kind == "family"]
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

    categories = {"OST_GenericAnnotation": GENERIC_ANNOTATION, "OST_DetailComponents": -2002000, "OST_Walls": "OST_Walls"}

    def _element_id(value):
        return _Id(value)

    return type("DB", (), {
        "FilteredElementCollector": _Collector,
        "Family": _Family,
        "ElementId": staticmethod(_element_id),
        "BuiltInCategory": type("BIC", (), categories),
        "BuiltInParameter": type("BIP", (), {"ALL_MODEL_TYPE_MARK": "ALL_MODEL_TYPE_MARK"}),
    })


def _config(**overrides):
    item = {"name": "Walls", "revit_category": "OST_Walls"}
    item.update(overrides)
    return L.validate_settings({"schema_version": "2.0", "categories": [item]})["Walls"]


def _model(family_category=GENERIC_ANNOTATION):
    return _Doc([
        _Element(1, "family", name="PR Legend - Walls", symbol_ids=(10, 11, 12),
                 family_category=_Category(family_category, "Generic Annotations")),
        _Element(10, "symbol", name="IWS-110", params={"Legend_Description": "Blockwork"}),
        _Element(11, "symbol", name="IWS-105", params={"Legend_Description": "Metal stud"}),
        _Element(12, "symbol", name="IWS-9"),
        _Element(20, "type", name="Stud 105", category="OST_Walls", mark="IWS-105"),
        _Element(21, "type", name="Block 110", category="OST_Walls", mark="IWS-110"),
        _Element(30, "instance", category="OST_Walls", type_id=20, views=(100,)),
        _Element(31, "instance", category="OST_Walls", type_id=21, views=(101,)),
    ])


class _Patches(object):
    """Patch get_db where it is looked up at call time and where it was bound at import."""

    def __init__(self, db):
        self._patches = [
            mock.patch.object(version_adapter, "get_db", return_value=db),
            mock.patch.object(symbol_library, "get_db", return_value=db),
        ]

    def __enter__(self):
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *exc):
        for patch in reversed(self._patches):
            patch.stop()
        return False


def _patched(doc):
    db = _fake_db(doc)
    return _Patches(db), db


class SettingsTests(unittest.TestCase):
    def test_shipped_settings_load(self):
        loaded = L.load_library_settings(CONFIG)
        categories = loaded["categories"]
        self.assertEqual(len(categories), 12)
        self.assertEqual(categories["Walls"]["family_name"], "PR Legend - Walls")
        self.assertEqual(categories["Fire Strategy"]["family_name"], "PR Legend - Fire Strategy")
        self.assertEqual(categories["Walls"]["description_parameter"], "Legend_Description")

    def test_old_excel_schema_is_rejected_with_a_hint(self):
        with self.assertRaises(ConfigurationError) as caught:
            L.validate_settings({"schema_version": "1.0", "categories": [{"name": "Walls"}]})
        self.assertIn("old Excel library", str(caught.exception))

    def test_invalid_settings_are_rejected(self):
        with open(CONFIG, encoding="utf-8") as handle:
            base = json.load(handle)
        cases = []
        bad = copy.deepcopy(base); bad["categories"].append(copy.deepcopy(bad["categories"][0])); cases.append(bad)
        bad = copy.deepcopy(base); bad["categories"][0]["revit_category"] = "Walls"; cases.append(bad)
        bad = copy.deepcopy(base); bad["categories"][0]["scale"] = 0; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["styles"]["heading_text_type"] = ""; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["layout"]["row_gap_mm"] = -1; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["family_name"] = ""; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["styles"]["text_type"] = ""; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["show_type_mark"] = "yes"; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["headings"] = {"title": 5}; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["text_visibility_parameter"] = ""; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["layout"]["width_mm"] = 5; cases.append(bad)
        bad = copy.deepcopy(base); bad["defaults"]["layout"]["text_pattern"] = None; cases.append(bad)
        for data in cases:
            with self.assertRaises(ConfigurationError):
                L.validate_settings(data)

    def test_family_name_override(self):
        config = _config(family_name="Office Wall Symbols")
        self.assertEqual(config["family_name"], "Office Wall Symbols")


class FamilyEntryTests(unittest.TestCase):
    def test_types_become_rows_sorted_naturally(self):
        doc = _model()
        patch, _db = _patched(doc)
        with patch:
            entries, problems = symbol_library.family_entries(doc, _config())
        self.assertEqual(problems, [])
        self.assertEqual([entry.code for entry in entries], ["IWS-9", "IWS-105", "IWS-110"])
        self.assertEqual(entries[1].description, "Metal stud")
        self.assertEqual(entries[1].label(), "IWS-105 - Metal stud")
        self.assertEqual(entries[0].label(), "IWS-9")
        self.assertEqual(entries[1].symbol_unique_id, "u11")

    def test_missing_family_and_wrong_category(self):
        doc = _model()
        patch, _db = _patched(doc)
        with patch:
            _entries, problems = symbol_library.family_entries(doc, _config(family_name="Nope"))
        self.assertIn("'Nope' is not loaded", problems[0])
        doc = _model(family_category=WALLS)
        patch, _db = _patched(doc)
        with patch:
            _entries, problems = symbol_library.family_entries(doc, _config())
        self.assertIn("has to be a Generic Annotation", problems[0])

    def test_family_name_match_ignores_case(self):
        doc = _model()
        patch, _db = _patched(doc)
        with patch:
            self.assertIsNotNone(symbol_library.find_family(doc, "pr legend - walls"))


class PrepareTests(unittest.TestCase):
    def _prepare(self, entries, symbols, need_template=True, show_heading=True, text_error=False, template_error=False,
                 show_text=True):
        config = _config()
        config["styles"]["show_heading"] = show_heading
        config["styles"]["show_text"] = show_text

        def _text(_doc, name):
            if text_error:
                raise LegendOperationError("Text note type '{0}' was not found.".format(name))
            return "text-type"

        def _template(_doc, name):
            if template_error:
                raise LegendOperationError("Template legend '{0}' was not found.".format(name))
            return "template"

        with mock.patch.object(S, "symbols_by_code", return_value=symbols), \
                mock.patch.object(S, "resolve_text_type", side_effect=_text), \
                mock.patch.object(S, "find_source_legend", side_effect=_template):
            return S.prepare(None, config, entries, need_template)

    def test_everything_resolves(self):
        entries = [L.LibraryEntry("IWS-105"), L.LibraryEntry("IWS-110")]
        resolved = self._prepare(entries, {"IWS-105": "s1", "IWS-110": "s2"})
        self.assertEqual(resolved["problems"], [])
        self.assertEqual(resolved["heading_type"], "text-type")
        self.assertEqual(resolved["text_type"], "text-type")
        self.assertEqual(resolved["template"], "template")

    def test_all_problems_are_reported_together(self):
        entries = [L.LibraryEntry("IWS-105"), L.LibraryEntry("IWS-999")]
        resolved = self._prepare(entries, {"IWS-105": "s1"}, text_error=True, template_error=True)
        problems = "\n".join(resolved["problems"])
        self.assertIn("no type called IWS-999", problems)
        self.assertIn("Text note type", problems)
        self.assertIn("Template legend", problems)

    def test_update_without_heading_needs_no_template_or_text(self):
        entries = [L.LibraryEntry("IWS-105")]
        resolved = self._prepare(entries, {"IWS-105": "s1"}, need_template=False, show_heading=False,
                                 text_error=True, template_error=True, show_text=False)
        self.assertEqual(resolved["problems"], [])
        self.assertIsNone(resolved["template"])
        self.assertIsNone(resolved["heading_type"])

    def test_hash_changes_with_rows_family_and_layout(self):
        config = _config()
        entries = [L.LibraryEntry("A", symbol_unique_id="x")]
        first = S.library_hash("Walls", config, entries)
        self.assertEqual(first, S.library_hash("Walls", config, [L.LibraryEntry("A", symbol_unique_id="x")]))
        self.assertNotEqual(first, S.library_hash("Walls", config, [L.LibraryEntry("A", symbol_unique_id="y")]))
        self.assertNotEqual(first, S.library_hash("Walls", _config(family_name="Other"), entries))
        self.assertNotEqual(first, S.library_hash("Walls", config, [L.LibraryEntry("A", "new text", symbol_unique_id="x")]))
        self.assertNotEqual(first, S.library_hash("Walls", config, entries, width_mm=90))
        self.assertEqual(first, S.library_hash("Walls", config, entries, width_mm=config["layout"]["width_mm"]))
        self.assertEqual(first, S.library_hash("Walls", config, entries, show_type_mark=True))
        self.assertNotEqual(first, S.library_hash("Walls", config, entries, show_type_mark=False))
        config["layout"]["row_gap_mm"] = 9
        self.assertNotEqual(first, S.library_hash("Walls", config, entries))


class StackTests(unittest.TestCase):
    def test_rows_stack_under_heading(self):
        tops, bottom = L.stack_rows([4.0, 6.0, 2.0], row_gap=1.0, heading_height=3.0, heading_gap=2.0)
        self.assertEqual(tops, [-5.0, -10.0, -17.0])
        self.assertEqual(bottom, -19.0)

    def test_rows_without_heading_start_at_zero(self):
        tops, bottom = L.stack_rows([2.0], row_gap=5.0)
        self.assertEqual(tops, [0.0])
        self.assertEqual(bottom, -2.0)
        self.assertEqual(L.stack_rows([], 1.0), ([], 0.0))


class TableTests(unittest.TestCase):
    def test_title_header_and_rows(self):
        table = L.table_layout(100.0, 10.0, 1.0, 4.0, 3.0, [5.0, 2.0])
        self.assertEqual(table["split_x"], 12.0)
        self.assertEqual(table["title"], (0.0, -6.0))
        self.assertEqual(table["header"], (-6.0, -11.0))
        self.assertEqual(table["rows"], [(-11.0, -18.0), (-18.0, -22.0)])
        self.assertEqual(table["h_lines"], [0.0, -6.0, -11.0, -18.0, -22.0])
        # Outer sides run full height; the column line starts under the title.
        self.assertEqual(table["v_lines"], [(0.0, 0.0, -22.0), (100.0, 0.0, -22.0), (12.0, -6.0, -22.0)])

    def test_rows_only(self):
        table = L.table_layout(50.0, 8.0, 1.0, None, None, [2.0])
        self.assertIsNone(table["title"])
        self.assertIsNone(table["header"])
        self.assertEqual(table["h_lines"], [0.0, -4.0])
        self.assertEqual(len(table["v_lines"]), 3)

    def test_centred_in_cell(self):
        self.assertEqual(L.centred_top_left(0.0, 10.0, 0.0, -6.0, 4.0, 2.0), (3.0, -2.0))

    def test_headings(self):
        config = _config()
        self.assertEqual(L.default_headings(config),
                         {"title": "Walls LEGEND", "graphic": "CODE", "description": "DESCRIPTION"})
        self.assertEqual(
            L.clean_headings({"title": " PARTITION TYPES LEGEND ", "graphic": ""}, L.default_headings(config)),
            {"title": "PARTITION TYPES LEGEND", "graphic": "", "description": "DESCRIPTION"},
        )

    def test_hash_changes_with_headings(self):
        config = _config()
        entries = [L.LibraryEntry("A", symbol_unique_id="x")]
        first = S.library_hash("Walls", config, entries)
        self.assertEqual(first, S.library_hash("Walls", config, entries, headings=L.default_headings(config)))
        self.assertNotEqual(first, S.library_hash("Walls", config, entries, headings={"title": "PARTITIONS"}))

    def test_headings_remembered_per_category(self):
        config = _config()
        saved = {}
        with mock.patch("project_settings.saved_headings", return_value={"title": "PARTITION TYPES LEGEND"}), \
                mock.patch("project_settings.save_headings", side_effect=lambda doc, cat, h: saved.update({cat: h})), \
                mock.patch.object(dialogs, "ask_fields", return_value=["PARTITION TYPES LEGEND", "SRS CODE", " DESCRIPTION "]) as ask:
            headings = library_ui.ask_headings(None, config, None)
        defaults = [default for _label, default in ask.call_args[0][2]]
        self.assertEqual(defaults, ["PARTITION TYPES LEGEND", "CODE", "DESCRIPTION"])
        self.assertEqual(headings, {"title": "PARTITION TYPES LEGEND", "graphic": "SRS CODE", "description": "DESCRIPTION"})
        self.assertEqual(saved, {"Walls": headings})
        with mock.patch("project_settings.saved_headings", return_value={}), \
                mock.patch.object(dialogs, "ask_fields", return_value=None):
            self.assertIsNone(library_ui.ask_headings(None, config, None))


class SourceLegendTests(unittest.TestCase):
    def test_named_legend_first_then_any_legend(self):
        self.assertEqual(S.pick_source_legend(["Door Key", "_TEMPLATE - LIBRARY LEGEND"], "_TEMPLATE - LIBRARY LEGEND"), 1)
        self.assertEqual(S.pick_source_legend(["Wall Key", "Door Key"], "_TEMPLATE - LIBRARY LEGEND"), 1)
        self.assertIsNone(S.pick_source_legend([], "_TEMPLATE - LIBRARY LEGEND"))


class TextLayoutTests(unittest.TestCase):
    def test_text_width_is_what_the_graphic_leaves(self):
        self.assertEqual(L.text_width_mm(120, 20, 3), 97.0)
        with self.assertRaises(ValueError) as caught:
            L.text_width_mm(30, 20, 3)
        self.assertIn("at least 38 mm", str(caught.exception))

    def test_row_is_as_tall_as_graphic_or_text(self):
        self.assertEqual(L.row_heights([4.0, 6.0, 0.0], [5.0, 2.0, 3.0]), [5.0, 6.0, 3.0])

    def test_text_pattern(self):
        entry = L.LibraryEntry("IWS-105", "Metal stud partition")
        self.assertEqual(L.format_text("{description}", entry), "Metal stud partition")
        self.assertEqual(L.format_text("{code}  {description}", entry), "IWS-105  Metal stud partition")
        self.assertEqual(L.format_text("{description}", L.LibraryEntry("IWS-105")), "")

    def test_width_typed_in_cm(self):
        self.assertEqual(L.parse_width_cm("12"), 120.0)
        self.assertEqual(L.parse_width_cm(" 12,5 cm"), 125.0)
        for text in ("", "abc", "1", "150", None):
            self.assertIsNone(L.parse_width_cm(text))

    def test_box_drawn_in_any_direction(self):
        import placement_service
        self.assertEqual(placement_service.box_top_left_and_width(5.0, 1.0, 2.0, 4.0), (2.0, 4.0, 3.0))
        self.assertEqual(placement_service.box_top_left_and_width(2.0, 4.0, 5.0, 1.0), (2.0, 4.0, 3.0))

    def test_width_falls_back_to_settings(self):
        config = _config()
        self.assertEqual(S.legend_width_mm(config), 120.0)
        self.assertEqual(S.legend_width_mm(config, 85), 85.0)


class _YesNo(object):
    def __init__(self, read_only=False):
        self.IsReadOnly = read_only
        self.value = None

    def Set(self, value):
        self.value = value


class _Symbol(object):
    def __init__(self, **params):
        self.params = params

    def LookupParameter(self, name):
        return self.params.get(name)


class ToggleTests(unittest.TestCase):
    def test_family_parameter_defaults(self):
        config = _config()
        self.assertEqual(config["description_parameter"], "Legend_Description")
        self.assertEqual(config["type_mark_visibility_parameter"], "Legend_TypeMark_Visibility")
        self.assertEqual(config["text_visibility_parameter"], "Text_Visibility")
        self.assertTrue(config["show_type_mark"])

    def test_type_mark_as_chosen_and_family_text_always_off(self):
        config = _config()
        for show, expected in ((True, 1), (False, 0)):
            mark, text = _YesNo(), _YesNo()
            report = {"warnings": []}
            S._set_toggles([_Symbol(Legend_TypeMark_Visibility=mark, Text_Visibility=text)], config, show, report)
            self.assertEqual((mark.value, text.value), (expected, 0))
            self.assertEqual(report["warnings"], [])

    def test_missing_parameter_warns_once(self):
        report = {"warnings": []}
        symbols = [_Symbol(Text_Visibility=_YesNo()), _Symbol(Text_Visibility=_YesNo())]
        S._set_toggles(symbols, _config(), True, report)
        self.assertEqual(len(report["warnings"]), 1)
        self.assertIn("Legend_TypeMark_Visibility", report["warnings"][0])

    def test_last_answer_is_listed_first(self):
        config = _config()
        seen = []

        def _choose(title, instruction, options, **_kw):
            seen.append([key for key, *_rest in options])
            return "hide"

        with mock.patch.object(dialogs, "choose_command", side_effect=_choose):
            self.assertFalse(library_ui.ask_type_mark(config, None))
            config["show_type_mark"] = False
            library_ui.ask_type_mark(config, None)
        self.assertEqual(seen, [["show", "hide"], ["hide", "show"]])
        with mock.patch.object(dialogs, "choose_command", return_value=None):
            self.assertIsNone(library_ui.ask_type_mark(config, None))


class MatchingTests(unittest.TestCase):
    def test_type_marks_and_codes(self):
        entries = [L.LibraryEntry("IWS-105"), L.LibraryEntry("IWS-110"), L.LibraryEntry("EWS-01")]
        self.assertEqual(L.match_type_marks(entries, ["iws-110 ", "EWS-01", None, ""]), ["IWS-110", "EWS-01"])
        self.assertEqual([entry.code for entry in L.entries_for_codes(entries, ["ews-01", "IWS-105"])], ["IWS-105", "EWS-01"])
        self.assertEqual(L.missing_codes(entries, ["IWS-105", "OLD-1"]), ["OLD-1"])


class TypeMarkTests(unittest.TestCase):
    def test_marks_from_views_on_a_sheet(self):
        doc = _model()
        views = [_Element(100, "view"), _Element(101, "view")]
        patch, _db = _patched(doc)
        with patch, mock.patch.object(collectors, "is_sheet", return_value=True), \
                mock.patch.object(collectors, "sheet_source_views", return_value=views):
            marks = collectors.type_marks_for_source(doc, object(), "OST_Walls", ["FloorPlan"])
        self.assertEqual(marks, ["IWS-105", "IWS-110"])

    def test_type_mark_blank_when_missing(self):
        self.assertEqual(collectors.type_mark(None), "")
        patch, _db = _patched(_Doc([]))
        with patch:
            self.assertEqual(collectors.type_mark(_Element(1, "type", mark=" W1 ")), "W1")
            self.assertEqual(collectors.type_mark(_Element(2, "type")), "")


class RowChoiceTests(unittest.TestCase):
    def test_preselection_maps_codes_to_indexes(self):
        entries = [L.LibraryEntry("IWS-105"), L.LibraryEntry("IWS-110"), L.LibraryEntry("EWS-01")]
        captured = {}

        def _fake_many(title, labels, preselected=None, prompt=None, button_text="OK", details=None):
            captured["preselected"] = preselected
            return [0, 2]

        with mock.patch.object(library_ui, "family_entries", return_value=(entries, [])), \
                mock.patch.object(dialogs, "choose_many_from_list", side_effect=_fake_many):
            chosen = library_ui.choose_rows(None, _config(), ["ews-01", "IWS-110", "OLD"], "prompt")
        self.assertEqual(captured["preselected"], [1, 2])
        self.assertEqual([entry.code for entry in chosen], ["IWS-105", "EWS-01"])

    def test_unusable_family_stops_with_a_message(self):
        with mock.patch.object(library_ui, "family_entries", return_value=([], ["Family 'X' is not loaded."])), \
                mock.patch.object(dialogs, "alert") as alert:
            self.assertIsNone(library_ui.choose_rows(None, _config(), [], "prompt"))
        self.assertIn("not loaded", alert.call_args[0][0])

    def test_checked_indexes_are_clean(self):
        self.assertEqual(dialogs.checked_indexes([3, 1, 1, -1, 9], 4), [1, 3])


if __name__ == "__main__":
    unittest.main()
