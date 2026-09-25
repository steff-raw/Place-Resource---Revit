# -*- coding: utf-8 -*-
"""Update every tool-managed legend whose visible types have changed.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Update All\nGenerated Legends"
__doc__ = "Update tool-managed legends whose source views still exist."
__author__ = "Place Resource"

import os
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from pyrevit import forms, revit

from configuration import load_settings
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
    accepted = forms.alert(
        "Update {0} generated legend(s)? Legends whose content hash is unchanged are skipped. "
        "Viewport positions are preserved. Source views that were deleted are reported and skipped.".format(
            len(legends)
        ),
        title="Update All Generated Legends",
        ok=False,
        yes=True,
        no=True,
    )
    if not accepted:
        return
    allow_delete = True
    if _any_definition_confirms(settings):
        allow_delete = bool(forms.alert(
            "Remove managed entries for types that are no longer visible? "
            "Manual notes and unmanaged annotation are not deleted.",
            title="Remove obsolete legend entries",
            ok=False,
            yes=True,
            no=True,
        ))
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
