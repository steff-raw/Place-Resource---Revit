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
    show_type_mark = ask_type_mark(config, existing)
    if show_type_mark is None:
        return None
    if not _confirm(category, config, chosen, existing, show_type_mark):
        return None
    if not _ensure_text(doc, config):
        return None
    report = build_library_legend(doc, config, chosen, sheet=None, legend_view=existing, show_type_mark=show_type_mark)
    print_library_report(report)
    if report["status"] == "failed":
        alert_error("Legend Setup", "\n".join(report["errors"]))
    return report


def run_sheet_legend(doc, uidoc, sheet, category, library_settings):
    """Place Legend: rows for one category on one sheet, then place the legend. Returns the report or None."""
    from collectors import type_marks_for_source
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
    size = choose_width(uidoc, sheet, config, existing)
    if size is None:
        return None
    width_mm, corner = size
    show_type_mark = ask_type_mark(config, existing)
    if show_type_mark is None:
        return None
    if not _ensure_text(doc, config):
        return None
    report = build_library_legend(doc, config, chosen, sheet=sheet, legend_view=existing,
                                  width_mm=width_mm, show_type_mark=show_type_mark)
    if report["status"] in ("created", "updated"):
        legend_view = doc.GetElement(existing.Id) if existing is not None else _view_by_id(doc, report["legend_view_id"])
        try:
            _put_on_sheet(doc, uidoc, sheet, legend_view, config, corner, report)
        except Exception as ex:
            report["warnings"].append("The legend was saved but not placed. {0}".format(ex))
    print_library_report(report)
    if report["status"] == "failed":
        alert_error("Place Legend on Sheet", "\n".join(report["errors"]))
    return report


def choose_width(uidoc, sheet, config, existing):
    """Ask how wide the legend is. Returns (width_mm, top-left XYZ or None), or None when cancelled.

    Drawing a box gives both the width and where the legend goes. A typed width
    keeps the usual pick-a-point placement.
    """
    from legend_library import MAX_WIDTH_CM, MIN_WIDTH_CM, parse_width_cm
    from placement_service import pick_sheet_box
    from units import internal_to_mm
    current = (read_view_payload(existing) or {}).get("width_mm") if existing is not None else None
    options = [
        ("box", "Draw a box on the sheet", "The text wraps to the box width. The legend starts at its top-left corner."),
        ("cm", "Type the width in cm", "Then pick where the legend goes."),
    ]
    if current:
        options.append(("keep", "Keep the current width ({0:g} cm)".format(round(current / 10.0, 1)), None))
    choice = dialogs.choose_command(
        "{0} legend width".format(config["name"]),
        "How wide should the legend be on the sheet?",
        options,
    )
    if choice is None:
        return None
    if choice == "keep":
        return float(current), None
    if choice == "box":
        picked = pick_sheet_box(uidoc, sheet)
        if picked is None:
            return None
        corner, width = picked
        width_mm = internal_to_mm(width)
        if width_mm < MIN_WIDTH_CM * 10:
            dialogs.alert("The box is only {0:.0f} mm wide. Draw a wider box.".format(width_mm), title="Legend width")
            return None
        return width_mm, corner
    default = "{0:g}".format(round(_stored_width(existing, config) / 10.0, 1))
    prompt = "Legend width in cm, from {0:g} to {1:g}.".format(MIN_WIDTH_CM, MAX_WIDTH_CM)
    while True:
        text = dialogs.ask_text("{0} legend width".format(config["name"]), prompt, default)
        if text is None:
            return None
        width_mm = parse_width_cm(text)
        if width_mm is not None:
            return width_mm, None
        prompt = "'{0}' is not a width from {1:g} to {2:g} cm. Type a number, e.g. 12.5.".format(
            text, MIN_WIDTH_CM, MAX_WIDTH_CM
        )
        default = text


def ask_type_mark(config, existing):
    """Ask whether the Type Mark shows above each symbol. Returns True/False, or None when cancelled.

    The last choice for this legend (or the settings default) is listed first.
    """
    stored = (read_view_payload(existing) or {}).get("show_type_mark") if existing is not None else None
    current = bool(config.get("show_type_mark", True)) if stored is None else bool(stored)
    show = ("show", "Show the Type Mark", "Turns on '{0}' on each symbol.".format(config["type_mark_visibility_parameter"]))
    hide = ("hide", "Hide the Type Mark", None)
    choice = dialogs.choose_command(
        "{0} legend".format(config["name"]),
        "Show the Type Mark above each symbol?",
        [show, hide] if current else [hide, show],
    )
    if choice is None:
        return None
    return choice == "show"


def _put_on_sheet(doc, uidoc, sheet, legend_view, config, corner, report):
    """Place the legend, or line up the one already on the sheet with a drawn box."""
    from placement_service import (
        align_top_left,
        interactive_place,
        legend_viewport_on_sheet,
        place_on_sheet,
        sheet_label,
    )
    if legend_view is None:
        return
    viewport = legend_viewport_on_sheet(doc, sheet, legend_view)
    if viewport is not None:
        if corner is None:
            report["notices"].append("The legend is already on '{0}'. Its position was kept.".format(sheet_label(sheet)))
            return
        report["warnings"].extend(align_top_left(doc, viewport, corner))
        report["notices"].append("The legend was moved to the box you drew.")
        return
    if corner is not None:
        viewport, warnings = place_on_sheet(doc, sheet, legend_view, corner)
        report["warnings"].extend(warnings or [])
        report["warnings"].extend(align_top_left(doc, viewport, corner))
        return
    viewport, warnings = interactive_place(doc, uidoc, sheet, legend_view, config, active_sheet=sheet)
    report["warnings"].extend(warnings or [])
    if viewport is None:
        report["warnings"].append("The legend was saved and was not placed on the sheet.")


def _ensure_text(doc, config):
    """Check the heading and row text types exist, asking for a style when they do not."""
    from ui_service import ensure_text_style
    styles = config["styles"]
    names = []
    if styles.get("show_heading"):
        names.append(styles["heading_text_type"])
    if styles.get("show_text", True):
        names.append(styles["text_type"])
    if not names:
        return True
    return ensure_text_style(doc, names)


def _confirm(category, config, chosen, existing, show_type_mark):
    content = "\n".join([
        "Rows: {0} types of family '{1}'".format(len(chosen), config["family_name"]),
        "Existing legend: {0}".format(existing.Name if existing is not None else "None, a new one will be made"),
        "Template legend: {0}".format(config["template_legend_name"]),
        "Scale: 1:{0}".format(config["scale"]),
        "Width: {0:g} cm".format(round(_stored_width(existing, config) / 10.0, 1)),
        "Type Mark above symbols: {0}".format("Yes" if show_type_mark else "No"),
    ])
    choice = dialogs.choose_command(
        "Legend Setup",
        "{0} the {1} legend?".format("Update" if existing is not None else "Create", category),
        [("apply", "{0} the legend".format("Update" if existing is not None else "Create"))],
        content=content,
    )
    return choice == "apply"


def _stored_width(existing, config):
    stored = (read_view_payload(existing) or {}).get("width_mm") if existing is not None else None
    return float(stored or config["layout"]["width_mm"])


def _view_by_id(doc, value):
    if value is None:
        return None
    from version_adapter import make_element_id
    return doc.GetElement(make_element_id(value))
