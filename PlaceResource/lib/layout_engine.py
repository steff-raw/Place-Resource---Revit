# -*- coding: utf-8 -*-
"""Deterministic legend layout.

All coordinates are Revit internal units (decimal feet). Y increases upward.
The origin is the configured corner of the finished block. This module does
not call the Revit API.
"""

import math
import re

from units import mm_to_internal

ALIGNMENTS = ("top_left", "top_right", "bottom_left", "bottom_right")
OVERLAP_TOLERANCE_MM = 0.5


def natural_sort_key(value):
    """Sort key that orders W2 before W10 and ignores letter case."""
    text = "" if value is None else str(value).strip()
    parts = re.split(r"(\d+)", text)
    key = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.casefold()))
    return tuple(key)


def _value_key(raw_value, natural_sort):
    if isinstance(raw_value, bool) or raw_value is None:
        return natural_sort_key("" if raw_value is None else str(raw_value))
    if isinstance(raw_value, (int, float)):
        return ((0, float(raw_value)),)
    if natural_sort:
        return natural_sort_key(raw_value)
    return natural_sort_key(raw_value)


def sort_records(records, rules, value_getter):
    """Stable multi-key sort. The last rule is the tie break after type id."""
    ordered = list(records)
    ordered.sort(key=lambda record: int(value_getter(record, "__type_id__") or 0))
    for rule in reversed(list(rules or [])):
        natural = bool(rule.get("natural_sort", False))
        descending = str(rule.get("direction", "ascending")).lower() == "descending"
        parameter = rule.get("parameter")

        def _key(record, parameter_name=parameter, use_natural=natural):
            return _value_key(value_getter(record, parameter_name), use_natural)

        ordered.sort(key=_key, reverse=descending)
    return ordered


def layout_config_to_internal(layout):
    """Copy a layout definition with millimetre lengths converted to feet."""
    converted = dict(layout)
    for key, value in list(layout.items()):
        if key.endswith("_mm"):
            converted[key[:-3] + "_internal"] = mm_to_internal(value)
    return converted


def estimate_measurements(entries, labels, layout_internal):
    """Build measurement dictionaries from configuration, before Revit creates elements."""
    row_height = layout_internal["row_height_internal"]
    text_height = min(row_height, mm_to_internal(3.5))
    graphic_width = layout_internal["graphic_width_internal"]
    estimated = []
    for entry in entries:
        estimated.append({
            "key": entry["key"],
            "component": {"width": graphic_width, "height": row_height},
            "labels": [
                {
                    "parameter": label["parameter"],
                    "width": mm_to_internal(label["width_mm"]),
                    "height": text_height,
                }
                for label in labels
            ],
        })
    return estimated


def _size(measurement, fallback_width, fallback_height):
    if not measurement:
        return fallback_width, fallback_height
    width = measurement.get("width")
    height = measurement.get("height")
    if width is None:
        width = fallback_width
    if height is None:
        height = fallback_height
    return float(width), float(height)


def used_column_count(count, columns, direction):
    """Return how many columns a layout will actually occupy."""
    if count <= 0:
        return 0
    max_column = 0
    for index in range(count):
        _row, column = _column_row(index, count, columns, direction)
        if column > max_column:
            max_column = column
    return max_column + 1


def _column_row(index, count, columns, direction):
    columns = max(1, int(columns))
    if count <= 0:
        return 0, 0
    if direction == "horizontal":
        return index // columns, index % columns
    rows_per_column = int(math.ceil(count / float(columns)))
    if rows_per_column <= 0:
        return 0, 0
    return index % rows_per_column, index // rows_per_column


def _boxes_overlap(left, right, tolerance):
    separated = (
        left["right"] <= right["left"] + tolerance
        or right["right"] <= left["left"] + tolerance
        or left["top"] <= right["bottom"] + tolerance
        or right["top"] <= left["bottom"] + tolerance
    )
    return not separated


def find_overlaps(boxes, tolerance_internal):
    """Return pairs of box ids whose rectangles overlap."""
    found = []
    ordered = list(boxes)
    for index, first in enumerate(ordered):
        for second in ordered[index + 1:]:
            if _boxes_overlap(first, second, tolerance_internal):
                found.append((first["id"], second["id"]))
    return found


