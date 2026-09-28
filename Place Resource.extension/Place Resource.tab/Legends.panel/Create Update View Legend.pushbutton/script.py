#! python3
# -*- coding: utf-8 -*-
"""Create or update the legend for the active model view.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Create / Update\nView Legend"
__doc__ = "Create or update a legend from the types visible in the active view."
__author__ = "Place Resource"

import os
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from pyrevit import revit

from configuration import load_settings
from errors import LegendToolError
from legend_service import create_or_update, prepare_plan
from logging_service import get_logger
from placement_service import interactive_place
from reporting import alert_error, print_plan, print_report
from ui_service import choose_definition, confirm_delete, confirm_plan
from validation import (
    assert_project_document,
    assert_supported_source_view,
    definitions_for_view,
    view_type_token,
)
from version_adapter import element_id_value, make_element_id

LOGGER = get_logger("create_update_view_legend")


def main():
    """Validate the view, confirm the plan, then commit the legend."""
    doc = revit.doc
    uidoc = revit.uidoc
    assert_project_document(doc)
    settings = load_settings()
    view = doc.ActiveView
    if view is None:
        raise LegendToolError("There is no active view. Open a plan, section, or elevation.")
    token = view_type_token(view)
    if token == "DrawingSheet":
        raise LegendToolError(
            "The active view is a sheet. Open a plan, section, or elevation, "
            "or run Place Legend on Sheet and pick a viewport."
        )
    if token == "Legend":
        raise LegendToolError(
            "A legend cannot be the source view. Open the model view whose visible types should be listed."
        )
    available = definitions_for_view(settings, view)
    if not available:
        raise LegendToolError(
            "No legend definition in the settings file supports the active view '{0}'. "
            "Open a view listed in source_view_types, or add this view type to the JSON file.".format(
                view.Name if view is not None else "(none)"
            )
        )
    definition = choose_definition(available)
    if definition is None:
        return
    assert_supported_source_view(view, definition)
    plan = prepare_plan(doc, view, definition, settings)
    print_plan(plan, definition)
    if plan["blocking_errors"]:
        alert_error("Create / Update View Legend", "\n".join(plan["blocking_errors"]))
        return
    choices = confirm_plan(view, definition, plan)
    if not choices or not choices.get("apply_changes"):
        print_report({
            "status": "preview",
            "source_view_id": element_id_value(view.Id),
            "source_view_name": view.Name,
            "legend_view_id": None if plan["existing"] is None else element_id_value(plan["existing"].Id),
            "legend_view_name": plan["existing_name"],
            "definition_name": definition["display_name"],
            "instance_count": plan["collection"].instance_count,
            "unique_type_count": plan["collection"].unique_type_count,
            "added": [],
            "updated": [],
            "removed": [],
            "realigned": 0,
            "warnings": ["No changes were made. The output above is the preview."],
            "errors": [],
            "notices": [],
            "host": "",
            "version": "",
        })
        return
    allow_delete = _confirm_removal(doc, definition, plan)
    report = create_or_update(doc, view, definition, settings, {"allow_delete": allow_delete})
    if choices.get("place_on_sheet") and report.get("status") != "failed" and report.get("legend_view_id") is not None:
        legend_view = doc.GetElement(make_element_id(report["legend_view_id"]))
        try:
            viewport, warnings = interactive_place(doc, uidoc, view, legend_view, definition)
        except LegendToolError as error:
            viewport = None
            warnings = [str(error)]
        if viewport is None:
            report.setdefault("warnings", []).append("The legend was saved and was not placed on a sheet.")
        report.setdefault("warnings", []).extend(warnings or [])
    print_report(report)
    if report.get("status") == "failed":
        alert_error("Create / Update View Legend", "\n".join(report.get("errors") or ["The legend was not changed."]))


def _confirm_removal(doc, definition, plan):
    update = definition["update"]
    if not plan["to_remove"] or not update.get("remove_unused_entries"):
        return False
    if not update.get("confirm_before_deleting"):
        return True
    labels = []
    for type_id in plan["to_remove"]:
        element = doc.GetElement(make_element_id(type_id))
        labels.append(element.Name if element is not None else str(type_id))
    return bool(confirm_delete(labels))


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Create / Update View Legend", str(error))
    except Exception as error:
        LOGGER.exception("Create / Update View Legend failed")
        alert_error("Create / Update View Legend", "Unexpected failure: {0}".format(error))
