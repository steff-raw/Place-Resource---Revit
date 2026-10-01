# -*- coding: utf-8 -*-
"""Dialog flows for library legends, shared by Legend Setup and Place Legend on Sheet.

Rows come from the category's symbol family (one type per code). All dialogs run
before any transaction. Model changes happen only in library_legend_service.
"""

import dialogs
import trail
from identity import find_library_legend, read_view_payload
from legend_library import entries_for_codes
from library_legend_service import build_library_legend, project_library
from reporting import alert_error, print_library_report
from symbol_library import family_entries, find_family, legend_families


def choose_category(doc, library_settings, title="Legend Setup", prompt=None):
    """Return a category name, or None when cancelled. Each row shows its family and type count."""
    trail.step("reading family picks saved in the model")
    library_settings = project_library(doc, library_settings)
    names = list(library_settings["categories"].keys())
    labels = []
    details = []
    for name in names:
        config = library_settings["categories"][name]
        trail.step("reading family '{0}' for {1}".format(config["family_name"], name))
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
    trail.step("listing annotation and detail families")
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
        button_text="Select",
        details=["{0} type{1}".format(count, "" if count == 1 else "s") for _name, count in families],
        selected_index=preselected or 0,
    )
    if index is None:
        return None
    chosen = names[index]
    if chosen != current:
        from project_settings import assign_family
        trail.step("saving family pick '{0}' for {1}".format(chosen, category))
        assign_family(doc, category, chosen)
    return chosen


HEADING_FONT_ROW = "Heading font"
TEXT_FONT_ROW = "Description font"


def setup_rows(saved, families):
    """Rows of the Legend Setup window.

    ``saved`` is the project settings; ``families`` is [(category, family name, loaded)].
    Returns (groups, missing count) where groups is [(title, [(text, state)])].
    """
    heading = saved.get("heading_text_type")
    body = saved.get("text_type")
    fonts = [
        ("{0} - {1}".format(HEADING_FONT_ROW, heading or (body and "Same as description font") or "Not set"),
         "ok" if (heading or body) else "missing"),
        ("{0} - {1}".format(TEXT_FONT_ROW, body or "Not set"), "ok" if body else "missing"),
    ]
    rows = []
    missing = 0 if body else 1
    for category, family, loaded in families:
        if loaded:
            rows.append(("{0} - {1}".format(category, family), "ok"))
        else:
            rows.append(("{0} - Not loaded".format(category), "missing"))
            missing += 1
    return [("Fonts", fonts), ("Legend families", rows)], missing


def run_setup(doc, library_settings):
    """Legend Setup: the heading and description fonts and the symbol family for each legend category.

    Shows one list: fonts, a separator, then one row per category in green (family
    loaded) or red (not loaded). Pick a row and press Change; press Done to finish.
    Everything is saved in the model, so it goes to central with the next sync.
    """
    from project_settings import read
    from ui_service import choose_text_type
    while True:
        library = project_library(doc, library_settings)
        names = list(library["categories"].keys())
        families = []
        for name in names:
            family = library["categories"][name]["family_name"]
            families.append((name, family, find_family(doc, family) is not None))
        groups, missing = setup_rows(read(doc), families)
        prompt = ("All set. Press Done to finish, or pick a row to change it." if not missing else
                  "{0} still to set (red). Pick a row and press Change. Press Done when finished.".format(missing))
        index = dialogs.choose_from_groups(
            "Legend Setup", groups, prompt=prompt + " Saved in this model.",
            button_text="Change", cancel_text="Done",
        )
        if index is None:
            return
        if index == 0:
            choose_text_type(doc, key="heading_text_type")
        elif index == 1:
            choose_text_type(doc, key="text_type")
        else:
            category = names[index - 2]
            choose_family(doc, category, dict(library["categories"][category]))


