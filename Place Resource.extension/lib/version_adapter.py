# -*- coding: utf-8 -*-
"""Isolate Revit-version differences from the rest of the tool.

Nothing in this module is a claim that a Revit version has been tested.
Callers use these helpers so version checks do not spread through services.
"""

from errors import UnsupportedRevitOperationError


def get_db():
    """Return the pyRevit Revit API namespace."""
    from pyrevit import DB
    return DB


def get_host_version():
    """Return the running Revit year as an integer, or 0 when unknown."""
    try:
        from pyrevit import HOST_APP
        return int(HOST_APP.version)
    except Exception:
        return 0


def element_id_value(element_id):
    """Return the integer stored by an ElementId.

    Revit 2024 renamed IntegerValue to Value. Both are read when present.
    """
    if element_id is None:
        return -1
    value_attr = getattr(element_id, "Value", None)
    if value_attr is not None:
        try:
            return int(value_attr)
        except Exception:
            pass
    integer_value = getattr(element_id, "IntegerValue", None)
    if integer_value is not None:
        try:
            return int(integer_value)
        except Exception:
            pass
    try:
        return int(element_id)
    except Exception:
        return -1


def make_element_id(value):
    """Build an ElementId from an integer without assuming the constructor width."""
    DB = get_db()
    number = int(value)
    try:
        return DB.ElementId(number)
    except Exception:
        pass
    try:
        from System import Int64
        return DB.ElementId(Int64(number))
    except Exception as ex:
        raise UnsupportedRevitOperationError(
            "This Revit version could not create an ElementId from {0}. {1}".format(
                number, ex
            )
        )


def category_id_value(built_in_category):
    """Return the integer id of a built-in category."""
    DB = get_db()
    return element_id_value(DB.ElementId(built_in_category))


def builtin_parameter(name):
    """Return a BuiltInParameter by configured name, or None if this Revit lacks it."""
    if not name:
        return None
    DB = get_db()
    return getattr(DB.BuiltInParameter, str(name), None)


def describe_version():
    """Return a short Revit/pyRevit version string for reports."""
    year = get_host_version()
    engine = "cpython3"
    try:
        import sys
        engine = "cpython {0}".format(sys.version.split()[0])
    except Exception:
        pass
    if year:
        return "Revit {0}, {1}".format(year, engine)
    return "Revit version unknown, {0}".format(engine)
