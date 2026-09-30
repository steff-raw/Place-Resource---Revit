# -*- coding: utf-8 -*-
"""Natural sort and multi-key record ordering."""

import os
import sys
import unittest

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from layout_engine import natural_sort_key, sort_records


class _Record(object):
    def __init__(self, type_id, values):
        self.type_id = type_id
        self.values = values


def _value(record, parameter):
    if parameter == "__type_id__":
        return record.type_id
    return record.values.get(parameter)


class NaturalSortTests(unittest.TestCase):
    def test_wall_marks_sort_numerically(self):
        ordered = sorted(["W10", "W2", "W1", "w3"], key=natural_sort_key)
        self.assertEqual(ordered, ["W1", "W2", "w3", "W10"])

    def test_empty_and_none_sort_first(self):
        ordered = sorted([None, "B", ""], key=natural_sort_key)
        self.assertEqual(ordered[0], None)
        self.assertEqual(ordered[1], "")

    def test_multi_key_sort_is_stable(self):
        records = [
            _Record(30, {"Type Mark": "W2", "Type Name": "Block"}),
            _Record(10, {"Type Mark": "W10", "Type Name": "Stud"}),
            _Record(20, {"Type Mark": "W2", "Type Name": "Stud"}),
        ]
        rules = [
            {"parameter": "Type Mark", "direction": "ascending", "natural_sort": True},
            {"parameter": "Type Name", "direction": "ascending", "natural_sort": True},
        ]
        ordered = sort_records(records, rules, _value)
        self.assertEqual(
            [(item.values["Type Mark"], item.values["Type Name"]) for item in ordered],
            [("W2", "Block"), ("W2", "Stud"), ("W10", "Stud")],
        )

    def test_descending_numeric_width(self):
        records = [
            _Record(1, {"Width": 0.5}),
            _Record(2, {"Width": 1.5}),
            _Record(3, {"Width": 0.5}),
        ]
        rules = [{"parameter": "Width", "direction": "descending", "natural_sort": False}]
        ordered = sort_records(records, rules, _value)
        self.assertEqual([item.type_id for item in ordered], [2, 1, 3])


if __name__ == "__main__":
    unittest.main()
