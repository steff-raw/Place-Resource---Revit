#! python3
# -*- coding: utf-8 -*-
"""Update every legend made by this tool when its visible types have changed.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Update All\nGenerated Legends"
__doc__ = "Update all legends made by this tool."
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

from configuration import load_settings
from dialogs import ask_yes_no
from errors import LegendToolError
from identity import ROLE_LIBRARY_LEGEND, iter_generated_legends
from legend_library import load_library_settings
from legend_service import update_all
from library_legend_service import update_all_library
from logging_service import get_logger
from reporting import alert_error, print_batch, print_library_batch
from ui_service import ensure_text_style
from validation import assert_project_document

LOGGER = get_logger("update_all_generated_legends")


def main():
    """Refresh view/sheet type legends and library legends. Deleted sources are reported and skipped."""
    doc = revit.doc
    assert_project_document(doc)
    settings = load_settings()
    legends = list(iter_generated_legends(doc))
    library_legends = list(iter_generated_legends(doc, ROLE_LIBRARY_LEGEND))
    if not legends and not library_legends:
        raise LegendToolError("No legends made by this tool in this model.")
    accepted = ask_yes_no(
        "Update All Generated Legends",
        "Update {0} type legends and {1} library legends?".format(len(legends), len(library_legends)),
        content="Unchanged legends are skipped. Viewports stay where they are. "
                "Legends whose view or sheet was deleted are listed and skipped. "
                "Library legends are rebuilt from the current symbol families.",
        yes_label="Update the legends",
        no_label="Cancel",
    )
    if not accepted:
        return
    if not ensure_text_style(doc, _text_type_names(settings, legends)):
        return
    failed = 0
    if legends:
        allow_delete = True
        if _any_definition_confirms(settings):
            allow_delete = ask_yes_no(
                "Remove old legend rows",
                "Remove rows for types that are no longer visible?",
                content="Notes you added by hand are never removed.",
                yes_label="Remove them",
                no_label="Keep them",
            )
        summary = update_all(doc, settings, {
            "allow_delete": allow_delete,
            "skip_if_unchanged": True,
        })
        print_batch(summary)
        failed += len(summary.get("failed") or [])
    if library_legends:
        library_settings = load_library_settings()
        library_summary = update_all_library(doc, library_settings)
        print_library_batch(library_summary)
        failed += len(library_summary.get("failed") or [])
    if failed:
        alert_error(
            "Update All Generated Legends",
            "{0} legends failed, see the output window. "
            "The others were updated.".format(failed),
        )


def _text_type_names(settings, legends):
    """Text types the type legends in this model need, from the settings file."""
    used = set(payload.get("legend_definition_id") for _view, payload in legends)
    names = []
    for definition in settings["data"]["legend_definitions"]:
        if definition["id"] in used:
            names.extend([definition["styles"]["text_note_type"], definition["styles"]["header_text_note_type"]])
    return names


def _any_definition_confirms(settings):
    for definition in settings["data"]["legend_definitions"]:
        update = definition.get("update") or {}
        if update.get("remove_unused_entries") and update.get("confirm_before_deleting"):
            return True
    return False


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Update All Generated Legends", str(error))
    except Exception as error:
        LOGGER.exception("Update All Generated Legends failed")
        alert_error("Update All Generated Legends", "Something went wrong: {0}".format(error))
