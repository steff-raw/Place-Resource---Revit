#! python3
# -*- coding: utf-8 -*-
"""Update every tool-managed legend whose visible types have changed.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Update All\nGenerated Legends"
__doc__ = "Update tool-managed legends whose source views still exist."
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
            return lib
    raise ImportError(
        "Place Resource lib folder was not found. Copy 'lib' and 'config' to "
        "Documents\\Gensler\\Python\\PlaceResource, or set PLACE_RESOURCE_HOME to the folder that "
        "contains them. Checked: " + "; ".join(os.path.abspath(item) for item in candidates if item)
    )


_find_lib()

from pyrevit import revit

from configuration import load_settings
from dialogs import ask_yes_no
from errors import LegendToolError
from identity import iter_generated_legends
from legend_service import update_all
from logging_service import get_logger
from reporting import alert_error, print_batch
from validation import assert_project_document

LOGGER = get_logger("update_all_generated_legends")


def main():
    """Refresh managed legends and skip deleted source views."""
    doc = revit.doc
    assert_project_document(doc)
    settings = load_settings()
    legends = list(iter_generated_legends(doc))
    if not legends:
        raise LegendToolError("This model has no tool-managed legends to update.")
    accepted = ask_yes_no(
        "Update All Generated Legends",
        "Update {0} generated legend(s)?".format(len(legends)),
        content="Legends whose content hash is unchanged are skipped. Viewport positions are preserved. "
                "Source views that were deleted are reported and skipped.",
        yes_label="Update the legends",
        no_label="Cancel",
    )
    if not accepted:
        return
    allow_delete = True
    if _any_definition_confirms(settings):
        allow_delete = ask_yes_no(
            "Remove obsolete legend entries",
            "Remove managed entries for types that are no longer visible?",
            content="Manual notes and unmanaged annotation are not deleted.",
            yes_label="Remove them",
            no_label="Keep them",
        )
    summary = update_all(doc, settings, {
        "allow_delete": allow_delete,
        "skip_if_unchanged": True,
    })
    print_batch(summary)
    if summary.get("failed"):
        alert_error(
            "Update All Generated Legends",
            "{0} legend(s) failed. The output window lists the errors. "
            "Successful legends were kept.".format(len(summary["failed"])),
        )


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
        alert_error("Update All Generated Legends", "Unexpected failure: {0}".format(error))
