#! python3
# -*- coding: utf-8 -*-
"""Build a legend from the Excel legend library.

Choose a category, tick library rows, and the tool creates or updates the
master legend for that category: a hatch or legend component, the Code as
title, and the description for each row.
"""

__title__ = "Legend\nSetup"
__doc__ = (
    "Create or update a library legend: choose a category (Walls, Fire Strategy, ...), "
    "tick rows from the Excel library, and the legend is built with hatch, title and description."
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
        "Place Resource lib folder was not found. Copy 'lib' and 'config' to "
        "Documents\\Gensler\\Python\\PlaceResource, or set PLACE_RESOURCE_HOME to the folder that "
        "contains them. Checked: " + "; ".join(os.path.abspath(item) for item in candidates if item)
    )


_find_lib()

from pyrevit import revit

from errors import LegendToolError
from legend_library import load_library_settings
from library_ui import run_setup
from logging_service import get_logger
from reporting import alert_error
from validation import assert_project_document

LOGGER = get_logger("legend_setup")


def main():
    """Load the library, then run the setup dialogs and build the legend."""
    doc = revit.doc
    assert_project_document(doc)
    library_settings = load_library_settings()
    for warning in library_settings["warnings"]:
        LOGGER.warning("%s", warning)
    run_setup(doc, library_settings)


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Legend Setup", str(error))
    except Exception as error:
        LOGGER.exception("Legend Setup failed")
        alert_error("Legend Setup", "Unexpected failure: {0}".format(error))
