# -*- coding: utf-8 -*-
"""Load and validate the legend settings files.

Office values stay in JSON. This module checks the file and fills only
documented behaviour defaults for optional keys.
"""

import json
import os

from errors import ConfigurationError

SUPPORTED_SCHEMA = "1.0"
TOOL_NAME = "view_legend_creator"

REQUIRED_INCLUDE = (
    "basic_walls",
    "curtain_walls",
    "stacked_walls",
    "in_place_walls",
    "linked_models",
)
REQUIRED_GENERIC_INCLUDE = ("linked_models",)
WALL_ONLY_INCLUDE = (
    "basic_walls",
    "curtain_walls",
    "stacked_walls",
    "in_place_walls",
    "stacked_wall_members",
    "when_parts_replace_original",
)
OPTIONAL_INCLUDE = ("demolished", "in_place", "stacked_wall_members", "when_parts_replace_original")
REQUIRED_LAYOUT = (
    "direction",
    "columns",
    "origin_x_mm",
    "origin_y_mm",
    "row_height_mm",
    "column_gap_mm",
    "graphic_width_mm",
    "label_gap_mm",
    "heading_gap_mm",
    "align",
    "auto_size_rows",
)
REQUIRED_UPDATE = (
    "remove_unused_entries",
    "preserve_manual_notes",
    "preserve_viewport_position",
    "confirm_before_deleting",
)
REQUIRED_STYLES = (
    "text_note_type",
    "header_text_note_type",
    "line_style",
    "show_border",
    "show_headers",
)
REQUIRED_REPRESENTATION = (
    "view_direction",
    "host_length_mm",
    "detail_level",
    "scale",
)
VIEW_DIRECTIONS = (
    "Section",
    "FloorPlan",
    "ElevationFront",
    "ElevationBack",
    "ElevationLeft",
    "ElevationRight",
)
DETAIL_LEVELS = ("Coarse", "Medium", "Fine")
ALIGNMENTS = ("top_left", "top_right", "bottom_left", "bottom_right")

WALL_INCLUDE_DEFAULTS = {
    "demolished": False,
    "stacked_wall_members": False,
    "when_parts_replace_original": False,
}
GENERIC_INCLUDE_DEFAULTS = {
    "demolished": False,
    "in_place": False,
}

BEHAVIOUR_DEFAULTS = {
    "type_rules": {
        "missing_required_parameter": "warn",
        "unused_loaded_types": "exclude",
        "unmapped_parameter": "warn_and_blank",
        "duplicate_sort_key": "keep_all",
        "linked_type_match": "family_and_type_name",
        "unmapped_linked_type": "warn_and_skip",
        "blank_label": "–",
    },
    "sheet_placement": {
        "mode": "pick_point",
        "anchor_x_mm": 20,
        "anchor_y_mm": 20,
        "prevent_duplicate_on_same_sheet": True,
    },
    "representation": {
        "layer_reference_planes": False,
        "fallback_detail_lines": False,
    },
    "update": {
        "full_rebuild": False,
        "create_when_empty": False,
        "sync_legend_name": False,
        "reset_representation": False,
    },
}


