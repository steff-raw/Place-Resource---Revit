# -*- coding: utf-8 -*-
"""Standard-library .xlsx reading."""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.abspath(os.path.join(HERE, "..", "lib"))
for path in (LIB, HERE):
    if path not in sys.path:
        sys.path.insert(0, path)

from errors import ConfigurationError
from xlsx_fixture import write_workbook
from xlsx_reader import column_index, read_workbook, sheet_records


class XlsxReaderTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def _path(self, name="book.xlsx"):
        return os.path.join(self.folder, name)

    def test_shared_and_inline_strings_numbers_and_gaps(self):
        sheets = OrderedDict([
            ("Walls", [
                ["Code", "Description", "Width"],
                ["IWS-105", "Metal stud & board <100>", 105],
                [],
                ["IWS-110", "", 2.5],
            ]),
            ("Fire Strategy", [["Code"], ["FR-60"]]),
        ])
        for shared in (True, False):
            path = self._path("shared.xlsx" if shared else "inline.xlsx")
            write_workbook(path, sheets, shared_strings=shared)
            book = read_workbook(path)
            self.assertEqual(list(book.keys()), ["Walls", "Fire Strategy"])
            self.assertEqual(book["Walls"][1], ["IWS-105", "Metal stud & board <100>", "105"])
            self.assertEqual(book["Walls"][2], ["", "", ""])
            self.assertEqual(book["Walls"][3], ["IWS-110", "", "2.5"])
            self.assertEqual(book["Fire Strategy"][1], ["FR-60"])

    def test_records_skip_blank_rows_and_keep_row_numbers(self):
        rows = [["", ""], ["Code", "Title"], ["A", "x"], ["", ""], ["B", ""]]
        records = sheet_records(rows)
        self.assertEqual([record["code"] for record in records], ["A", "B"])
        self.assertEqual([record["__row__"] for record in records], [3, 5])

    def test_column_letters(self):
        self.assertEqual(column_index("A1"), 0)
        self.assertEqual(column_index("Z9"), 25)
        self.assertEqual(column_index("AA3"), 26)
        self.assertEqual(column_index("AZ3"), 51)

    def test_rich_text_and_phonetic_runs(self):
        path = self._path()
        write_workbook(path, OrderedDict([("S", [["x"]])]))
        with zipfile.ZipFile(path) as source:
            parts = {name: source.read(name) for name in source.namelist()}
        parts["xl/sharedStrings.xml"] = (
            b'<?xml version="1.0"?><sst xmlns="urn:x"><si><r><t>Fire </t></r><r><t>60</t></r>'
            b'<rPh><t>skip</t></rPh></si></sst>'
        )
        rich = self._path("rich.xlsx")
        with zipfile.ZipFile(rich, "w") as target:
            for name, data in parts.items():
                target.writestr(name, data)
        self.assertEqual(read_workbook(rich)["S"][0], ["Fire 60"])

    def test_missing_and_invalid_files(self):
        with self.assertRaises(ConfigurationError):
            read_workbook(self._path("missing.xlsx"))
        bad = self._path("bad.xlsx")
        with open(bad, "w") as handle:
            handle.write("Code,Title\n")
        with self.assertRaises(ConfigurationError) as caught:
            read_workbook(bad)
        self.assertIn("not an Excel .xlsx", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
