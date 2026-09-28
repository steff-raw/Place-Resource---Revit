# -*- coding: utf-8 -*-
"""Legend library settings, Type Mark matching and row stacking.

The library lives in Revit as symbol families: one Generic Annotation family
per category (e.g. "PR Legend - Walls"), one type per code, type name = Type Mark
(e.g. IWS-105). Each type carries the graphic and the description. This module
is pure Python; Revit reading is in symbol_library.py.
"""

import copy
import json
import os
from collections import OrderedDict

from errors import ConfigurationError

SUPPORTED_SCHEMA = "2.0"

DEFAULTS = {
    "family_name": "PR Legend - {category}",
    "description_parameter": "Description",
    "template_legend_name": "_TEMPLATE - LIBRARY LEGEND",
    "output_name_pattern": "{category} LEGEND",
    "sheet_output_name_pattern": "{category} LEGEND - {sheet_number}",
    "scale": 100,
    "source_view_types": ["FloorPlan", "CeilingPlan", "Section", "Elevation"],
    "styles": {
        "heading_text_type": "2.5mm Arial Bold",
        "show_heading": True,
    },
    "layout": {
        "row_gap_mm": 3,
        "heading_gap_mm": 5,
    },
    "sheet_placement": {
        "mode": "pick_point",
        "anchor_x_mm": 20,
        "anchor_y_mm": 20,
        "prevent_duplicate_on_same_sheet": True,
    },
}


class LibraryEntry(object):
    """One legend row: a type of the category's symbol family."""

    def __init__(self, code, description="", symbol_id=None, symbol_unique_id=None):
        self.code = code
        self.description = description or ""
        self.symbol_id = symbol_id
        self.symbol_unique_id = symbol_unique_id

    def label(self):
        """Text shown in selection lists."""
        if self.description:
            return "{0}  —  {1}".format(self.code, self.description)
        return self.code

    def as_hash_record(self):
        return [self.code, self.symbol_unique_id or ""]


