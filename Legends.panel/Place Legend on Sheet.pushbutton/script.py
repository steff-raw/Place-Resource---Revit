#! python3
# -*- coding: utf-8 -*-
"""Place the generated legend for a model view onto a sheet.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Place Legend\non Sheet"
__doc__ = (
    "Place legends on a sheet. On a sheet, first choose which legends it shows: the type legend "
    "from its views and any library legend (Walls, Fire Strategy, ...)."
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

from configuration import load_settings
from errors import LegendToolError
from identity import find_legend
from legend_service import create_or_update, prepare_plan
from logging_service import get_logger
from placement_service import interactive_place, model_viewports_on_sheet, sheet_label
from reporting import alert_error, print_report
from ui_service import choose_definition, choose_named_item, confirm_delete, ensure_text_style
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


VIEW_TYPE_LEGEND = "Type legend from the views on this sheet (legends.json)"


def _place_from_sheet(doc, uidoc, sheet, settings):
    """First ask which legend(s) this sheet shows, then build and place each one."""
    from dialogs import choose_many_from_list
    from identity import find_library_legend
    library_settings, library_error = _load_library()
    labels = [VIEW_TYPE_LEGEND]
    categories = []
    preselected = []
    if library_settings is not None:
        for category in library_settings["categories"]:
            categories.append(category)
            labels.append("Library: {0}".format(category))
            if find_library_legend(doc, category, sheet) is not None:
                preselected.append(len(labels) - 1)
    prompt = "Tick the legends to show on sheet {0}. Ticked: library legends already made for this sheet.".format(
        sheet_label(sheet)
    )
    if library_error:
        prompt = "The Excel legend library could not be loaded, so only the type legend is offered. {0}".format(
            library_error
        )
    chosen = choose_many_from_list("Place Legend on Sheet", labels, preselected=preselected, prompt=prompt)
    if not chosen:
        return
    from library_ui import run_sheet_legend
    for index in chosen:
        # One legend failing does not stop the others. Each one is its own undoable change.
        try:
            if index == 0:
                _place_view_legend_from_sheet(doc, uidoc, sheet, settings)
            else:
                run_sheet_legend(doc, uidoc, sheet, categories[index - 1], library_settings)
        except LegendToolError as error:
            LOGGER.error("%s", error)
            alert_error("Place Legend on Sheet", "{0}\n\n{1}".format(labels[index], error))


def _load_library():
    from legend_library import load_library_settings
    try:
        return load_library_settings(), None
    except LegendToolError as error:
        LOGGER.warning("Legend library not loaded: %s", error)
        return None, str(error)


def _place_view_legend_from_sheet(doc, uidoc, sheet, settings):
    pairs = model_viewports_on_sheet(doc, sheet, settings["data"]["legend_definitions"])
    if not pairs:
        raise LegendToolError(
            "Sheet '{0}' has no plan, section, or elevation viewport supported by the settings file.".format(
                sheet_label(sheet)
            )
        )
    labels = ["All views on this sheet (combined legend)"]
    labels.extend("{0} ({1})".format(view.Name, view_type_token(view)) for _viewport, view in pairs)
    selected = choose_named_item(
        "Select the source for the legend",
        list(range(len(labels))),
        lambda index: labels[index],
    )
    if selected is None:
        return
    # Index 0 uses the sheet itself as the source: types from every supported view on it are merged.
    source_view = sheet if selected == 0 else pairs[selected - 1][1]
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
    from dialogs import ask_yes_no
    legend_view = find_legend(doc, source_view, definition["id"])
    if legend_view is not None:
        return legend_view
    create = ask_yes_no(
        "Place Legend on Sheet",
        "There is no generated legend for '{0}' using '{1}'. Create it now?".format(
            source_view.Name, definition["display_name"]
        ),
        yes_label="Create the legend",
        no_label="Cancel",
    )
    if not create:
        return None
    styles = definition["styles"]
    if not ensure_text_style(doc, [styles["text_note_type"], styles["header_text_note_type"]]):
        return None
    plan = prepare_plan(doc, source_view, definition, settings)
    allow_delete = False
    if plan["to_remove"] and definition["update"].get("remove_unused_entries"):
        allow_delete = True
        if definition["update"].get("confirm_before_deleting"):
            labels = []
            for type_id in plan["to_remove"]:
                element = doc.GetElement(make_element_id(type_id))
                labels.append(element.Name if element is not None else str(type_id))
            allow_delete = bool(confirm_delete(labels))
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
