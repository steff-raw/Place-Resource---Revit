# -*- coding: utf-8 -*-
"""Convert millimetres to Revit internal units.

Revit stores lengths in decimal feet. 1 foot = 304.8 mm exactly, so this
conversion does not depend on a Revit session and stays stable across versions.
"""

MM_PER_FOOT = 304.8


def mm_to_internal(millimetres):
    """Return decimal feet for a millimetre length."""
    return float(millimetres) / MM_PER_FOOT


def internal_to_mm(internal_feet):
    """Return millimetres for a length stored in decimal feet."""
    return float(internal_feet) * MM_PER_FOOT


def format_millimetres(internal_feet, decimals=0):
    """Format an internal length as a millimetre string."""
    millimetres = internal_to_mm(internal_feet)
    places = int(decimals or 0)
    if places <= 0:
        return str(int(round(millimetres)))
    return "{0:.{1}f}".format(millimetres, places)
