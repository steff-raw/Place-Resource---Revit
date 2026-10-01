# -*- coding: utf-8 -*-
"""Per-project legend settings stored in the Revit model.

One DataStorage element carries an Extensible Storage entity with a JSON payload:

    {"text_type": "<TextNoteType name>",
     "families": {"<category>": "<family name>"},
     "headings": {"<category>": {"title": ..., "graphic": ..., "description": ...}}}

The settings travel with the model, so every project keeps its own text style
its own symbol family and the last headings typed for each legend category.
Do not change the schema GUID. Keys from older versions (e.g. "masters") are ignored.
"""

import json

SETTINGS_SCHEMA_GUID = "5b7e2d94-3a1c-4f08-9e6b-2c4d8a1f7e35"
SETTINGS_SCHEMA_NAME = "PRLegendProjectSettings"
_EMPTY = {"text_type": None, "families": {}, "headings": {}}
_HEADING_KEYS = ("title", "graphic", "description")


def normalize(data):
    """Return a clean settings dict whatever was stored."""
    result = {"text_type": None, "families": {}, "headings": {}}
    if not isinstance(data, dict):
        return result
    text_type = data.get("text_type")
    if isinstance(text_type, str) and text_type.strip():
        result["text_type"] = text_type.strip()
    families = data.get("families")
    if isinstance(families, dict):
        for category, family in families.items():
            if isinstance(category, str) and isinstance(family, str) and family.strip():
                result["families"][category] = family.strip()
    headings = data.get("headings")
    if isinstance(headings, dict):
        for category, values in headings.items():
            if isinstance(category, str) and isinstance(values, dict):
                kept = dict((key, values[key]) for key in _HEADING_KEYS if isinstance(values.get(key), str))
                if kept:
                    result["headings"][category] = kept
    return result


def read(doc):
    """Return the project settings. Missing or unreadable storage gives the defaults."""
    from identity import _read_entity
    storage = _storage(doc, create=False)
    if storage is None:
        return normalize(_EMPTY)
    return normalize(_read_entity(storage, SETTINGS_SCHEMA_GUID))


def write(doc, data):
    """Save the settings. The caller must have a transaction open."""
    from identity import _write_entity
    storage = _storage(doc, create=True)
    _write_entity(storage, SETTINGS_SCHEMA_GUID, SETTINGS_SCHEMA_NAME, "Place Resource legend settings.", normalize(data))


def save(doc, data, name="Place Resource: legend settings"):
    """Open a transaction and save the settings."""
    from transactions import TransactionContext
    with TransactionContext(doc, name):
        write(doc, data)


def text_type_name(doc):
    """The text note type chosen for this project, or None."""
    return read(doc)["text_type"]


def family_assignments(doc):
    """Category name to symbol family name, as picked in Legend Setup."""
    return read(doc)["families"]


def assign_family(doc, category, family_name):
    """Save the symbol family for one category (opens its own transaction)."""
    data = read(doc)
    data["families"][category] = family_name
    save(doc, data, "Place Resource: legend family")


def saved_headings(doc, category):
    """The headings last typed for this legend category, or {}."""
    return read(doc)["headings"].get(category, {})


def save_headings(doc, category, headings):
    """Remember the headings for one category (opens its own transaction). Skips the save when unchanged."""
    data = read(doc)
    wanted = dict((key, headings.get(key, "")) for key in _HEADING_KEYS)
    if data["headings"].get(category) == wanted:
        return
    data["headings"][category] = wanted
    save(doc, data, "Place Resource: legend headings")


def describe(data):
    """Short text for dialogs."""
    data = normalize(data)
    return "Legend text style: {0}".format(data["text_type"] or "not set (settings file is used)")


def _storage(doc, create):
    from identity import _read_entity
    from version_adapter import get_db
    DB = get_db()
    for storage in DB.FilteredElementCollector(doc).OfClass(DB.ExtensibleStorage.DataStorage):
        if _read_entity(storage, SETTINGS_SCHEMA_GUID) is not None:
            return storage
    if not create:
        return None
    return DB.ExtensibleStorage.DataStorage.Create(doc)


def dumps(data):
    """Stable JSON text of the settings, used in reports and tests."""
    return json.dumps(normalize(data), sort_keys=True)
