# -*- coding: utf-8 -*-
"""Legend library settings, Type Mark matching and row stacking.

The library lives in Revit as symbol families: one family per category, one type
per Type Mark (e.g. IWS-105). The family draws the graphic. The description comes
from a type parameter and the tool writes it as wrapped text. Pure Python;
Revit reading is in symbol_library.py.
"""

import copy
import json
import os
from collections import OrderedDict

from errors import ConfigurationError

SUPPORTED_SCHEMA = "2.0"

DEFAULTS = {
    "family_name": "PR Legend - {category}",
    "description_parameter": "Legend_Description",
    "type_mark_visibility_parameter": "Legend_TypeMark_Visibility",
    "text_visibility_parameter": "Text_Visibility",
    "show_type_mark": True,
    "template_legend_name": "_TEMPLATE - LIBRARY LEGEND",
    "output_name_pattern": "{category} LEGEND",
    "sheet_output_name_pattern": "{category} LEGEND - {sheet_number}",
    "scale": 100,
    "source_view_types": ["FloorPlan", "CeilingPlan", "Section", "Elevation"],
    "styles": {
        "heading_text_type": "2.5mm Arial Bold",
        "show_heading": True,
        "text_type": "2.5mm Arial",
        "show_text": True,
    },
    "layout": {
        "row_gap_mm": 3,
        "heading_gap_mm": 5,
        "text_gap_mm": 3,
        "width_mm": 120,
        "text_pattern": "{description}",
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
            return "{0} - {1}".format(self.code, self.description)
        return self.code

    def as_hash_record(self):
        return [self.code, self.symbol_unique_id or "", self.description]


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
            hint = (" Version 1.0 was for the old Excel library. Use the library_legends.json "
                    "that comes with the tool.")
        raise ConfigurationError(
            "{0}: schema_version '{1}' is not supported. This version reads {2}.{3}".format(
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


def with_families(library_settings, assignments):
    """Return a copy of the settings where each category uses the family picked for it in the model.

    Categories without a pick keep family_name from library_legends.json.
    """
    categories = OrderedDict()
    for name, config in library_settings["categories"].items():
        config = dict(config)
        family = (assignments or {}).get(name)
        if family:
            config["family_name"] = family
        categories[name] = config
    result = dict(library_settings)
    result["categories"] = categories
    return result


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


MIN_TEXT_WIDTH_MM = 15.0
MIN_WIDTH_CM = 2.0
MAX_WIDTH_CM = 100.0


def text_width_mm(total_mm, graphic_mm, gap_mm):
    """Width left for the text after the widest graphic and the gap, in paper millimetres.

    Raises ValueError when the legend is too narrow to fit readable text.
    """
    width = float(total_mm) - float(graphic_mm) - float(gap_mm)
    if width < MIN_TEXT_WIDTH_MM:
        raise ValueError(
            "The legend is {0:.0f} mm wide but the symbols take {1:.0f} mm. Make it at least "
            "{2:.0f} mm wide.".format(total_mm, graphic_mm, float(graphic_mm) + float(gap_mm) + MIN_TEXT_WIDTH_MM)
        )
    return width


def row_heights(graphic_heights, text_heights):
    """Each row is as tall as its graphic or its text, whichever is taller."""
    return [max(float(g or 0.0), float(t or 0.0)) for g, t in zip(graphic_heights, text_heights)]


def format_text(pattern, entry):
    """Fill {code} and {description} for one row. Returns stripped text, empty when there is nothing to show."""
    text = (pattern or "{description}").replace("{code}", entry.code or "").replace(
        "{description}", entry.description or ""
    )
    return text.strip()


def parse_width_cm(text):
    """Read a width typed in cm ("12", "12.5", "12,5", "12 cm"). Returns millimetres, or None when not valid."""
    value = (text or "").strip().lower().replace("cm", "").replace(",", ".").strip()
    try:
        number = float(value)
    except ValueError:
        return None
    if number < MIN_WIDTH_CM or number > MAX_WIDTH_CM:
        return None
    return number * 10.0


def _merge(base, override):
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _validate_category(config, prefix):
    for key in ("family_name", "description_parameter", "type_mark_visibility_parameter",
                "text_visibility_parameter", "template_legend_name",
                "output_name_pattern", "sheet_output_name_pattern"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ConfigurationError("{0}: {1} must be a non-empty string.".format(prefix, key))
    if not isinstance(config.get("show_type_mark"), bool):
        raise ConfigurationError("{0}: show_type_mark must be true or false.".format(prefix))
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
    if not isinstance(styles.get("text_type"), str) or not styles["text_type"].strip():
        raise ConfigurationError("{0}: styles.text_type must name a text note type.".format(prefix))
    if not isinstance(styles.get("show_text"), bool):
        raise ConfigurationError("{0}: styles.show_text must be true or false.".format(prefix))
    layout = config.get("layout") or {}
    for key in ("row_gap_mm", "heading_gap_mm", "text_gap_mm"):
        value = layout.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ConfigurationError("{0}: layout.{1} must be a number of millimetres, 0 or more.".format(prefix, key))
    width = layout.get("width_mm")
    if isinstance(width, bool) or not isinstance(width, (int, float)) or not 20 <= width <= 1000:
        raise ConfigurationError("{0}: layout.width_mm must be between 20 and 1000.".format(prefix))
    if not isinstance(layout.get("text_pattern"), str):
        raise ConfigurationError("{0}: layout.text_pattern must be text such as {{description}}.".format(prefix))
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
