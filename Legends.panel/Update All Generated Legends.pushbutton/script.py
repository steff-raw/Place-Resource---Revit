#! python3
# -*- coding: utf-8 -*-
"""Rebuild every legend made by this tool, in place.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Update All\nGenerated Legends"
__doc__ = "Redraw every legend made by this tool in place: same width, same position."
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

from pyrevit import revit

from dialogs import ask_yes_no
from errors import LegendToolError
from legend_library import load_library_settings
from library_legend_service import project_library, tool_legends, update_all_library
from logging_service import get_logger
from reporting import alert_error, print_library_batch
from ui_service import ensure_text_style
from validation import assert_project_document

LOGGER = get_logger("update_all_generated_legends")


def main():
    """Rebuild every legend this tool made, in place."""
    doc = revit.doc
    assert_project_document(doc)
    library_settings = load_library_settings()
    legends = tool_legends(doc, project_library(doc, library_settings))
    if not legends:
        raise LegendToolError(
            "No legends made by this tool in this model. They are named like 'Walls LEGEND - A-101'."
        )
    accepted = ask_yes_no(
        "Update All Generated Legends",
        "Update {0} legends?".format(len(legends)),
        content="Each legend is redrawn from its symbol family and the Type Marks on its sheet. "
                "Anything changed by hand inside these legends is replaced. "
                "Width, headings and position on the sheet stay the same.",
        yes_label="Update the legends",
        no_label="Cancel",
    )
    if not accepted:
        return
    if not ensure_text_style(doc, _text_type_names(library_settings)):
        return
    summary = update_all_library(doc, library_settings)
    print_library_batch(summary)
    failed = len(summary.get("failed") or [])
    skipped = len(summary.get("skipped") or [])
    if failed or skipped:
        alert_error(
            "Update All Generated Legends",
            "{0} failed and {1} skipped, see the output window. The others were updated.".format(failed, skipped),
        )


def _text_type_names(library_settings):
    names = set()
    for config in library_settings["categories"].values():
        names.add(config["styles"]["text_type"])
        if config["styles"].get("show_heading"):
            names.add(config["styles"]["heading_text_type"])
    return sorted(names)


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Update All Generated Legends", str(error))
    except Exception as error:
        LOGGER.exception("Update All Generated Legends failed")
        alert_error("Update All Generated Legends", "Something went wrong: {0}".format(error))
