# -*- coding: utf-8 -*-
"""Dialog flows for library legends, shared by Legend Setup and Place Legend on Sheet.

Rows come from the category's symbol family (one type per code). All dialogs run
before any transaction. Model changes happen only in library_legend_service.
"""

import dialogs
from identity import find_library_legend, read_view_payload
from legend_library import match_type_marks
from library_legend_service import build_library_legend, project_library
from reporting import alert_error, print_library_report
from symbol_library import family_entries, find_family, legend_families


def choose_category(doc, library_settings, title="Legend Setup", prompt=None):
    """Return a category name, or None when cancelled. Each row shows its family and type count."""
    library_settings = project_library(doc, library_settings)
    names = list(library_settings["categories"].keys())
    labels = []
    details = []
    for name in names:
        config = library_settings["categories"][name]
        entries, problems = family_entries(doc, config)
        labels.append(name)
        if problems:
            details.append("family '{0}' not loaded".format(config["family_name"]))
        else:
            details.append("{0} type{1} in '{2}'".format(len(entries), "" if len(entries) == 1 else "s", config["family_name"]))
    index = dialogs.choose_from_list(
        title, labels, prompt=prompt or "Choose the legend category.", button_text="Next", details=details
    )
    return None if index is None else names[index]


def choose_family(doc, category, config):
    """Pick the symbol family for a category from the families loaded in the model and save it.

    Returns the family name, or None when cancelled or no suitable family is loaded.
    """
    families = legend_families(doc)
    if not families:
        dialogs.alert(
            "No Generic Annotation or Detail Item families are loaded in this model. "
            "Load your legend symbol family first.",
            title="Legend Setup",
        )
        return None
    names = [name for name, _count in families]
    current = config["family_name"]
    preselected = None
    for index, name in enumerate(names):
        if name.strip().lower() == current.strip().lower():
            preselected = index
            break
    index = dialogs.choose_from_list(
        "{0} legend family".format(category),
        names,
        prompt="Pick the symbol family for {0}. Its type names are the Type Marks. "
               "Current: {1}".format(category, current if preselected is not None else "none"),
        button_text="Next",
        details=["{0} type{1}".format(count, "" if count == 1 else "s") for _name, count in families],
        selected_index=preselected or 0,
    )
    if index is None:
        return None
    chosen = names[index]
    if chosen != current:
        from project_settings import assign_family
        assign_family(doc, category, chosen)
    return chosen


def choose_rows(doc, config, preselected_codes, prompt):
    """Return the ticked entries (family order), or None when cancelled or the family is unusable."""
    entries, problems = family_entries(doc, config)
    if problems:
        dialogs.alert("\n".join(problems), title="Legend library")
        return None
    if not entries:
        dialogs.alert(
            "Family '{0}' has no types. Add one type per Type Mark, named after it (e.g. IWS-105).".format(
                config["family_name"]
            ),
            title="Legend library",
        )
        return None
    wanted = set(code.strip().lower() for code in preselected_codes or [])
    preselected = [index for index, entry in enumerate(entries) if entry.code.strip().lower() in wanted]
    indexes = dialogs.choose_many_from_list(
        "{0} legend rows".format(config["name"]),
        [entry.label() for entry in entries],
        preselected=preselected,
        prompt=prompt,
        button_text="Continue",
    )
    if indexes is None:
        return None
    return [entries[index] for index in indexes]


def run_setup(doc, library_settings):
    """Legend Setup: category, rows, then create or update the category legend (not tied to a sheet). Returns the report or None."""
    category = choose_category(doc, library_settings)
    if category is None:
        return None
    config = dict(project_library(doc, library_settings)["categories"][category])
    family = choose_family(doc, category, config)
    if family is None:
        return None
    config["family_name"] = family
    existing = find_library_legend(doc, category, None)
    stored = (read_view_payload(existing) or {}).get("codes") if existing is not None else None
    if stored is None:
        entries, _problems = family_entries(doc, config)
        stored = [entry.code for entry in entries]
    chosen = choose_rows(
        doc, config, stored,
        "Types of family '{0}'. {1}".format(
            config["family_name"],
            "Ticked: the rows already in '{0}'.".format(existing.Name) if existing is not None else "All types start ticked.",
        ),
    )
    if not chosen:
        return None
    if not _confirm(category, config, chosen, existing):
        return None
    if not _ensure_text(doc, config):
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
    config = dict(project_library(doc, library_settings)["categories"][category])
    if find_family(doc, config["family_name"]) is None:
        family = choose_family(doc, category, config)
        if family is None:
            return None
        config["family_name"] = family
    existing = find_library_legend(doc, category, sheet)
    if existing is not None:
        preselected = (read_view_payload(existing) or {}).get("codes") or []
        why = "Ticked: the rows already in '{0}'.".format(existing.Name)
    elif config.get("revit_category"):
        entries, _problems = family_entries(doc, config)
        marks = type_marks_for_source(doc, sheet, config["revit_category"], config["source_view_types"])
        preselected = match_type_marks(entries, marks)
        why = "Ticked: types that match a Type Mark in the views on this sheet ({0} found).".format(len(preselected))
    else:
        preselected = []
        why = "Tick the rows that apply to this sheet."
    chosen = choose_rows(
        doc, config, preselected,
        "Types of family '{0}'. {1} Add or remove rows as needed.".format(config["family_name"], why),
    )
    if not chosen:
        return None
    if not _ensure_text(doc, config):
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


def _ensure_text(doc, config):
    """The heading is the only text the tool writes; the family draws everything else."""
    from ui_service import ensure_text_style
    styles = config["styles"]
    if not styles.get("show_heading"):
        return True
    return ensure_text_style(doc, [styles["heading_text_type"]])


def _confirm(category, config, chosen, existing):
    content = "\n".join([
        "Rows: {0} types of family '{1}'".format(len(chosen), config["family_name"]),
        "Existing legend: {0}".format(existing.Name if existing is not None else "None, a new one will be made"),
        "Template legend: {0}".format(config["template_legend_name"]),
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
