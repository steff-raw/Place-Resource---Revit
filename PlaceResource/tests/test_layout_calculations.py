# -*- coding: utf-8 -*-
"""Layout positions, alignment, and overlap checks."""

import os
import sys
import unittest

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

from layout_engine import compute_layout, find_overlaps, layout_config_to_internal
from units import mm_to_internal


def _layout():
    raw = {
        "direction": "vertical",
        "columns": 1,
        "origin_x_mm": 0,
        "origin_y_mm": 0,
        "row_height_mm": 304.8,
        "column_gap_mm": 304.8,
        "graphic_width_mm": 304.8,
        "label_gap_mm": 0,
        "heading_gap_mm": 304.8,
        "align": "top_left",
        "auto_size_rows": True,
    }
    return layout_config_to_internal(raw)


def _labels():
    return [{"parameter": "Type Mark", "heading": "Type", "width_mm": 304.8}]


def _entry(key, component_height=1.0, label_height=0.5):
    return {
        "key": key,
        "component": {"width": 1.0, "height": component_height},
        "labels": [{"parameter": "Type Mark", "width": 1.0, "height": label_height}],
    }


class LayoutTests(unittest.TestCase):
    def test_millimetre_conversion_matches_internal_feet(self):
        self.assertAlmostEqual(mm_to_internal(304.8), 1.0)
        self.assertAlmostEqual(layout_config_to_internal({"row_height_mm": 304.8})["row_height_internal"], 1.0)

    def test_single_column_top_left(self):
        layout = compute_layout([_entry("1"), _entry("2")], _labels(), _layout(), header_height=1.0, show_headers=True)
        self.assertEqual(layout["positions"]["heading:Type Mark:0"], (1.0, 0.0))
        self.assertEqual(layout["positions"]["component:1"], (0.0, -2.0))
        self.assertEqual(layout["positions"]["label:1:Type Mark"], (1.0, -2.0))
        self.assertEqual(layout["positions"]["component:2"], (0.0, -3.0))
        self.assertEqual(layout["overlaps"], [])

    def test_tall_text_expands_the_row(self):
        layout = compute_layout(
            [_entry("1", component_height=1.0, label_height=2.5)],
            _labels(),
            _layout(),
            header_height=1.0,
            show_headers=False,
        )
        self.assertAlmostEqual(layout["row_heights"][0], 2.5)
        self.assertEqual(layout["positions"]["component:1"], (0.0, 0.0))

    def test_vertical_columns_fill_down_then_across(self):
        raw = _layout()
        raw["columns"] = 2
        entries = [_entry(str(index)) for index in range(1, 4)]
        layout = compute_layout(entries, _labels(), raw, header_height=0.0, show_headers=False)
        self.assertEqual(layout["positions"]["component:1"][0], layout["positions"]["component:2"][0])
        self.assertGreater(layout["positions"]["component:3"][0], layout["positions"]["component:1"][0])
        self.assertAlmostEqual(
            layout["positions"]["component:3"][0] - layout["positions"]["component:1"][0],
            3.0,
        )

    def test_bottom_right_origin(self):
        raw = _layout()
        raw["align"] = "bottom_right"
        raw["origin_x_internal"] = 10.0
        raw["origin_y_internal"] = 0.0
        layout = compute_layout([_entry("1")], _labels(), raw, header_height=1.0, show_headers=True)
        self.assertAlmostEqual(layout["block"]["right"], 10.0)
        self.assertAlmostEqual(layout["block"]["bottom"], 0.0)

    def test_overlap_detector_ignores_touching_edges(self):
        boxes = [
            {"id": "a", "left": 0, "right": 1, "bottom": 0, "top": 1},
            {"id": "b", "left": 1, "right": 2, "bottom": 0, "top": 1},
        ]
        self.assertEqual(find_overlaps(boxes, 0.001), [])
        boxes[1]["left"] = 0.5
        self.assertEqual(len(find_overlaps(boxes, 0.001)), 1)


if __name__ == "__main__":
    unittest.main()
