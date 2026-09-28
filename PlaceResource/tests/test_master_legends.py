# -*- coding: utf-8 -*-
"""Master legend rows, project settings, text style fallback and source choice."""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
CONFIG = os.path.abspath(os.path.join(HERE, "..", "config", "library_legends.json"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import legend_component_service
import legend_library as L
import library_legend_service as S
import library_ui
import master_legend_service
import project_settings
import ui_service
from errors import ConfigurationError, LegendOperationError


def _item(ident, left, top, width=1.0, height=1.0, text=None):
    return {
        "id": ident, "is_text": text is not None, "text": text or "",
        "left": left, "right": left + width, "top": top, "bottom": top - height,
    }


def _master_items():
    """Heading, three rows (mark, graphic, description), a note far left, and a text-only line."""
    return [
        _item(1, 0.0, 12.0, width=8.0, text="WALL TYPES"),        # heading, left column, no graphic
        _item(10, 0.0, 9.0, text="IWS-105"),                       # mark
        _item(11, 3.0, 9.5, width=4.0, height=2.0),                # graphic
        _item(12, 8.0, 9.0, width=10.0, text="Metal stud\n100mm"),  # description
        _item(20, 0.0, 6.0, text="IWS-110"),
        _item(21, 3.0, 6.3, width=4.0, height=1.6),
        _item(22, 8.0, 6.0, width=10.0, text="Blockwork"),
        _item(23, 12.0, 6.0, width=3.0, text="EI60"),
        _item(30, 0.02, 3.0, text="IWS-105"),                      # duplicate code
        _item(31, 3.0, 3.2, width=4.0),
    ]


class RowsFromItemsTests(unittest.TestCase):
    def test_rows_found_by_left_type_mark(self):
        rows, notes = L.rows_from_items(_master_items(), tolerance=0.1)
        self.assertEqual([row["code"] for row in rows], ["IWS-105", "IWS-110"])
        first, second = rows
        self.assertEqual(first["element_ids"], [11, 12])
        self.assertEqual(first["description"], "Metal stud 100mm")
        self.assertEqual(second["element_ids"], [21, 22, 23])
        self.assertEqual(second["description"], "Blockwork EI60")
        self.assertNotIn(20, second["element_ids"])
        self.assertEqual(first["box"]["left"], 3.0)
        self.assertTrue(any("WALL TYPES" in note and "heading" in note for note in notes))
        self.assertTrue(any("appears twice" in note for note in notes))

    def test_single_row_takes_everything_right_of_the_mark(self):
        items = [_item(1, 0.0, 5.0, text="FR-60"), _item(2, 2.0, 30.0), _item(3, -5.0, 5.0)]
        rows, _notes = L.rows_from_items(items, tolerance=0.1)
        self.assertEqual(rows[0]["element_ids"], [2])

    def test_no_text_means_no_rows(self):
        rows, notes = L.rows_from_items([_item(1, 0.0, 1.0)], tolerance=0.1)
        self.assertEqual(rows, [])
        self.assertIn("no text notes", notes[0])

    def test_fingerprint_changes_when_a_row_changes(self):
        rows, _ = L.rows_from_items(_master_items(), tolerance=0.1)
        items = _master_items()
        items[3]["text"] = "Metal stud 150mm"
        changed, _ = L.rows_from_items(items, tolerance=0.1)
        self.assertNotEqual(rows[0]["fingerprint"], changed[0]["fingerprint"])
        self.assertEqual(rows[1]["fingerprint"], changed[1]["fingerprint"])
        config = L.validate_settings({"schema_version": "1.0", "library_file": "x.xlsx",
                                      "categories": [{"name": "Walls"}]})["Walls"]
        before = S.library_hash("Walls", config, [L.master_entry(rows[0], 1)])
        after = S.library_hash("Walls", config, [L.master_entry(changed[0], 1)])
        self.assertNotEqual(before, after)

    def test_master_entry_carries_ids_and_source(self):
        rows, _ = L.rows_from_items(_master_items(), tolerance=0.1)
        entry = L.master_entry(rows[1], 2)
        self.assertEqual(entry.source, L.SOURCE_MASTER)
        self.assertEqual(entry.element_ids, [21, 22, 23])
        self.assertIn("Blockwork", entry.label())


class ProjectSettingsTests(unittest.TestCase):
    def test_normalize_drops_bad_values(self):
        data = project_settings.normalize({"text_type": "  2.5mm Arial ", "masters": {"Walls": "abc", "Doors": "", 3: "x"}})
        self.assertEqual(data, {"text_type": "2.5mm Arial", "masters": {"Walls": "abc"}})
        self.assertEqual(project_settings.normalize(None), {"text_type": None, "masters": {}})
        self.assertIn("not set", project_settings.describe({}))


class TextStyleTests(unittest.TestCase):
    def test_saved_style_wins_then_settings_file(self):
        calls = []

        def _find(doc, name):
            calls.append(name)
            if name == "Missing":
                raise LegendOperationError("missing")
            return name

        with mock.patch.object(legend_component_service, "find_text_type", side_effect=_find), \
                mock.patch.object(project_settings, "text_type_name", return_value="Office Text"):
            self.assertEqual(legend_component_service.resolve_text_type(None, "2.5mm Arial"), "Office Text")
        with mock.patch.object(legend_component_service, "find_text_type", side_effect=_find), \
                mock.patch.object(project_settings, "text_type_name", return_value="Missing"):
            self.assertEqual(legend_component_service.resolve_text_type(None, "2.5mm Arial"), "2.5mm Arial")
        with mock.patch.object(legend_component_service, "find_text_type", side_effect=_find), \
                mock.patch.object(project_settings, "text_type_name", return_value=None):
            self.assertFalse(legend_component_service.text_types_resolve(None, ["Missing"]))

    def test_picker_only_when_needed(self):
        with mock.patch.object(legend_component_service, "text_types_resolve", return_value=True), \
                mock.patch.object(ui_service, "choose_text_type") as picker:
            self.assertTrue(ui_service.ensure_text_style(None, ["2.5mm Arial"]))
            picker.assert_not_called()
        with mock.patch.object(legend_component_service, "text_types_resolve", return_value=False), \
                mock.patch.object(ui_service, "choose_text_type", return_value="Annotation - 1.5mm") as picker:
            self.assertTrue(ui_service.ensure_text_style(None, ["2.5mm Arial"]))
            self.assertIn("2.5mm Arial", picker.call_args[1]["reason"])
        with mock.patch.object(legend_component_service, "text_types_resolve", return_value=False), \
                mock.patch.object(ui_service, "choose_text_type", return_value=None):
            self.assertFalse(ui_service.ensure_text_style(None, ["2.5mm Arial"]))


class SourceChoiceTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "library": {"Walls": [L.LibraryEntry("IWS-105", "", "", "region", "R", 2)]},
            "library_error": None,
        }

    def test_linked_master_is_used(self):
        master = mock.Mock()
        master.Name = "MASTER - Walls"
        rows = [L.LibraryEntry("IWS-110", "", "", "master", "", 1)]
        with mock.patch.object(project_settings, "read", return_value={"text_type": None, "masters": {"Walls": "u"}}), \
                mock.patch.object(project_settings, "master_for", return_value=master), \
                mock.patch.object(master_legend_service, "read_master", return_value=(rows, [])):
            entries, source, notes = library_ui.category_entries(None, self.settings, "Walls")
        self.assertEqual([entry.code for entry in entries], ["IWS-110"])
        self.assertEqual(source, "master legend 'MASTER - Walls'")

    def test_deleted_master_falls_back_to_excel_with_a_note(self):
        with mock.patch.object(project_settings, "read", return_value={"text_type": None, "masters": {"Walls": "u"}}), \
                mock.patch.object(project_settings, "master_for", return_value=None):
            entries, source, notes = library_ui.category_entries(None, self.settings, "Walls")
        self.assertEqual(source, "Excel library")
        self.assertEqual(entries[0].code, "IWS-105")
        self.assertIn("was deleted", notes[0])

    def test_unreadable_excel_keeps_categories(self):
        def _broken(path):
            raise ConfigurationError("workbook is broken")
        loaded = L.load_library_settings(CONFIG, read_workbook=_broken)
        self.assertEqual(loaded["library_error"], "workbook is broken")
        self.assertEqual(len(loaded["categories"]), 12)
        self.assertEqual(loaded["library"]["Walls"], [])


if __name__ == "__main__":
    unittest.main()
