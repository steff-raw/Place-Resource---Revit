# -*- coding: utf-8 -*-
"""TaskDialog wiring for the CPython-safe dialogs, using a fake Revit UI module."""

import os
import sys
import types
import unittest

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)


class _Enum(object):
    def __init__(self, *names):
        for name in names:
            setattr(self, name, name)


_LINKS = ("CommandLink1", "CommandLink2", "CommandLink3", "CommandLink4")


class _FakeTaskDialog(object):
    answer = None
    last = None

    def __init__(self, title):
        self.title = title
        self.links = []
        _FakeTaskDialog.last = self

    def AddCommandLink(self, link_id, label, detail=None):
        self.links.append((link_id, label, detail))

    def Show(self):
        return _FakeTaskDialog.answer


def _install_fake_ui():
    ui = types.ModuleType("Autodesk.Revit.UI")
    ui.TaskDialog = _FakeTaskDialog
    ui.TaskDialogCommandLinkId = _Enum(*_LINKS)
    ui.TaskDialogResult = _Enum(*(_LINKS + ("Cancel", "Close")))
    ui.TaskDialogCommonButtons = _Enum("Cancel", "Ok")
    autodesk = types.ModuleType("Autodesk")
    revit = types.ModuleType("Autodesk.Revit")
    autodesk.Revit = revit
    revit.UI = ui
    sys.modules["Autodesk"] = autodesk
    sys.modules["Autodesk.Revit"] = revit
    sys.modules["Autodesk.Revit.UI"] = ui


class DialogTests(unittest.TestCase):
    def setUp(self):
        self._saved = {name: sys.modules.get(name) for name in ("Autodesk", "Autodesk.Revit", "Autodesk.Revit.UI")}
        _install_fake_ui()
        import dialogs
        self.dialogs = dialogs

    def tearDown(self):
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_command_link_maps_to_key(self):
        _FakeTaskDialog.answer = "CommandLink2"
        key = self.dialogs.choose_command("T", "Pick", [("a", "A"), ("b", "B", "detail")])
        self.assertEqual(key, "b")
        self.assertEqual(_FakeTaskDialog.last.links[1], ("CommandLink2", "B", "detail"))

    def test_cancel_returns_none(self):
        _FakeTaskDialog.answer = "Cancel"
        self.assertIsNone(self.dialogs.choose_command("T", "Pick", [("a", "A")]))

    def test_more_than_four_options_is_rejected(self):
        with self.assertRaises(ValueError):
            self.dialogs.choose_command("T", "Pick", [(str(i), str(i)) for i in range(5)])

    def test_yes_no(self):
        _FakeTaskDialog.answer = "CommandLink1"
        self.assertTrue(self.dialogs.ask_yes_no("T", "Sure?"))
        _FakeTaskDialog.answer = "CommandLink2"
        self.assertFalse(self.dialogs.ask_yes_no("T", "Sure?"))
        _FakeTaskDialog.answer = "Close"
        self.assertFalse(self.dialogs.ask_yes_no("T", "Sure?"))

    def test_sizes_scale_with_screen_dpi(self):
        self.assertEqual(self.dialogs.scaled(820, 1.0), 820)
        self.assertEqual(self.dialogs.scaled(820, 1.5), 1230)
        self.assertEqual(self.dialogs.scaled(34, 1.25), 43)
        self.assertEqual(self.dialogs.scaled(0.2, 1.0), 1)
        self.assertEqual(self.dialogs.scaled(52, None), 52)

    def test_fields_do_not_overlap(self):
        positions, total = self.dialogs.field_positions(3, 24, 28, 14, 14)
        self.assertEqual(positions, [(14, 38), (80, 104), (146, 170)])
        for (label_top, box_top), (next_label, _box) in zip(positions, positions[1:]):
            self.assertGreaterEqual(next_label, box_top + 28)
        self.assertEqual(total, 14 + 3 * (24 + 28) + 2 * 14 + 14)

    def test_rows_show_details(self):
        rows = self.dialogs.row_labels(["Validate", "Choose", "Open"], ["check the file", None])
        self.assertEqual(rows, ["Validate - check the file", "Choose", "Open"])
        self.assertEqual(self.dialogs.row_labels(["A"]), ["A"])

    def test_every_settings_action_has_a_detail(self):
        import ui_service
        self.assertEqual(len(ui_service.SETTINGS_DETAILS), len(ui_service.SETTINGS_ACTIONS))
        self.assertTrue(all(ui_service.SETTINGS_DETAILS))

    def test_settings_actions_round_trip(self):
        from unittest import mock
        import ui_service
        self.assertEqual(ui_service.SETTINGS_ACTIONS[0], "Legend text style")
        self.assertNotIn("Link master legends", ui_service.SETTINGS_ACTIONS)
        for index, name in enumerate(ui_service.SETTINGS_ACTIONS):
            with mock.patch.object(self.dialogs, "choose_from_list", return_value=index):
                self.assertEqual(ui_service.choose_settings_action(), name)
        with mock.patch.object(self.dialogs, "choose_from_list", return_value=None):
            self.assertIsNone(ui_service.choose_settings_action())

    def test_confirm_plan_choices(self):
        import ui_service

        class _View(object):
            Name = "Level 01"

        class _Collection(object):
            view_info = {"view_type": "FloorPlan"}
            instance_count = 3
            unique_type_count = 2
            warnings = []

        plan = {
            "collection": _Collection(),
            "existing_name": None,
            "estimate": {"block": {"width": 0.5, "height": 0.25}},
            "mode": "create",
            "to_add": [1, 2],
            "to_remove": [],
        }
        definition = {"display_name": "Wall Type Legend"}
        expected = {
            "CommandLink1": {"apply_changes": True, "place_on_sheet": False},
            "CommandLink2": {"apply_changes": True, "place_on_sheet": True},
            "CommandLink3": {"apply_changes": False, "place_on_sheet": False},
        }
        for answer, choices in expected.items():
            _FakeTaskDialog.answer = answer
            self.assertEqual(ui_service.confirm_plan(_View(), definition, plan), choices)
        _FakeTaskDialog.answer = "Cancel"
        self.assertIsNone(ui_service.confirm_plan(_View(), definition, plan))


if __name__ == "__main__":
    unittest.main()
