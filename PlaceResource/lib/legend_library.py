# -*- coding: utf-8 -*-
"""Legend library: settings, Excel rows, Type Mark matching and row layout.

Pure Python. Nothing here calls Revit, so it is covered by unit tests.

The library is one Excel workbook with a sheet per category. Columns (header
row, any order, case-insensitive):

    Code | Title | Description | Graphic | Filled Region Type | Notes

- Code is required and unique per sheet (e.g. IWS-105).
- Title defaults to Code.
- Graphic is Region (default) or Component.
- Filled Region Type is required for Region rows. It names a Filled Region Type in the model.
- Notes and any other columns are ignored.
"""

import copy
import json
import os
from collections import OrderedDict

from errors import ConfigurationError

SUPPORTED_SCHEMA = "1.0"
GRAPHIC_REGION = "region"
GRAPHIC_COMPONENT = "component"
GRAPHIC_MASTER = "master"
SOURCE_EXCEL = "excel"
SOURCE_MASTER = "revit"

_HEADER_ALIASES = {
    "code": ("code", "type mark", "mark"),
    "title": ("title", "name"),
    "description": ("description", "desc"),
    "graphic": ("graphic", "graphic type", "representation"),
    "region_type": ("filled region type", "region type", "hatch", "filled region"),
}

