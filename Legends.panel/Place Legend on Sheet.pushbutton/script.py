#! python3
# -*- coding: utf-8 -*-
"""Make legends for a sheet from the symbol families and place them on it.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Place Legend\non Sheet"
__doc__ = (
    "Make legends for the open sheet (or a sheet you pick) and place them: "
    "choose the categories, draw a box or type the width, then the headings."
)
__author__ = "Place Resource"

import os
import sys


def _find_lib():
    """Put the Place Resource lib folder on sys.path.

    A folder qualifies when it holds lib/legend_service.py. Keep config/ next to lib/. Checked in order:
    1. The PLACE_RESOURCE_HOME environment variable.
    2. PlaceResource next to Legends.panel (repository layout).
    3. Documents/Gensler/Python/PlaceResource under OneDrive, then the user profile.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.environ.get("PLACE_RESOURCE_HOME"), os.path.join(here, "..", "..", "PlaceResource")]
    for root in (os.environ.get("OneDriveCommercial"), os.environ.get("OneDrive"), os.path.expanduser("~")):
        if root:
            candidates.append(os.path.join(root, "Documents", "Gensler", "Python", "PlaceResource"))
    for folder in candidates:
        if not folder:
            continue
        lib = os.path.abspath(os.path.join(folder, "lib"))
        if os.path.isfile(os.path.join(lib, "legend_service.py")):
            if lib not in sys.path:
                sys.path.insert(0, lib)
            # Load the current lib code on every click. Edited files then work without
            # a pyRevit Reload, which breaks the CPython engine until Revit restarts.
            prefix = os.path.normcase(lib + os.sep)
            for name, module in list(sys.modules.items()):
                path = getattr(module, "__file__", None) or ""
                if path and os.path.normcase(os.path.abspath(path)).startswith(prefix):
                    del sys.modules[name]
            return lib
    raise ImportError(
        "PlaceResource folder not found. Copy lib and config to "
        "Documents\\Gensler\\Python\\PlaceResource, or set PLACE_RESOURCE_HOME. Looked in: " + "; ".join(os.path.abspath(item) for item in candidates if item)
    )


_find_lib()

import trail

trail.start("Place Legend on Sheet")

from pyrevit import revit

from errors import LegendToolError
from logging_service import get_logger
from reporting import alert_error
from validation import assert_project_document

LOGGER = get_logger("place_legend_on_sheet")


def main():
    """Pick the legend categories for a sheet, then build and place each one."""
    from dialogs import choose_many_from_list
    from identity import find_library_legend
    from legend_library import load_library_settings
    from library_ui import _active_sheet, choose_sheet, run_sheet_legend
    from placement_service import sheet_label
    doc = revit.doc
    uidoc = revit.uidoc
    assert_project_document(doc)
    library_settings = load_library_settings()
    sheet = _active_sheet(doc) or choose_sheet(doc)
    if sheet is None:
        return
    categories = list(library_settings["categories"].keys())
    preselected = [index for index, category in enumerate(categories)
                   if find_library_legend(doc, category, sheet) is not None]
    chosen = choose_many_from_list(
        "Place Legend on Sheet", categories, preselected=preselected,
        prompt="Tick the legends for sheet {0}. Ticked: legends this sheet already has.".format(sheet_label(sheet)),
    )
    if not chosen:
        return
    for index in chosen:
        # One legend failing does not stop the others. Each one is its own undoable change.
        try:
            run_sheet_legend(doc, uidoc, sheet, categories[index], library_settings)
        except LegendToolError as error:
            LOGGER.error("%s", error)
            alert_error("Place Legend on Sheet", "{0}\n\n{1}".format(categories[index], error))


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Place Legend on Sheet", str(error))
    except Exception as error:
        LOGGER.exception("Place Legend on Sheet failed")
        alert_error("Place Legend on Sheet", "Something went wrong: {0}".format(error))