def choose_sheet(doc):
    """Pick a sheet from all sheets in the model. Returns the sheet, or None when cancelled."""
    from placement_service import all_sheets, sheet_label
    sheets = all_sheets(doc)
    if not sheets:
        dialogs.alert("This model has no sheets.", title="Place Legend on Sheet")
        return None
    index = dialogs.choose_from_list(
        "Pick the sheet",
        [sheet_label(sheet) for sheet in sheets],
        prompt="Pick the sheet for the legends. Tip: open the sheet first to skip this step.",
        button_text="Next",
    )
    return None if index is None else sheets[index]


def run_sheet_legend(doc, uidoc, sheet, category, library_settings):
    """Place Legend: rows for one category on one sheet, then place the legend. Returns the report or None.

    For model categories (Walls, Doors, ...) the rows are the family types whose name
    matches a Type Mark in the views on the sheet, with no tick list. Other categories
    (Fire Strategy, ...) have nothing to match, so every type of the family is used.
    """
    config = dict(project_library(doc, library_settings)["categories"][category])
    if find_family(doc, config["family_name"]) is None:
        family = choose_family(doc, category, config)
        if family is None:
            return None
        config["family_name"] = family
    existing = find_library_legend(doc, category, sheet)
    if config.get("revit_category"):
        chosen = _rows_from_sheet(doc, sheet, config)
    else:
        chosen = _all_rows(doc, config)
    if not chosen:
        return None
    size = choose_width(uidoc, sheet, config, existing)
    if size is None:
        return None
    width_mm, corner = size
    show_type_mark = ask_type_mark(config, existing)
    if show_type_mark is None:
        return None
    headings = ask_headings(doc, config, existing)
    if headings is None:
        return None
    if not _ensure_text(doc, config):
        return None
    trail.step("building sheet legend for {0}".format(category))
    report = build_library_legend(doc, config, chosen, sheet=sheet, legend_view=existing,
                                  width_mm=width_mm, show_type_mark=show_type_mark, headings=headings)
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


def _all_rows(doc, config):
    """Every type of the family, in family order. Shows a message and returns None when there are none."""
    entries, problems = family_entries(doc, config)
    if problems:
        dialogs.alert("\n".join(problems), title="Legend library")
        return None
    if not entries:
        dialogs.alert(
            "Family '{0}' has no types. Add one type per Type Mark, named after it (e.g. IWS-105).".format(
                config["family_name"]),
            title="Legend library",
        )
        return None
    return entries


def _rows_from_sheet(doc, sheet, config):
    """Family entries matching the Type Marks in the sheet's views. Shows a message and returns None when none match."""
    from library_legend_service import sheet_codes
    from placement_service import sheet_label
    entries, problems = family_entries(doc, config)
    if problems:
        dialogs.alert("\n".join(problems), title="Legend library")
        return None
    from collectors import sheet_source_views, type_marks_for_source
    trail.step("reading Type Marks in the views on the sheet")
    codes = sheet_codes(doc, sheet, config, entries)
    if not codes:
        views = sheet_source_views(doc, sheet, config["source_view_types"])
        marks = type_marks_for_source(doc, sheet, config["revit_category"], config["source_view_types"])
        dialogs.alert(
            "None of the {0} Type Marks on sheet {1} matches a type of family '{2}'.\n\n"
            "Views checked: {3}\n\n"
            "Type Marks found: {4}\n\n"
            "Family types: {5}".format(
                config["name"].lower(), sheet_label(sheet), config["family_name"],
                _short_list([view.Name for view in views], "none (no {0} on this sheet)".format(
                    " / ".join(config["source_view_types"]))),
                _short_list(marks, "none (the {0} in these views have no Type Mark)".format(config["name"].lower())),
                _short_list([entry.code + (" ({0})".format(entry.mark) if entry.mark and entry.mark != entry.code else "")
                             for entry in entries], "none"),
            ),
            title="{0} legend".format(config["name"]),
        )
        return None
    return entries_for_codes(entries, codes)