DEFAULTS = {
    "template_legend_name": "_TEMPLATE - LIBRARY LEGEND",
    "output_name_pattern": "{category} LEGEND",
    "sheet_output_name_pattern": "{category} LEGEND - {sheet_number}",
    "scale": 100,
    "source_view_types": ["FloorPlan", "CeilingPlan", "Section", "Elevation"],
    "styles": {
        "title_text_type": "2.5mm Arial Bold",
        "description_text_type": "2.5mm Arial",
        "heading_text_type": "2.5mm Arial Bold",
        "show_heading": True,
    },
    "layout": {
        "swatch_width_mm": 15,
        "swatch_height_mm": 8,
        "title_width_mm": 25,
        "description_width_mm": 70,
        "column_gap_mm": 4,
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

_LAYOUT_KEYS = tuple(DEFAULTS["layout"].keys())
_STYLE_TEXT_KEYS = ("title_text_type", "description_text_type", "heading_text_type")


class LibraryEntry(object):
    """One row of the legend library."""

    def __init__(self, code, title, description, graphic, region_type, row_number):
        self.code = code
        self.title = title or code
        self.description = description
        self.graphic = graphic
        self.region_type = region_type
        self.row_number = row_number
        # Master legend rows only: where the row lives in the Revit master legend.
        self.source = SOURCE_EXCEL
        self.element_ids = []
        self.box = None
        self.fingerprint = ""

    def label(self):
        """Text shown in selection lists."""
        text = self.title if self.title == self.code else "{0}  {1}".format(self.code, self.title)
        if self.description:
            text = "{0}  —  {1}".format(text, self.description)
        return text

    def as_hash_record(self):
        return [self.code, self.title, self.description, self.graphic, self.region_type, self.fingerprint]


def master_entry(row, index):
    """Build a LibraryEntry from a rows_from_items row."""
    entry = LibraryEntry(row["code"], "", row["description"], GRAPHIC_MASTER, "", index)
    entry.source = SOURCE_MASTER
    entry.element_ids = list(row["element_ids"])
    entry.box = dict(row["box"])
    entry.fingerprint = row["fingerprint"]
    return entry


def rows_from_items(items, tolerance):
    """Find legend rows in a master legend.

    ``items``: every element of the master legend as
    {"id", "is_text", "text", "left", "right", "top", "bottom"} in model units (y up).

    Rules:
    - The Type Mark column is the text notes whose left edge is within ``tolerance``
      of the left-most text note. Each of those texts is one row's Code.
    - Rows are horizontal bands around each Code, split halfway between neighbouring Codes.
      The first and last bands reach half a row pitch beyond their Code.
    - Every other element whose centre is in a band, and that is not left of the Code, joins the row.
    - A row with no graphic (only text) is a heading and is skipped.
    - The Code text itself is not part of the row.

    Returns (rows, notes). Each row: {"code", "description", "element_ids", "box", "fingerprint"}.
    """
    notes = []
    texts = [item for item in items if item.get("is_text") and (item.get("text") or "").strip()]
    if not texts:
        return [], ["The master legend has no text notes. Put the Type Mark text at the left of each row."]
    min_left = min(item["left"] for item in texts)
    marks = [item for item in texts if item["left"] <= min_left + tolerance]
    marks.sort(key=lambda item: -_centre_y(item))
    centres = [_centre_y(mark) for mark in marks]
    bands = []
    for index, centre in enumerate(centres):
        if len(centres) == 1:
            bands.append((None, None))
            continue
        if index == 0:
            upper = centre + (centre - centres[1]) / 2.0
        else:
            upper = (centres[index - 1] + centre) / 2.0
        if index == len(centres) - 1:
            lower = centre - (centres[index - 1] - centre) / 2.0
        else:
            lower = (centre + centres[index + 1]) / 2.0
        bands.append((upper, lower))

    mark_ids = set(mark["id"] for mark in marks)
    members = [[] for _ in marks]
    for item in items:
        if item["id"] in mark_ids:
            continue
        centre = _centre_y(item)
        for index, (upper, lower) in enumerate(bands):
            if upper is not None and centre > upper:
                continue
            if lower is not None and centre <= lower:
                continue
            if item["left"] < marks[index]["left"] - tolerance:
                break
            members[index].append(item)
            break

    rows = []
    seen = {}
    for index, mark in enumerate(marks):
        code = (mark.get("text") or "").strip().splitlines()[0].strip()
        row_items = sorted(members[index], key=lambda item: (item["left"], -item["top"]))
        graphics = [item for item in row_items if not item.get("is_text")]
        if not graphics:
            notes.append("'{0}' has no graphic on its row, so it was treated as a heading.".format(code))
            continue
        key = normalize_code(code)
        if key in seen:
            notes.append("Code '{0}' appears twice in the master legend. The upper row was used.".format(code))
            continue
        seen[key] = True
        description = " ".join(
            " ".join((item.get("text") or "").split()) for item in row_items if item.get("is_text")
        ).strip()
        box = {
            "left": min(item["left"] for item in row_items),
            "right": max(item["right"] for item in row_items),
            "top": max(item["top"] for item in row_items),
            "bottom": min(item["bottom"] for item in row_items),
        }
        fingerprint = "|".join(
            "{0}:{1}:{2:.3f}:{3:.3f}:{4:.3f}:{5:.3f}".format(
                item["id"], (item.get("text") or "").strip(),
                item["left"] - box["left"], item["top"] - box["top"],
                item["right"] - item["left"], item["top"] - item["bottom"],
            )
            for item in row_items
        )
        rows.append({
            "code": code,
            "description": description,
            "element_ids": [item["id"] for item in row_items],
            "box": box,
            "fingerprint": fingerprint,
        })
    return rows, notes


def _centre_y(item):
    return (item["top"] + item["bottom"]) / 2.0


def default_settings_path():
    """Return config/library_legends.json next to lib."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "config", "library_legends.json")


def load_library_settings(path=None, read_workbook=None):
    """Load library_legends.json and the Excel library it names.

    Returns {"path", "library_path", "categories": OrderedDict name -> config,
    "library": {name: [LibraryEntry]}, "warnings": [...]}.
    ``read_workbook`` is injectable for tests; it defaults to xlsx_reader.read_workbook.
    """
    settings_path = path or default_settings_path()
    data = _read_json(settings_path)
    categories = validate_settings(data, settings_path)
    library_path = data["library_file"]
    if not os.path.isabs(library_path):
        library_path = os.path.join(os.path.dirname(settings_path), library_path)
    if read_workbook is None:
        from xlsx_reader import read_workbook
    library_error = None
    try:
        workbook = read_workbook(library_path)
        library, warnings = parse_library(workbook, list(categories.keys()))
    except ConfigurationError as ex:
        # Master legends in the model still work when the Excel library cannot be read.
        library_error = str(ex)
        library = OrderedDict((name, []) for name in categories)
        warnings = [library_error]
    return {
        "path": settings_path,
        "library_path": library_path,
        "categories": categories,
        "library": library,
        "library_error": library_error,
        "warnings": warnings,
    }


def category_names(path=None):
    """Category names from library_legends.json, without reading the Excel workbook."""
    settings_path = path or default_settings_path()
    return list(validate_settings(_read_json(settings_path), settings_path).keys())


def validate_settings(data, label="library_legends.json"):
    """Validate the settings and return an ordered mapping of category name to merged config."""
    if not isinstance(data, dict):
        raise ConfigurationError("{0} must contain a JSON object.".format(label))
    if data.get("schema_version") != SUPPORTED_SCHEMA:
        raise ConfigurationError(
            "{0} schema_version '{1}' is not supported. This build reads {2}.".format(
                label, data.get("schema_version"), SUPPORTED_SCHEMA
            )
        )
    if not isinstance(data.get("library_file"), str) or not data["library_file"].strip():
        raise ConfigurationError("{0} must set library_file to the .xlsx library workbook.".format(label))
    if not data["library_file"].lower().endswith(".xlsx"):
        raise ConfigurationError("{0} library_file must be an .xlsx workbook.".format(label))
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
        categories[name] = merged
    return categories


def parse_library(workbook, category_names):
    """Parse workbook sheets for the configured categories.

    Returns ({category: [LibraryEntry]}, warnings). Raises ConfigurationError listing every row problem.
    A configured category without a sheet gets an empty list and a warning.
    """
    from xlsx_reader import sheet_records
    library = OrderedDict()
    warnings = []
    problems = []
    lowered = {name.strip().lower(): name for name in workbook.keys()}
    for category in category_names:
        sheet_name = lowered.get(category.strip().lower())
        if sheet_name is None:
            library[category] = []
            warnings.append("The library workbook has no sheet named '{0}'.".format(category))
            continue
        entries, sheet_problems = parse_sheet(category, sheet_records(workbook[sheet_name]))
        library[category] = entries
        problems.extend(sheet_problems)
    if problems:
        raise ConfigurationError(
            "The legend library has {0} problem(s). Fix them in Excel and save:\n- {1}".format(
                len(problems), "\n- ".join(problems)
            )
        )
    return library, warnings


def parse_sheet(category, records):
    """Return (entries, problems) for one sheet's records."""
    entries = []
    problems = []
    seen = {}
    for record in records:
        row = record.get("__row__")
        code = _field(record, "code")
        if not code:
            if any(value for key, value in record.items() if key != "__row__"):
                problems.append("{0} row {1}: Code is empty.".format(category, row))
            continue
        graphic_text = (_field(record, "graphic") or GRAPHIC_REGION).strip().lower()
        if graphic_text not in (GRAPHIC_REGION, GRAPHIC_COMPONENT):
            problems.append("{0} row {1} ({2}): Graphic must be Region or Component, not '{3}'.".format(
                category, row, code, _field(record, "graphic")
            ))
            continue
        region_type = _field(record, "region_type")
        if graphic_text == GRAPHIC_REGION and not region_type:
            problems.append("{0} row {1} ({2}): Filled Region Type is empty for a Region row.".format(
                category, row, code
            ))
            continue
        key = code.strip().lower()
        if key in seen:
            problems.append("{0} row {1}: Code '{2}' is already used on row {3}.".format(
                category, row, code, seen[key]
            ))
            continue
        seen[key] = row
        entries.append(LibraryEntry(
            code=code,
            title=_field(record, "title"),
            description=_field(record, "description"),
            graphic=graphic_text,
            region_type=region_type,
            row_number=row,
        ))
    return entries, problems


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


def layout_rows(row_sizes, layout_model, heading_size=None):
    """Compute top-left positions for a library legend.

    ``row_sizes``: list of {"graphic": (w, h), "title": (w, h), "description": (w, h)} in model units.
    ``layout_model``: the layout block already converted to model units, keys
    swatch_width, swatch_height, title_width, description_width, column_gap, row_gap, heading_gap.
    ``heading_size``: (w, h) of the category heading, or None when no heading is shown.

    Returns {"heading": (x, y) or None, "rows": [{"graphic", "title", "description": (x, y), "height"}],
    "block": {"left", "top", "right", "bottom"}}. The origin is the top-left corner at (0, 0); y grows up.
    """
    graphic_width = layout_model["swatch_width"]
    title_width = layout_model["title_width"]
    description_width = layout_model["description_width"]
    for size in row_sizes:
        graphic_width = max(graphic_width, size["graphic"][0])
        title_width = max(title_width, size["title"][0])
        description_width = max(description_width, size["description"][0])
    title_x = graphic_width + layout_model["column_gap"]
    description_x = title_x + title_width + layout_model["column_gap"]
    right = description_x + description_width

    y = 0.0
    heading = None
    if heading_size is not None:
        heading = (0.0, 0.0)
        right = max(right, heading_size[0])
        y = -(heading_size[1] + layout_model["heading_gap"])

    rows = []
    for index, size in enumerate(row_sizes):
        height = max(size["graphic"][1], size["title"][1], size["description"][1], layout_model["swatch_height"])
        rows.append({
            "graphic": (0.0, y),
            "title": (title_x, y),
            "description": (description_x, y),
            "height": height,
        })
        y -= height
        if index < len(row_sizes) - 1:
            y -= layout_model["row_gap"]
    return {
        "heading": heading,
        "rows": rows,
        "block": {"left": 0.0, "top": 0.0, "right": right, "bottom": y},
    }


def layout_to_model(layout_mm, scale, mm_to_internal):
    """Convert the paper-mm layout block to model units at the legend scale."""
    factor = float(scale)
    return {
        "swatch_width": mm_to_internal(layout_mm["swatch_width_mm"]) * factor,
        "swatch_height": mm_to_internal(layout_mm["swatch_height_mm"]) * factor,
        "title_width": mm_to_internal(layout_mm["title_width_mm"]) * factor,
        "description_width": mm_to_internal(layout_mm["description_width_mm"]) * factor,
        "column_gap": mm_to_internal(layout_mm["column_gap_mm"]) * factor,
        "row_gap": mm_to_internal(layout_mm["row_gap_mm"]) * factor,
        "heading_gap": mm_to_internal(layout_mm["heading_gap_mm"]) * factor,
    }


def _field(record, name):
    for alias in _HEADER_ALIASES[name]:
        value = record.get(alias)
        if value:
            return value.strip()
    return ""


def _merge(base, override):
    merged = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _validate_category(config, prefix):
    for key in ("template_legend_name", "output_name_pattern", "sheet_output_name_pattern"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ConfigurationError("{0}: {1} must be a non-empty string.".format(prefix, key))
    scale = config.get("scale")
    if isinstance(scale, bool) or not isinstance(scale, int) or scale <= 0:
        raise ConfigurationError("{0}: scale must be a positive whole number such as 100.".format(prefix))
    view_types = config.get("source_view_types")
    if not isinstance(view_types, list) or not view_types or any(not isinstance(item, str) for item in view_types):
        raise ConfigurationError("{0}: source_view_types must be a non-empty list of view type names.".format(prefix))
    styles = config.get("styles") or {}
    for key in _STYLE_TEXT_KEYS:
        if not isinstance(styles.get(key), str) or not styles[key].strip():
            raise ConfigurationError("{0}: styles.{1} must name a text note type.".format(prefix, key))
    if not isinstance(styles.get("show_heading"), bool):
        raise ConfigurationError("{0}: styles.show_heading must be true or false.".format(prefix))
    layout = config.get("layout") or {}
    for key in _LAYOUT_KEYS:
        value = layout.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ConfigurationError("{0}: layout.{1} must be a number of millimetres, 0 or more.".format(prefix, key))
    for key in ("swatch_width_mm", "swatch_height_mm"):
        if layout[key] <= 0:
            raise ConfigurationError("{0}: layout.{1} must be greater than zero.".format(prefix, key))
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
