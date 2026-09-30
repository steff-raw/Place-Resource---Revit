# -*- coding: utf-8 -*-
"""New Revit warnings are found by comparing Document.GetWarnings() before and after."""

import os
import sys
import unittest

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import transactions


class _Id(object):
    def __init__(self, value):
        self.Value = value


class _Warning(object):
    def __init__(self, text, ids):
        self._text = text
        self._ids = [_Id(value) for value in ids]

    def GetDescriptionText(self):
        return self._text

    def GetFailingElements(self):
        return self._ids


class _Doc(object):
    def __init__(self, warnings):
        self.warnings = warnings

    def GetWarnings(self):
        return self.warnings


class WarningDiffTests(unittest.TestCase):
    def test_only_new_warnings_are_reported(self):
        before = transactions.warning_keys(_Doc([_Warning("Walls overlap", [5, 3])]))
        after = transactions.warning_keys(_Doc([
            _Warning("Walls overlap", [3, 5]),
            _Warning("Text is too long", [9]),
        ]))
        self.assertEqual(
            transactions.new_warning_messages(before, after),
            ["Revit warning: Text is too long (elements 9)"],
        )

    def test_repeated_warning_counts(self):
        before = [("Duplicate", ())]
        after = [("Duplicate", ()), ("Duplicate", ())]
        self.assertEqual(transactions.new_warning_messages(before, after), ["Revit warning: Duplicate"])

    def test_unreadable_warnings_are_skipped(self):
        class _Broken(object):
            def GetWarnings(self):
                raise RuntimeError("not available")
        self.assertIsNone(transactions.warning_keys(_Broken()))
        self.assertEqual(transactions.new_warning_messages(None, [("x", ())]), [])

    def test_no_python_callback_is_defined(self):
        self.assertFalse(hasattr(transactions, "_WarningCollector"))


if __name__ == "__main__":
    unittest.main()