def _short_list(items, empty_text, limit=15):
    items = list(items)
    if not items:
        return empty_text
    text = ", ".join(items[:limit])
    return text + (" and {0} more".format(len(items) - limit) if len(items) > limit else "")


def ask_headings(doc, config, existing):
    """Ask for the title and the two column headings. Returns a dict, or None when cancelled.

    The boxes start with this legend's headings, else the ones last typed for this
    category (saved in the model), else the defaults from the settings. What is typed
    is saved for next time.
    """
    from legend_library import clean_headings, default_headings
    from project_settings import save_headings, saved_headings
    current = clean_headings(saved_headings(doc, config["name"]), default_headings(config))
    if existing is not None:
        current = clean_headings((read_view_payload(existing) or {}).get("headings"), current)
    values = dialogs.ask_fields(
        "{0} legend headings".format(config["name"]),
        "Headings for the legend. Leave a box empty to leave that heading out. "
        "They are remembered for the next {0} legend.".format(config["name"]),
        [
            ("Main heading", current["title"]),
            ("Graphic column heading", current["graphic"]),
            ("Description column heading", current["description"]),
        ],
    )
    if values is None:
        return None
    headings = {"title": values[0].strip(), "graphic": values[1].strip(), "description": values[2].strip()}
    trail.step("saving headings for {0}".format(config["name"]))
    save_headings(doc, config["name"], headings)
    return headings


def ask_type_mark(config, existing):
    """Ask whether the Type Mark shows above each symbol. Returns True/False, or None when cancelled.

    The last choice for this legend (or the settings default) is listed first.
    """
    stored = (read_view_payload(existing) or {}).get("show_type_mark") if existing is not None else None
    current = bool(config.get("show_type_mark", True)) if stored is None else bool(stored)
    show = ("show", "Show the Type Mark", "Applies to the whole legend.")
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
        set_viewport_type,
        sheet_label,
    )
    if legend_view is None:
        return
    viewport = legend_viewport_on_sheet(doc, sheet, legend_view)
    if viewport is not None:
        report["warnings"].extend(set_viewport_type(doc, viewport, config.get("viewport_type_name")))
        if corner is None:
            report["notices"].append("The legend is already on '{0}'. Its position was kept.".format(sheet_label(sheet)))
            return
        report["warnings"].extend(align_top_left(doc, viewport, corner))
        report["notices"].append("The legend was moved to the box you drew.")
        return
    if corner is not None:
        viewport, warnings = place_on_sheet(doc, sheet, legend_view, corner)
        report["warnings"].extend(warnings or [])
        # The title is hidden first, so the box outline used for lining up is the legend itself.
        report["warnings"].extend(set_viewport_type(doc, viewport, config.get("viewport_type_name")))
        report["warnings"].extend(align_top_left(doc, viewport, corner))
        return
    viewport, warnings = interactive_place(doc, uidoc, sheet, legend_view, config, active_sheet=sheet)
    report["warnings"].extend(warnings or [])
    if viewport is None:
        report["warnings"].append("The legend was saved and was not placed on the sheet.")
    else:
        report["warnings"].extend(set_viewport_type(doc, viewport, config.get("viewport_type_name")))


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
    trail.step("checking text types: {0}".format(", ".join(names)))
    return ensure_text_style(doc, names)


def _active_sheet(doc):
    from version_adapter import get_db
    view = getattr(doc, "ActiveView", None)
    try:
        if view is not None and view.ViewType == get_db().ViewType.DrawingSheet:
            return view
    except Exception:
        pass
    return None


def _stored_width(existing, config):
    stored = (read_view_payload(existing) or {}).get("width_mm") if existing is not None else None
    return float(stored or config["layout"]["width_mm"])


def _view_by_id(doc, value):
    if value is None:
        return None
    from version_adapter import make_element_id
    return doc.GetElement(make_element_id(value))
