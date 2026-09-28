#! python3
# -*- coding: utf-8 -*-
"""Build or rebuild the legend symbol family for a category.

One Generic Annotation family per category (e.g. "PR Legend - Walls"), one type
per code: type name = Type Mark, Code and Description type parameters, and the
hatch swatch of the Filled Region Type named as the code.
"""

__title__ = "Build Legend\nFamily"
__doc__ = (
    "Build or rebuild the legend symbol family of a category from the model: one type per "
    "Type Mark with its hatch and description. The family is saved and loaded into the model."
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
from library_ui import run_build_family
from logging_service import get_logger
from reporting import alert_error
from validation import assert_project_document

LOGGER = get_logger("build_legend_family")


def main():
    """Choose a category and codes, then build, save and load the family."""
    doc = revit.doc
    assert_project_document(doc)
    run_build_family(doc, load_library_settings())


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Build Legend Family", str(error))
    except Exception as error:
        LOGGER.exception("Build Legend Family failed")
        alert_error("Build Legend Family", "Unexpected failure: {0}".format(error))
