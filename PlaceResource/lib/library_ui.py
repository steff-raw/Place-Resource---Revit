# -*- coding: utf-8 -*-
"""Dialog flows for library legends, shared by Legend Setup and Place Legend on Sheet.

All dialogs run before any transaction. Model changes happen only in
library_legend_service.build_library_legend.
"""

import dialogs
from identity import find_library_legend, read_view_payload
from legend_library import entries_for_codes, match_type_marks
from library_legend_service import build_library_legend
from reporting import alert_error, print_library_report


def choose_category(library_settings, title="Legend Setup", prompt=None):
    """Return a category name, or None when cancelled."""
    names = list(library_settings["categories"].keys())
    labels = []
    for name in names:
        count = len(library_settings["library"].get(name) or [])
        labels.append("{0}  ({1} row{2} in the library)".format(name, count, "" if count == 1 else "s"))
    index = dialogs.choose_from_list(
        title, labels, prompt=prompt or "Choose the legend category.", button_text="Next"
    )
    return None if index is None else names[index]


def choose_rows(category, entries, preselected_codes, prompt):
    """Return the ticked library entries (library order), or None when cancelled."""
    if not entries:
        dialogs.alert(
            "The '{0}' sheet of the Excel library has no rows. Add rows (Code, Description, Graphic, "
            "Filled Region Type), save the workbook, and run the command again.".format(category),
            title="Legend library",
        )
        return None
    wanted = set(code.strip().lower() for code in preselected_codes or [])
    preselected = [index for index, entry in enumerate(entries) if entry.code.strip().lower() in wanted]
    indexes = dialogs.choose_many_from_list(
        "{0} legend rows".format(category),
        [entry.label() for entry in entries],
        preselected=preselected,
        prompt=prompt,
        button_text="Continue",
    )
    if indexes is None:
        return None
    return [entries[index] for index in indexes]


def run_setup(doc, library_settings):
    """Legend Setup: category, rows, then create or update the master legend. Returns the report or None."""
    category = choose_category(library_settings)
    if category is None:
        return None
    config = library_settings["categories"][category]
    entries = library_settings["library"].get(category) or []
    existing = find_library_legend(doc, category, None)
    stored = (read_view_payload(existing) or {}).get("codes") if existing is not None else None
    preselected = stored if stored is not None else [entry.code for entry in entries]
    chosen = choose_rows(
        category, entries, preselected,
        "Tick the rows for the {0} legend. {1}".format(
            category,
            "Ticked: the rows already in '{0}'.".format(existing.Name) if existing is not None else "All rows start ticked.",
        ),
    )
    if not chosen:
        return None
    if not _confirm(category, config, chosen, existing, None):
        return None
    report = build_library_legend(doc, config, chosen, sheet=None, legend_view=existing)
    print_library_report(report)
    if report["status"] == "failed":
        alert_error("Legend Setup", "\n".join(report["errors"]))
    return report


def run_sheet_legend(doc, uidoc, sheet, category, library_settings):
    """Place Legend: rows for one category on one sheet, then place the legend. Returns the report or None."""
    from collectors import type_marks_for_source
    from placement_service import interactive_place, legend_viewport_on_sheet, sheet_label
    config = library_settings["categories"][category]
    entries = library_settings["library"].get(category) or []
    existing = find_library_legend(doc, category, sheet)
    if existing is not None:
        preselected = (read_view_payload(existing) or {}).get("codes") or []
        why = "Ticked: the rows already in '{0}'.".format(existing.Name)
    elif config.get("revit_category"):
        marks = type_marks_for_source(doc, sheet, config["revit_category"], config["source_view_types"])
        preselected = match_type_marks(entries, marks)
        why = "Ticked: library codes that match a Type Mark in the views on this sheet ({0} found).".format(
            len(preselected)
        )
    else:
        preselected = []
        why = "Tick the rows that apply to this sheet."
    chosen = choose_rows(category, entries, preselected, "{0} Add or remove rows as needed.".format(why))
    if not chosen:
        return None
    report = build_library_legend(doc, config, chosen, sheet=sheet, legend_view=existing)
    if report["status"] in ("created", "updated"):
        legend_view = doc.GetElement(existing.Id) if existing is not None else _view_by_id(doc, report["legend_view_id"])
        if legend_view is not None and legend_viewport_on_sheet(doc, sheet, legend_view) is not None:
            report["notices"].append("The legend is already on '{0}'. Its position was kept.".format(sheet_label(sheet)))
        elif legend_view is not None:
            try:
                viewport, warnings = interactive_place(doc, uidoc, sheet, legend_view, config, active_sheet=sheet)
                report["warnings"].extend(warnings or [])
                if viewport is None:
                    report["warnings"].append("The legend was saved and was not placed on the sheet.")
            except Exception as ex:
                report["warnings"].append("The legend was saved but not placed. {0}".format(ex))
    print_library_report(report)
    if report["status"] == "failed":
        alert_error("Place Legend on Sheet", "\n".join(report["errors"]))
    return report


def _confirm(category, config, chosen, existing, sheet):
    regions = sum(1 for entry in chosen if entry.graphic == "region")
    components = len(chosen) - regions
    content = "\n".join([
        "Rows: {0} ({1} hatch, {2} legend component)".format(len(chosen), regions, components),
        "Existing legend: {0}".format(existing.Name if existing is not None else "None, a new one will be made"),
        "Template: {0}".format(config["template_legend_name"]),
        "Scale: 1:{0}".format(config["scale"]),
    ])
    choice = dialogs.choose_command(
        "Legend Setup",
        "{0} the {1} legend?".format("Update" if existing is not None else "Create", category),
        [("apply", "{0} the legend".format("Update" if existing is not None else "Create"))],
        content=content,
    )
    return choice == "apply"


def _view_by_id(doc, value):
    if value is None:
        return None
    from version_adapter import make_element_id
    return doc.GetElement(make_element_id(value))
