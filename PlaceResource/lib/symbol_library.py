# -*- coding: utf-8 -*-
"""Read the legend library from symbol families loaded in the model. Read-only.

One family per category, e.g. "PR Legend - Walls". Each family type is one
legend row: its type name is the code (the Type Mark, e.g. IWS-105), and the
type parameter named in description_parameter holds the description.
"""

from layout_engine import natural_sort_key
from legend_library import LibraryEntry
from version_adapter import element_id_value, get_db

ALLOWED_FAMILY_CATEGORIES = ("OST_GenericAnnotation", "OST_DetailComponents")


def find_family(doc, family_name):
    """Return the loaded Family with this name (exact, then case-insensitive), or None."""
    DB = get_db()
    families = list(DB.FilteredElementCollector(doc).OfClass(DB.Family))
    for family in families:
        if _name(family) == family_name:
            return family
    wanted = family_name.strip().lower()
    for family in families:
        if _name(family).strip().lower() == wanted:
            return family
    return None


def family_entries(doc, config):
    """Return (entries, problems) for a category.

    ``entries`` are LibraryEntry rows sorted naturally by code (W1, W2, W10).
    ``problems`` are blocking messages (family missing or of the wrong category).
    """
    DB = get_db()
    family_name = config["family_name"]
    family = find_family(doc, family_name)
    if family is None:
        return [], [
            "Family '{0}' is not loaded in this model. Load it (Insert > Load Family), or build it with "
            "Build Legend Family.".format(family_name)
        ]
    problem = _category_problem(DB, family, family_name)
    if problem:
        return [], [problem]
    entries = []
    for symbol_id in family.GetFamilySymbolIds():
        symbol = doc.GetElement(symbol_id)
        if symbol is None:
            continue
        code = _name(symbol).strip()
        if not code:
            continue
        entries.append(LibraryEntry(
            code=code,
            description=_parameter_text(symbol, config["description_parameter"]),
            symbol_id=element_id_value(symbol.Id),
            symbol_unique_id=getattr(symbol, "UniqueId", None),
        ))
    entries.sort(key=lambda entry: natural_sort_key(entry.code))
    return entries, []


def symbols_by_code(doc, entries):
    """Map each entry's code to its FamilySymbol element (missing ones are left out)."""
    from version_adapter import make_element_id
    result = {}
    for entry in entries:
        if entry.symbol_id is None:
            continue
        symbol = doc.GetElement(make_element_id(entry.symbol_id))
        if symbol is not None:
            result[entry.code] = symbol
    return result


def _category_problem(DB, family, family_name):
    allowed = set()
    for name in ALLOWED_FAMILY_CATEGORIES:
        built_in = getattr(DB.BuiltInCategory, name, None)
        if built_in is not None:
            allowed.add(element_id_value(DB.ElementId(built_in)))
    category = getattr(family, "FamilyCategory", None)
    if category is None:
        return None
    if element_id_value(category.Id) not in allowed:
        return (
            "Family '{0}' is a {1} family. Use a Generic Annotation family (or a Detail Item family) "
            "so it can be placed in a legend.".format(family_name, getattr(category, "Name", "different"))
        )
    return None


def _parameter_text(element, name):
    try:
        parameter = element.LookupParameter(name)
    except Exception:
        return ""
    if parameter is None:
        return ""
    try:
        text = parameter.AsString()
        if text is None:
            text = parameter.AsValueString()
        return (text or "").strip()
    except Exception:
        return ""


def _name(element):
    try:
        return element.Name or ""
    except Exception:
        return ""