def default_settings_path():
    """Return config/library_legends.json next to lib."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "config", "library_legends.json")


def load_library_settings(path=None):
    """Load library_legends.json. Returns {"path", "categories": OrderedDict name -> config}."""
    settings_path = path or default_settings_path()
    categories = validate_settings(_read_json(settings_path), settings_path)
    return {"path": settings_path, "categories": categories}


def category_names(path=None):
    """Category names from library_legends.json."""
    return list(load_library_settings(path)["categories"].keys())


def validate_settings(data, label="library_legends.json"):
    """Validate the settings and return an ordered mapping of category name to merged config."""
    if not isinstance(data, dict):
        raise ConfigurationError("{0} must contain a JSON object.".format(label))
    version = data.get("schema_version")
    if version != SUPPORTED_SCHEMA:
        hint = ""
        if version == "1.0":
            hint = (" Version 1.0 used the Excel library, which was replaced by symbol families. "
                    "Replace the file with the library_legends.json shipped with the tool.")
        raise ConfigurationError(
            "{0} schema_version '{1}' is not supported. This build reads {2}.{3}".format(
                label, version, SUPPORTED_SCHEMA, hint
            )
        )
    defaults = _merge(DEFAULTS, data.get("defaults") or {})
    items = data.get("categories")
    if not isinstance(items, list) or not items:
        raise ConfigurationError("{0} must contain a non-empty categories list.".format(label))
    categories = OrderedDict()
    for index, item in enumerate(items):
        prefix = "{0} categories[{1}]".format(label, index)
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ConfigurationError("{0} needs a name.".format(prefix))
        name = item["name"].strip()
        if name in categories:
            raise ConfigurationError("{0}: category '{1}' is listed twice.".format(prefix, name))
        merged = _merge(defaults, item)
        merged["name"] = name
        revit_category = merged.get("revit_category")
        if revit_category is not None and (not isinstance(revit_category, str) or not revit_category.startswith("OST_")):
            raise ConfigurationError(
                "{0}: revit_category must be null or a built-in category such as OST_Walls.".format(prefix)
            )
        _validate_category(merged, prefix)
        merged["family_name"] = merged["family_name"].replace("{category}", name).strip()
        categories[name] = merged
    return categories


def entries_for_codes(entries, codes):
    """Return entries whose code is in ``codes``, in library order. Matching ignores case."""
    wanted = set(normalize_code(code) for code in codes or [])
    return [entry for entry in entries if normalize_code(entry.code) in wanted]


def missing_codes(entries, codes):
    """Return codes that are not in the library, in the order given."""
    known = set(normalize_code(entry.code) for entry in entries)
    return [code for code in codes or [] if normalize_code(code) not in known]


def match_type_marks(entries, type_marks):
    """Return library codes whose Code equals one of ``type_marks`` (case-insensitive)."""
    marks = set(normalize_code(mark) for mark in type_marks or [] if mark)
    return [entry.code for entry in entries if normalize_code(entry.code) in marks]


def normalize_code(value):
    return (value or "").strip().lower()


def apply_pattern(pattern, category, sheet=None):
    """Fill {category}, {sheet_number} and {sheet_name} in a name pattern."""
    from configuration import apply_name_pattern
    return apply_name_pattern(pattern, {
        "category": category,
        "sheet_number": getattr(sheet, "SheetNumber", "") if sheet is not None else "",
        "sheet_name": getattr(sheet, "Name", "") if sheet is not None else "",
    })


def stack_rows(heights, row_gap, heading_height=None, heading_gap=0.0):
    """Top y of each row when rows are stacked downward from y = 0 (y grows up).

    A heading, when given, takes the top slot and is followed by ``heading_gap``.
    Returns (row_tops, bottom).
    """
    y = 0.0
    if heading_height is not None:
        y = -(float(heading_height) + float(heading_gap))
    tops = []
    for index, height in enumerate(heights):
        tops.append(y)
        y -= float(height)
        if index < len(heights) - 1:
            y -= float(row_gap)
    return tops, y


def _merge(base, override):
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _validate_category(config, prefix):
    for key in ("family_name", "description_parameter", "template_legend_name",
                "output_name_pattern", "sheet_output_name_pattern"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ConfigurationError("{0}: {1} must be a non-empty string.".format(prefix, key))
    scale = config.get("scale")
    if isinstance(scale, bool) or not isinstance(scale, int) or scale <= 0:
        raise ConfigurationError("{0}: scale must be a positive whole number such as 100.".format(prefix))
    view_types = config.get("source_view_types")
    if not isinstance(view_types, list) or not view_types or any(not isinstance(item, str) for item in view_types):
        raise ConfigurationError("{0}: source_view_types must be a non-empty list of view type names.".format(prefix))
    styles = config.get("styles") or {}
    if not isinstance(styles.get("heading_text_type"), str) or not styles["heading_text_type"].strip():
        raise ConfigurationError("{0}: styles.heading_text_type must name a text note type.".format(prefix))
    if not isinstance(styles.get("show_heading"), bool):
        raise ConfigurationError("{0}: styles.show_heading must be true or false.".format(prefix))
    layout = config.get("layout") or {}
    for key in ("row_gap_mm", "heading_gap_mm"):
        value = layout.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ConfigurationError("{0}: layout.{1} must be a number of millimetres, 0 or more.".format(prefix, key))
    placement = config.get("sheet_placement") or {}
    if placement.get("mode") not in ("pick_point", "configured_point"):
        raise ConfigurationError("{0}: sheet_placement.mode must be pick_point or configured_point.".format(prefix))


def _read_json(path):
    if not os.path.isfile(path):
        raise ConfigurationError("Cannot find the library settings file {0}.".format(path))
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except ValueError as ex:
        raise ConfigurationError("{0} is not valid JSON. {1}".format(path, ex))