def compute_layout(entries, labels, layout_internal, header_height=None, show_headers=True):
    """Return top-left positions for components, labels, and headings.

    ``entries`` is an ordered list of
    ``{"key", "component": {width, height}, "labels": [{"parameter", "width", "height"}]}``.
    Label widths in the measurements are minimums; configured widths are also
    minimums. The larger value is reserved so columns cannot overlap.
    """
    direction = layout_internal.get("direction", "vertical")
    columns = max(1, int(layout_internal.get("columns", 1)))
    auto_size = bool(layout_internal.get("auto_size_rows", True))
    graphic_width = float(layout_internal["graphic_width_internal"])
    label_gap = float(layout_internal["label_gap_internal"])
    column_gap = float(layout_internal["column_gap_internal"])
    min_row_height = float(layout_internal["row_height_internal"])
    heading_gap = float(layout_internal["heading_gap_internal"])
    warnings = []
    count = len(entries)
    if count == 0:
        return {
            "positions": {},
            "boxes": [],
            "overlaps": [],
            "warnings": [],
            "block": {"width": 0.0, "height": 0.0, "left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},
            "row_heights": [],
            "expanded_labels": [],
        }

    membership = []
    max_row = 0
    max_col = 0
    for index, entry in enumerate(entries):
        row, column = _column_row(index, count, columns, direction)
        membership.append((row, column))
        max_row = max(max_row, row)
        max_col = max(max_col, column)

    column_count = max_col + 1
    row_count = max_row + 1
    configured_label_widths = [mm_to_internal(label["width_mm"]) for label in labels]
    graphic_by_column = [graphic_width for _ in range(column_count)]
    label_widths = [list(configured_label_widths) for _ in range(column_count)]
    expanded_labels = []

    for entry, (row, column) in zip(entries, membership):
        component_width, _component_height = _size(entry.get("component"), graphic_width, min_row_height)
        if component_width > graphic_by_column[column]:
            graphic_by_column[column] = component_width
        measured_labels = {item["parameter"]: item for item in entry.get("labels", [])}
        for label_index, label in enumerate(labels):
            measured = measured_labels.get(label["parameter"])
            measured_width, _measured_height = _size(
                measured,
                configured_label_widths[label_index],
                min_row_height,
            )
            if measured_width > label_widths[column][label_index] + mm_to_internal(0.5):
                label_widths[column][label_index] = measured_width
                expanded_labels.append(label["parameter"])
                warnings.append(
                    "'{0}' is wider than its column, so the column was widened.".format(
                        label.get("heading") or label["parameter"]
                    )
                )

    row_heights = []
    for row in range(row_count):
        height = min_row_height
        if auto_size:
            for entry, (entry_row, _column) in zip(entries, membership):
                if entry_row != row:
                    continue
                _width, component_height = _size(entry.get("component"), graphic_width, min_row_height)
                height = max(height, component_height)
                for item in entry.get("labels", []):
                    _label_width, label_height = _size(item, 0.0, 0.0)
                    height = max(height, label_height)
        row_heights.append(height)

    if header_height is None:
        header_height = min(min_row_height, mm_to_internal(4.0))
    header_block = (float(header_height) + heading_gap) if show_headers else 0.0

    column_widths = []
    for column in range(column_count):
        width = graphic_by_column[column]
        if labels:
            width += label_gap + sum(label_widths[column])
        column_widths.append(width)

    block_width = sum(column_widths) + column_gap * max(0, column_count - 1)
    block_height = header_block + sum(row_heights)

    origin_x = float(layout_internal.get("origin_x_internal", layout_internal.get("origin_x", 0.0)))
    origin_y = float(layout_internal.get("origin_y_internal", layout_internal.get("origin_y", 0.0)))
    align = layout_internal.get("align", "top_left")
    if align == "top_left":
        left = origin_x
        top = origin_y
    elif align == "top_right":
        left = origin_x - block_width
        top = origin_y
    elif align == "bottom_left":
        left = origin_x
        top = origin_y + block_height
    elif align == "bottom_right":
        left = origin_x - block_width
        top = origin_y + block_height
    else:
        left = origin_x
        top = origin_y
        warnings.append("Alignment '{0}' is unknown. top_left was used.".format(align))

    column_left = []
    cursor = left
    for width in column_widths:
        column_left.append(cursor)
        cursor += width + column_gap

    row_top = []
    cursor_y = top - header_block
    for height in row_heights:
        row_top.append(cursor_y)
        cursor_y -= height

    positions = {}
    boxes = []

    def _add_box(box_id, box_left, box_top, box_width, box_height):
        box = {
            "id": box_id,
            "left": box_left,
            "top": box_top,
            "right": box_left + box_width,
            "bottom": box_top - box_height,
            "width": box_width,
            "height": box_height,
        }
        boxes.append(box)
        positions[box_id] = (box_left, box_top)
        return box

    if show_headers:
        for column in range(column_count):
            x_cursor = column_left[column] + graphic_by_column[column] + (label_gap if labels else 0.0)
            for label_index, label in enumerate(labels):
                box_id = "heading:{0}:{1}".format(label["parameter"], column)
                width = label_widths[column][label_index]
                _add_box(box_id, x_cursor, top, width, float(header_height))
                x_cursor += width

    for entry, (row, column) in zip(entries, membership):
        component_width, component_height = _size(entry.get("component"), graphic_width, row_heights[row])
        reserved_graphic = graphic_by_column[column]
        component_left = column_left[column]
        component_top = row_top[row]
        _add_box(
            "component:{0}".format(entry["key"]),
            component_left,
            component_top,
            min(component_width, reserved_graphic),
            min(component_height, row_heights[row]),
        )
        x_cursor = column_left[column] + reserved_graphic + (label_gap if labels else 0.0)
        measured_labels = {item["parameter"]: item for item in entry.get("labels", [])}
        for label_index, label in enumerate(labels):
            measured = measured_labels.get(label["parameter"])
            _measured_width, measured_height = _size(measured, label_widths[column][label_index], row_heights[row])
            box_id = "label:{0}:{1}".format(entry["key"], label["parameter"])
            _add_box(
                box_id,
                x_cursor,
                row_top[row],
                label_widths[column][label_index],
                min(measured_height, row_heights[row]),
            )
            x_cursor += label_widths[column][label_index]

    tolerance = mm_to_internal(OVERLAP_TOLERANCE_MM)
    overlaps = find_overlaps(boxes, tolerance)
    for first_id, second_id in overlaps:
        warnings.append(
            "'{0}' and '{1}' overlap. Increase the row height or column width.".format(
                first_id, second_id
            )
        )

    return {
        "positions": positions,
        "boxes": boxes,
        "overlaps": overlaps,
        "warnings": warnings,
        "block": {
            "width": block_width,
            "height": block_height,
            "left": left,
            "top": top,
            "right": left + block_width,
            "bottom": top - block_height,
        },
        "row_heights": row_heights,
        "expanded_labels": sorted(set(expanded_labels)),
        "column_widths": column_widths,
    }
