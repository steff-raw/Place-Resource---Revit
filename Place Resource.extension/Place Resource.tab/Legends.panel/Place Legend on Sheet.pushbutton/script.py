#! python3
# -*- coding: utf-8 -*-
"""Place the generated legend for a model view onto a sheet.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Place Legend\non Sheet"
__doc__ = "Place the generated legend for a model view onto a sheet."
__author__ = "Place Resource"

import os
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from pyrevit import revit

from configuration import load_settings
from errors import LegendToolError
from identity import find_legend
from legend_service import create_or_update, prepare_plan
from logging_service import get_logger
from placement_service import interactive_place, model_viewports_on_sheet, sheet_label
from reporting import alert_error, print_report
from ui_service import choose_definition, choose_named_item, confirm_delete
from validation import assert_project_document, assert_supported_source_view, definitions_for_view, view_type_token
from version_adapter import element_id_value, get_db, make_element_id

LOGGER = get_logger("place_legend_on_sheet")


def main():
    """Place a generated legend on the active sheet, or on a sheet the user selects."""
    doc = revit.doc
    uidoc = revit.uidoc
    assert_project_document(doc)
    settings = load_settings()
    active = doc.ActiveView
    DB = get_db()
    if active is not None and active.ViewType == DB.ViewType.DrawingSheet:
        _place_from_sheet(doc, uidoc, active, settings)
        return
    definitions = definitions_for_view(settings, active)
    if not definitions:
        raise LegendToolError(
            "Open a supported model view, or open a sheet and run this command to pick a viewport."
        )
    definition = choose_definition(definitions)
    if definition is None:
        return
    assert_supported_source_view(active, definition)
    legend_view = _ensure_legend(doc, active, definition, settings)
    if legend_view is None:
        return
    viewport, warnings = interactive_place(doc, uidoc, active, legend_view, definition)
    _report_placement(active, legend_view, definition, viewport, warnings)


def _place_from_sheet(doc, uidoc, sheet, settings):
    pairs = model_viewports_on_sheet(doc, sheet, settings["data"]["legend_definitions"])
    if not pairs:
        raise LegendToolError(
            "Sheet '{0}' has no plan, section, or elevation viewport supported by the settings file.".format(
                sheet_label(sheet)
            )
        )
    labels = ["{0} ({1})".format(view.Name, view_type_token(view)) for _viewport, view in pairs]
    selected = choose_named_item(
        "Select the model view on this sheet",
        list(range(len(pairs))),
        lambda index: labels[index],
    )
    if selected is None:
        return
    _viewport, source_view = pairs[selected]
    definitions = definitions_for_view(settings, source_view)
    if not definitions:
        raise LegendToolError(
            "View '{0}' is not covered by a legend definition.".format(source_view.Name)
        )
    definition = choose_definition(definitions)
    if definition is None:
        return
    legend_view = _ensure_legend(doc, source_view, definition, settings)
    if legend_view is None:
        return
    viewport, warnings = interactive_place(
        doc, uidoc, source_view, legend_view, definition, active_sheet=sheet
    )
    _report_placement(source_view, legend_view, definition, viewport, warnings)


def _ensure_legend(doc, source_view, definition, settings):
    from pyrevit import forms
    legend_view = find_legend(doc, source_view, definition["id"])
    if legend_view is not None:
        return legend_view
    create = forms.alert(
        "There is no generated legend for '{0}' using '{1}'. Create it now?".format(
            source_view.Name, definition["display_name"]
        ),
        title="Place Legend on Sheet",
        ok=False,
        yes=True,
        no=True,
    )
    if not create:
        return None
    plan = prepare_plan(doc, source_view, definition, settings)
    allow_delete = False
    if plan["to_remove"] and definition["update"].get("remove_unused_entries"):
        allow_delete = True
        if definition["update"].get("confirm_before_deleting"):
            allow_delete = bool(confirm_delete([str(type_id) for type_id in plan["to_remove"]]))
    report = create_or_update(doc, source_view, definition, settings, {"allow_delete": allow_delete})
    print_report(report)
    if report.get("status") == "failed" or report.get("legend_view_id") is None:
        alert_error("Place Legend on Sheet", "\n".join(report.get("errors") or ["The legend was not created."]))
        return None
    return doc.GetElement(make_element_id(report["legend_view_id"]))


def _report_placement(source_view, legend_view, definition, viewport, warnings):
    print_report({
        "status": "placed" if viewport is not None else "not placed",
        "source_view_id": element_id_value(source_view.Id),
        "source_view_name": source_view.Name,
        "legend_view_id": None if legend_view is None else element_id_value(legend_view.Id),
        "legend_view_name": None if legend_view is None else legend_view.Name,
        "definition_name": definition["display_name"],
        "instance_count": "",
        "unique_type_count": "",
        "added": [],
        "updated": [],
        "removed": [],
        "realigned": 0,
        "warnings": list(warnings or []) + (
            [] if viewport is not None else ["The legend was not placed."]
        ),
        "errors": [],
        "notices": [] if viewport is None else ["The legend viewport was created. Future updates keep its centre."],
        "host": "",
        "version": "",
    })


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Place Legend on Sheet", str(error))
    except Exception as error:
        LOGGER.exception("Place Legend on Sheet failed")
        alert_error("Place Legend on Sheet", "Unexpected failure: {0}".format(error))