def extension_root():
    """Return the PlaceResource folder that contains lib and config."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_settings_path():
    """Return the settings file shipped with the extension."""
    return os.path.join(extension_root(), "config", "legends.json")


def override_path_file():
    """Return the optional one-line file that points at an office settings file."""
    return os.path.join(extension_root(), "config", "user_settings_path.txt")


def resolve_settings_path():
    """Return the settings path for this command.

    Rocket mode keeps the interpreter alive, so this is resolved on every
    command and never cached on the module.
    """
    pointer = override_path_file()
    if os.path.isfile(pointer):
        with open(pointer, "r", encoding="utf-8") as handle:
            custom = handle.read().strip()
        if custom:
            if not os.path.isfile(custom):
                raise ConfigurationError(
                    "The configured settings file does not exist: {0}. "
                    "Open Place Resources > Settings and choose a file, "
                    "or delete {1}.".format(custom, pointer)
                )
            return custom
    return default_settings_path()


def set_settings_override(path):
    """Remember an office settings file for later commands."""
    target = override_path_file()
    if not path:
        if os.path.isfile(target):
            os.remove(target)
        return
    if not os.path.isfile(path):
        raise ConfigurationError("Cannot use settings file '{0}' because it does not exist.".format(path))
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(os.path.abspath(path))


def load_settings(path=None):
    """Load, migrate, and validate settings. Call once per command."""
    settings_path = path or resolve_settings_path()
    data = _read_json(settings_path)
    data = migrate_settings(data)
    _validate_settings(data, settings_path)
    data = _apply_defaults(data)
    alias_path = _alias_path(settings_path, data.get("parameter_alias_file"))
    aliases = load_aliases(alias_path)
    return {
        "path": settings_path,
        "alias_path": alias_path,
        "data": data,
        "aliases": aliases,
    }


def migrate_settings(data):
    """Accept schema 1.0. Refuse unknown versions instead of guessing."""
    if not isinstance(data, dict):
        raise ConfigurationError("The settings file must contain a JSON object.")
    version = data.get("schema_version")
    if version != SUPPORTED_SCHEMA:
        raise ConfigurationError(
            "Settings schema_version '{0}' is not supported. This build reads schema {1}. "
            "Add a migration before changing the file version.".format(version, SUPPORTED_SCHEMA)
        )
    return data


def load_aliases(path):
    """Load the parameter alias table."""
    data = _read_json(path)
    if not isinstance(data, dict) or not data:
        raise ConfigurationError(
            "Parameter alias file {0} must be a JSON object with one entry per parameter.".format(path)
        )
    for key, spec in data.items():
        if not isinstance(key, str) or not key.strip():
            raise ConfigurationError("Parameter alias keys must be non-empty strings in {0}.".format(path))
        if not isinstance(spec, dict):
            raise ConfigurationError("Alias '{0}' in {1} must be an object.".format(key, path))
        builtin = spec.get("builtin")
        guid = spec.get("guid")
        names = spec.get("names")
        if builtin is not None and not isinstance(builtin, str):
            raise ConfigurationError("Alias '{0}' builtin must be a string or null.".format(key))
        if guid is not None and not isinstance(guid, str):
            raise ConfigurationError("Alias '{0}' guid must be a string or null.".format(key))
        if names is None:
            names = []
            spec["names"] = names
        if not isinstance(names, list) or any(not isinstance(item, str) for item in names):
            raise ConfigurationError("Alias '{0}' names must be a list of strings.".format(key))
        if not builtin and not guid and not names:
            raise ConfigurationError(
                "Alias '{0}' needs a built-in parameter, a shared parameter GUID, or an exact name.".format(key)
            )
        if guid:
            _validate_guid(guid, key)
    return data


def apply_name_pattern(pattern, tokens):
    """Replace known tokens without calling format on user-authored braces."""
    result = "" if pattern is None else str(pattern)
    for key, value in tokens.items():
        result = result.replace("{" + key + "}", "" if value is None else str(value))
    return sanitize_view_name(result)


def sanitize_view_name(name):
    """Remove characters Revit rejects in view names."""
    invalid = '\\/:*?"<>|{}[]'
    cleaned = []
    for character in "" if name is None else str(name):
        if character in "\r\n\t":
            cleaned.append(" ")
        elif character in invalid:
            cleaned.append("-")
        else:
            cleaned.append(character)
    text = "".join(cleaned).strip()
    if len(text) > 200:
        text = text[:200].rstrip()
    if not text:
        raise ConfigurationError("The legend name pattern produced an empty view name.")
    return text


def definition_by_id(settings, definition_id):
    """Return one legend definition from a loaded settings bundle."""
    for definition in settings["data"]["legend_definitions"]:
        if definition["id"] == definition_id:
            return definition
    raise ConfigurationError(
        "Legend definition '{0}' is not in {1}.".format(definition_id, settings["path"])
    )


def _read_json(path):
    if not os.path.isfile(path):
        raise ConfigurationError(
            "Cannot find settings file {0}. Install the extension config folder "
            "or choose a file from Place Resources > Settings.".format(path)
        )
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except ValueError as ex:
        raise ConfigurationError("Settings file {0} is not valid JSON. {1}".format(path, ex))


def _alias_path(settings_path, configured_name):
    if not configured_name:
        raise ConfigurationError("Settings must include parameter_alias_file.")
    if os.path.isabs(configured_name):
        return configured_name
    return os.path.join(os.path.dirname(settings_path), configured_name)


def _apply_defaults(data):
    for definition in data["legend_definitions"]:
        include_defaults = WALL_INCLUDE_DEFAULTS if _is_wall(definition) else GENERIC_INCLUDE_DEFAULTS
        include = definition.setdefault("include", {})
        for key, value in include_defaults.items():
            include.setdefault(key, value)
        for section, defaults in BEHAVIOUR_DEFAULTS.items():
            block = definition.setdefault(section, {})
            for key, value in defaults.items():
                block.setdefault(key, value)
    return data


def _validate_settings(data, path):
    definitions = data.get("legend_definitions")
    if not isinstance(definitions, list) or not definitions:
        raise ConfigurationError("{0} must contain a non-empty legend_definitions list.".format(path))
    if not data.get("parameter_alias_file"):
        raise ConfigurationError("{0} must set parameter_alias_file.".format(path))
    seen = set()
    for index, definition in enumerate(definitions):
        label = "legend_definitions[{0}]".format(index)
        if not isinstance(definition, dict):
            raise ConfigurationError("{0} must be an object.".format(label))
        _require_strings(definition, ("id", "display_name", "category", "template_legend_name",
                                      "output_name_pattern", "output_identity_parameter"), label)
        if definition["id"] in seen:
            raise ConfigurationError("Duplicate legend definition id '{0}'.".format(definition["id"]))
        seen.add(definition["id"])
        if not str(definition["category"]).startswith("OST_"):
            raise ConfigurationError(
                "{0} category must be a built-in category name such as OST_Walls.".format(label)
            )
        view_types = definition.get("source_view_types")
        if not isinstance(view_types, list) or not view_types or any(not isinstance(item, str) for item in view_types):
            raise ConfigurationError("{0} source_view_types must be a non-empty list of view type names.".format(label))
        _validate_include(definition, label)
        _validate_sort(definition.get("sort"), label)
        _validate_representation(definition.get("representation"), label)
        _validate_layout(definition.get("layout"), label)
        _validate_labels(definition.get("labels"), label)
        _require_bool_map(definition.get("styles"), ("show_border", "show_headers"), label + ".styles")
        _require_strings(definition.get("styles") or {}, REQUIRED_STYLES[:3], label + ".styles")
        _require_bool_map(definition.get("update"), REQUIRED_UPDATE, label + ".update")
        _validate_optional_sections(definition, label)


def _validate_optional_sections(definition, label):
    type_rules = definition.get("type_rules", {})
    if type_rules is not None and not isinstance(type_rules, dict):
        raise ConfigurationError("{0}.type_rules must be an object.".format(label))
    unmapped = (type_rules or {}).get("unmapped_parameter", "warn_and_blank")
    if unmapped not in ("warn_and_blank", "error"):
        raise ConfigurationError(
            "{0}.type_rules.unmapped_parameter must be 'warn_and_blank' or 'error'.".format(label)
        )
    placement = definition.get("sheet_placement", {})
    if placement is not None and not isinstance(placement, dict):
        raise ConfigurationError("{0}.sheet_placement must be an object.".format(label))
    mode = (placement or {}).get("mode", "pick_point")
    if mode not in ("pick_point", "configured_point"):
        raise ConfigurationError(
            "{0}.sheet_placement.mode must be 'pick_point' or 'configured_point'.".format(label)
        )


def _is_wall(definition):
    return definition.get("category") == "OST_Walls"


def _validate_include(definition, label):
    include = definition.get("include")
    prefix = label + ".include"
    if _is_wall(definition):
        _require_bool_map(include, REQUIRED_INCLUDE, prefix)
    else:
        _require_bool_map(include, REQUIRED_GENERIC_INCLUDE, prefix)
        wall_keys = [key for key in WALL_ONLY_INCLUDE if key in include]
        if wall_keys:
            raise ConfigurationError(
                "{0} has wall-only flags ({1}) but the category is {2}. Remove them. "
                "Use in_place, linked_models, and demolished for this category.".format(
                    prefix, ", ".join(wall_keys), definition.get("category")
                )
            )
    for key in OPTIONAL_INCLUDE:
        if key in include and not isinstance(include[key], bool):
            raise ConfigurationError("{0}.{1} must be true or false.".format(prefix, key))


def _validate_sort(rules, label):
    if not isinstance(rules, list) or not rules:
        raise ConfigurationError("{0}.sort must contain at least one rule.".format(label))
    for index, rule in enumerate(rules):
        prefix = "{0}.sort[{1}]".format(label, index)
        if not isinstance(rule, dict):
            raise ConfigurationError("{0} must be an object.".format(prefix))
        if not isinstance(rule.get("parameter"), str) or not rule.get("parameter"):
            raise ConfigurationError("{0}.parameter is required.".format(prefix))
        if rule.get("direction") not in ("ascending", "descending"):
            raise ConfigurationError("{0}.direction must be ascending or descending.".format(prefix))
        if not isinstance(rule.get("natural_sort"), bool):
            raise ConfigurationError("{0}.natural_sort must be true or false.".format(prefix))


def _validate_representation(representation, label):
    if not isinstance(representation, dict):
        raise ConfigurationError("{0}.representation is required.".format(label))
    _require_strings(representation, ("view_direction", "detail_level"), label + ".representation")
    if representation["view_direction"] not in VIEW_DIRECTIONS:
        raise ConfigurationError(
            "{0}.representation.view_direction must be one of: {1}.".format(
                label, ", ".join(VIEW_DIRECTIONS)
            )
        )
    if representation["detail_level"] not in DETAIL_LEVELS:
        raise ConfigurationError(
            "{0}.representation.detail_level must be Coarse, Medium, or Fine.".format(label)
        )
    _require_number(representation.get("host_length_mm"), label + ".representation.host_length_mm", positive=True)
    scale = representation.get("scale")
    if not isinstance(scale, int) or isinstance(scale, bool) or scale <= 0:
        raise ConfigurationError("{0}.representation.scale must be a positive integer such as 20.".format(label))
    for key in ("layer_reference_planes", "fallback_detail_lines"):
        if key in representation and not isinstance(representation[key], bool):
            raise ConfigurationError("{0}.representation.{1} must be true or false.".format(label, key))


def _validate_layout(layout, label):
    if not isinstance(layout, dict):
        raise ConfigurationError("{0}.layout is required.".format(label))
    missing = [key for key in REQUIRED_LAYOUT if key not in layout]
    if missing:
        raise ConfigurationError("{0}.layout is missing {1}.".format(label, ", ".join(missing)))
    if layout["direction"] not in ("vertical", "horizontal"):
        raise ConfigurationError("{0}.layout.direction must be vertical or horizontal.".format(label))
    if layout["align"] not in ALIGNMENTS:
        raise ConfigurationError(
            "{0}.layout.align must be one of: {1}.".format(label, ", ".join(ALIGNMENTS))
        )
    columns = layout["columns"]
    if not isinstance(columns, int) or isinstance(columns, bool) or columns <= 0:
        raise ConfigurationError("{0}.layout.columns must be a positive integer.".format(label))
    if not isinstance(layout["auto_size_rows"], bool):
        raise ConfigurationError("{0}.layout.auto_size_rows must be true or false.".format(label))
    for key in REQUIRED_LAYOUT:
        if key.endswith("_mm"):
            _require_number(layout[key], "{0}.layout.{1}".format(label, key), positive=False)


def _validate_labels(labels, label):
    if not isinstance(labels, list) or not labels:
        raise ConfigurationError("{0}.labels must contain at least one label.".format(label))
    for index, item in enumerate(labels):
        prefix = "{0}.labels[{1}]".format(label, index)
        if not isinstance(item, dict):
            raise ConfigurationError("{0} must be an object.".format(prefix))
        for key in ("parameter", "heading"):
            if not isinstance(item.get(key), str) or not item.get(key).strip():
                raise ConfigurationError("{0}.{1} is required.".format(prefix, key))
        _require_number(item.get("width_mm"), prefix + ".width_mm", positive=True)
        if not isinstance(item.get("required"), bool):
            raise ConfigurationError("{0}.required must be true or false.".format(prefix))
        if "format" in item and item["format"] not in ("millimetres", "text"):
            raise ConfigurationError("{0}.format must be 'millimetres' or 'text'.".format(prefix))
        if "decimals" in item and (not isinstance(item["decimals"], int) or isinstance(item["decimals"], bool)):
            raise ConfigurationError("{0}.decimals must be an integer.".format(prefix))


def _require_strings(block, keys, label):
    for key in keys:
        value = block.get(key) if isinstance(block, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError("{0}.{1} must be a non-empty string.".format(label, key))


def _require_bool_map(block, keys, label):
    if not isinstance(block, dict):
        raise ConfigurationError("{0} is required.".format(label))
    for key in keys:
        if not isinstance(block.get(key), bool):
            raise ConfigurationError("{0}.{1} must be true or false.".format(label, key))


def _require_number(value, label, positive):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError("{0} must be a number.".format(label))
    if positive and value <= 0:
        raise ConfigurationError("{0} must be greater than zero.".format(label))


def _validate_guid(value, key):
    text = value.strip()
    parts = text.split("-")
    if len(parts) != 5 or [len(part) for part in parts] != [8, 4, 4, 4, 12]:
        raise ConfigurationError(
            "Alias '{0}' guid '{1}' is not a GUID. Expected 8-4-4-4-12 hexadecimal characters.".format(key, value)
        )
    try:
        int(text.replace("-", ""), 16)
    except ValueError:
        raise ConfigurationError("Alias '{0}' guid '{1}' contains non-hexadecimal characters.".format(key, value))
