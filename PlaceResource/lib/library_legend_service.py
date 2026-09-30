# -*- coding: utf-8 -*-
"""Build legends from the category's symbol family.

Each chosen family type (one per Type Mark, e.g. IWS-105) is placed once in the
legend, stacked top to bottom under an optional heading. The family draws the
graphic. The tool writes the description from the type parameter as a text note
to the right of the graphic, wrapped to fit the legend width.

Everything is resolved before a transaction starts. The whole change is one
transaction group. Only elements this tool marked are deleted on update.
"""

from errors import LegendOperationError, LegendToolError
from identity import (
    ROLE_LIBRARY_LEGEND,
    build_library_element_payload,
    build_library_view_payload,
    collect_managed_elements,
    content_hash,
    delete_managed_elements,
    find_library_legend,
    iter_generated_legends,
    read_view_payload,
    write_element_identity,
    write_view_identity,
)
from legend_component_service import LegendComponentService, resolve_text_type, unique_view_name
from legend_library import (
    apply_pattern,
    entries_for_codes,
    format_text,
    missing_codes,
    normalize_code,
    row_heights,
    stack_rows,
    text_width_mm,
)
from logging_service import get_logger
from trail import step
from symbol_library import family_entries, symbols_by_code
from transactions import TransactionContext, TransactionGroupContext
from units import internal_to_mm, mm_to_internal
from version_adapter import element_id_value, get_db

LOGGER = get_logger("library_legend_service")

# Roles written by this and earlier versions (Excel and master-legend rows), so updates clear them all.
LIBRARY_ROLES = (
    "library_row", "library_heading",
    "library_graphic", "library_title", "library_description", "library_seed",
    "library_text",
)
SOURCE_FAMILY = "family"


def legend_width_mm(config, width_mm=None):
    """The width to build with: the one given, else the default from the settings."""
    return float(width_mm) if width_mm else float(config["layout"]["width_mm"])


def type_mark_choice(config, show_type_mark=None):
    """The Type Mark toggle to build with: the one given, else the default from the settings."""
    return bool(config.get("show_type_mark", True)) if show_type_mark is None else bool(show_type_mark)


def library_hash(category, config, entries, width_mm=None, show_type_mark=None):
    """Hash of what a library legend shows, used to skip unchanged legends."""
    records = [{"type_id": index, "display": {"row": entry.as_hash_record()}} for index, entry in enumerate(entries)]
    return content_hash(
        "library:{0}".format(category),
        "2.1",
        records,
        {"family": config["family_name"], "layout": config["layout"], "styles": config["styles"],
         "width_mm": legend_width_mm(config, width_mm),
         "show_type_mark": type_mark_choice(config, show_type_mark)},
    )


def prepare(doc, config, entries, need_template):
    """Resolve family types, heading text type and template. Nothing in the model changes."""
    problems = []
    resolved = {"problems": problems, "symbols": {}, "heading_type": None, "text_type": None, "template": None}
    resolved["symbols"] = symbols_by_code(doc, entries)
    missing = [entry.code for entry in entries if entry.code not in resolved["symbols"]]
    if missing:
        problems.append(
            "Family '{0}' has no type called {1}. Reload the family and try again.".format(
                config["family_name"], ", ".join(missing)
            )
        )
    if config["styles"].get("show_heading"):
        try:
            resolved["heading_type"] = resolve_text_type(doc, config["styles"]["heading_text_type"])
        except LegendOperationError as ex:
            problems.append(str(ex))
    if config["styles"].get("show_text", True):
        try:
            resolved["text_type"] = resolve_text_type(doc, config["styles"]["text_type"])
        except LegendOperationError as ex:
            if str(ex) not in problems:
                problems.append(str(ex))
    if need_template:
        try:
            resolved["template"] = find_source_legend(doc, config["template_legend_name"])
        except LegendOperationError as ex:
            problems.append(str(ex))
    return resolved


def find_source_legend(doc, preferred_name):
    """Pick the legend view that a new library legend is copied from.

    Revit's API cannot make a legend view from nothing, only copy one. The legend
    named ``preferred_name`` is used when it exists, otherwise any legend view in
    the model. Only the view is copied, never its contents.
    """
    DB = get_db()
    legends = []
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            if view.IsTemplate or view.ViewType != DB.ViewType.Legend:
                continue
            legends.append(view)
        except Exception:
            continue
    choice = pick_source_legend([view.Name for view in legends], preferred_name)
    if choice is None:
        raise LegendOperationError(
            "This model has no legend views. Revit cannot make the first one by code: "
            "go to View > Legends > Legend, click OK, then run this again. Any name works. "
            "This is needed once per model."
        )
    return legends[choice]


def pick_source_legend(names, preferred_name):
    """Index of the legend to copy: the preferred name, else the first by name. None when there are none."""
    if not names:
        return None
    for index, name in enumerate(names):
        if name == preferred_name:
            return index
    return min(range(len(names)), key=lambda index: names[index].lower())


def build_library_legend(doc, config, entries, sheet=None, legend_view=None, width_mm=None, show_type_mark=None):
    """Create or update a library legend. Returns a report dictionary.

    ``sheet`` None builds the category legend that is not tied to a sheet.
    ``width_mm`` is the legend width on paper. None uses the width stored on the
    legend, then layout.width_mm from the settings. ``show_type_mark`` works the
    same way with show_type_mark.
    """
    category = config["name"]
    existing = legend_view or find_library_legend(doc, category, sheet)
    report = {
        "status": "failed",
        "category": category,
        "sheet": _sheet_label(sheet),
        "legend_view_id": element_id_value(existing.Id) if existing is not None else None,
        "legend_view_name": existing.Name if existing is not None else None,
        "codes": [entry.code for entry in entries],
        "width_mm": None,
        "show_type_mark": None,
        "warnings": [],
        "errors": [],
        "notices": [],
    }
    if not entries:
        report["status"] = "skipped"
        report["warnings"].append("No rows were ticked, so the legend was not changed.")
        return report
    stored = (read_view_payload(existing) or {}) if existing is not None else {}
    if not width_mm:
        width_mm = stored.get("width_mm")
    width_mm = legend_width_mm(config, width_mm)
    if show_type_mark is None:
        show_type_mark = stored.get("show_type_mark")
    show_type_mark = type_mark_choice(config, show_type_mark)
    report["width_mm"] = width_mm
    report["show_type_mark"] = show_type_mark
    resolved = prepare(doc, config, entries, need_template=existing is None)
    if resolved["problems"]:
        report["errors"].extend(resolved["problems"])
        report["errors"].append("Nothing was changed in the model.")
        return report
    try:
        view = _run(doc, config, entries, sheet, existing, resolved, report, width_mm, show_type_mark)
    except LegendToolError as ex:
        report["errors"].append(str(ex))
        report["errors"].append("The change was undone. The model is as it was before.")
        return report
    except Exception as ex:
        LOGGER.exception("Library legend failed")
        report["errors"].append("Something went wrong: {0}".format(ex))
        report["errors"].append("The change was undone.")
        return report
    report["status"] = "created" if existing is None else "updated"
    report["legend_view_id"] = element_id_value(view.Id)
    report["legend_view_name"] = view.Name
    return report


def project_library(doc, library_settings):
    """Apply the symbol families picked for this model to the library settings."""
    from legend_library import with_families
    from project_settings import family_assignments
    try:
        assignments = family_assignments(doc)
    except Exception:
        assignments = {}
    return with_families(library_settings, assignments)


def update_all_library(doc, library_settings):
    """Rebuild library legends whose rows changed. Graphic changes come from the family itself."""
    library_settings = project_library(doc, library_settings)
    summary = {"updated": [], "unchanged": [], "skipped": [], "failed": [], "warnings": []}
    for view, payload in list(iter_generated_legends(doc, ROLE_LIBRARY_LEGEND)):
        category = payload.get("category")
        config = library_settings["categories"].get(category)
        if config is None:
            summary["skipped"].append({"legend": view.Name, "reason": "Category '{0}' is not in the settings.".format(category)})
            continue
        sheet = _resolve_sheet(doc, payload)
        if payload.get("sheet_unique_id") and sheet is None:
            summary["skipped"].append({"legend": view.Name, "reason": "Its sheet was deleted."})
            continue
        library, problems = family_entries(doc, config)
        if problems:
            summary["skipped"].append({"legend": view.Name, "reason": " ".join(problems)})
            continue
        codes = payload.get("codes") or []
        gone = missing_codes(library, codes)
        if gone:
            summary["warnings"].append("'{0}': types no longer in family '{1}': {2}.".format(
                view.Name, config["family_name"], ", ".join(gone)
            ))
        entries = entries_for_codes(library, codes)
        width_mm = payload.get("width_mm")
        show_type_mark = payload.get("show_type_mark")
        if payload.get("source") == SOURCE_FAMILY and payload.get("content_hash") == library_hash(
                category, config, entries, width_mm, show_type_mark):
            summary["unchanged"].append({"legend": view.Name})
            continue
        report = build_library_legend(doc, config, entries, sheet=sheet, legend_view=view,
                                      width_mm=width_mm, show_type_mark=show_type_mark)
        target = summary["failed"] if report["status"] == "failed" else summary["updated"]
        target.append({"legend": view.Name, "status": report["status"], "errors": report["errors"]})
        summary["warnings"].extend(report["warnings"])
    return summary


def audit_library(doc, library_settings):
    """Read-only comparison of library legends with their families and the model."""
    library_settings = project_library(doc, library_settings)
    rows = []
    for view, payload in iter_generated_legends(doc, ROLE_LIBRARY_LEGEND):
        category = payload.get("category")
        config = library_settings["categories"].get(category)
        codes = payload.get("codes") or []
        sheet = _resolve_sheet(doc, payload)
        if config is not None:
            library, problems = family_entries(doc, config)
        else:
            library, problems = [], ["Category is not in the settings."]
        entries = entries_for_codes(library, codes)
        row = {
            "legend": view.Name,
            "legend_view_id": element_id_value(view.Id),
            "category": category,
            "source": "family '{0}'".format(config["family_name"]) if config is not None else "unknown",
            "problem": " ".join(problems) or None,
            "sheet": _sheet_label(sheet) if sheet is not None else ("Deleted sheet" if payload.get("sheet_unique_id") else "Master"),
            "codes": codes,
            "missing_codes": missing_codes(library, codes) if not problems else [],
            "unlisted_marks": [],
            "outdated": config is not None and not problems and (
                payload.get("source") != SOURCE_FAMILY
                or payload.get("content_hash") != library_hash(
                    category, config, entries, payload.get("width_mm"), payload.get("show_type_mark"))
            ),
            "updated_utc": payload.get("updated_utc"),
        }
        if config is not None and config.get("revit_category") and sheet is not None and not problems:
            try:
                from collectors import type_marks_for_source
                marks = type_marks_for_source(doc, sheet, config["revit_category"], config["source_view_types"])
                shown = set(normalize_code(code) for code in codes)
                known = set(normalize_code(entry.code) for entry in library)
                row["unlisted_marks"] = [mark for mark in marks if normalize_code(mark) in known and normalize_code(mark) not in shown]
            except Exception as ex:
                row["unlisted_marks"] = ["Type Marks could not be read: {0}".format(ex)]
        rows.append(row)
    return rows


def _run(doc, config, entries, sheet, existing, resolved, report, width_mm, show_type_mark):
    from legend_service import _capture_viewports, _restore_viewports
    DB = get_db()
    category = config["name"]
    codes = [entry.code for entry in entries]
    viewports = []
    with TransactionGroupContext(doc, "Place Resource: {0} legend".format(category)):
        with TransactionContext(doc, "Prepare library legend") as transaction:
            if existing is None:
                step("copying the template legend")
                view = _new_legend(doc, resolved["template"], config, sheet, report)
            else:
                view = existing
                viewports = _capture_viewports(doc, view)
                doomed = [element for element, payload in collect_managed_elements(doc, view)
                          if payload.get("role") in LIBRARY_ROLES]
                if doomed:
                    step("removing {0} old legend elements".format(len(doomed)))
                    delete_managed_elements(doc, doomed)
            payload = build_library_view_payload(category, codes, sheet, library_hash(category, config, entries, width_mm, show_type_mark))
            payload["source"] = SOURCE_FAMILY
            payload["width_mm"] = width_mm
            payload["show_type_mark"] = show_type_mark
            payload["family_name"] = config["family_name"]
            step("saving legend data in the model")
            if write_view_identity(view, payload, doc) == "json_registry":
                report["warnings"].append(
                    "Could not save the legend's settings inside the model. They were saved in a local file "
                    "instead, which does not go with the model if it is moved or shared."
                )
        report["warnings"].extend(transaction.warnings)

        placed = []
        heading = None
        with TransactionContext(doc, "Place legend symbols") as transaction:
            origin = DB.XYZ(0, 0, 0)
            service = LegendComponentService(doc, view)
            if resolved["heading_type"] is not None:
                step("adding heading text")
                heading = service.create_text(origin, category, resolved["heading_type"].Id, 0)
                write_element_identity(heading, build_library_element_payload(category, None, "library_heading"))
            for entry in entries:
                symbol = resolved["symbols"][entry.code]
                step("placing symbol {0}".format(entry.code))
                instance = _place_symbol(doc, view, symbol, origin, entry.code)
                write_element_identity(instance, build_library_element_payload(category, entry.code, "library_row"))
                placed.append((entry, instance))
            step("setting Yes/No parameters")
            _set_toggles([instance for _entry, instance in placed], config, show_type_mark, report)
            step("regenerating after symbols")
            doc.Regenerate()
        report["warnings"].extend(transaction.warnings)

        texts = {}
        with TransactionContext(doc, "Add legend text") as transaction:
            if resolved["text_type"] is not None:
                step("adding description text")
                texts = _add_texts(doc, view, config, placed, resolved["text_type"], width_mm, report)
                doc.Regenerate()
        report["warnings"].extend(transaction.warnings)

        with TransactionContext(doc, "Arrange legend symbols") as transaction:
            step("arranging rows")
            _arrange(doc, view, config, heading, placed, texts, report)
            if viewports:
                _restore_viewports(doc, viewports, report)
            doc.Regenerate()
        report["warnings"].extend(transaction.warnings)
    return view


def _place_symbol(doc, view, symbol, origin, code):
    """Place one annotation symbol in the legend view. (verify: NewFamilyInstance in legend views)"""
    try:
        if not symbol.IsActive:
            symbol.Activate()
    except Exception:
        pass
    try:
        return doc.Create.NewFamilyInstance(origin, symbol, view)
    except Exception as ex:
        raise LegendOperationError(
            "Revit could not place '{0}' in legend '{1}'. The family must be a Generic Annotation. {2}".format(
                code, view.Name, ex
            )
        )


def _set_toggles(instances, config, show_type_mark, report):
    """Set the family's Yes/No instance parameters: Type Mark label as chosen, description label always off.

    The tool writes the description itself, so the family label stays hidden.
    A missing or read-only parameter gives one warning, not an error.
    """
    wanted = (
        (config["type_mark_visibility_parameter"], 1 if show_type_mark else 0),
        (config["text_visibility_parameter"], 0),
    )
    problems = set()
    for instance in instances:
        for name, value in wanted:
            parameter = None
            try:
                parameter = instance.LookupParameter(name)
            except Exception:
                pass
            if parameter is None or getattr(parameter, "IsReadOnly", False):
                problems.add(name)
                continue
            try:
                parameter.Set(value)
            except Exception:
                problems.add(name)
    for name in sorted(problems):
        report["warnings"].append(
            "Could not set '{0}' in this legend. Check it is a Yes/No instance parameter in family '{1}'.".format(
                name, config["family_name"]
            )
        )


def _graphic_column(service, placed):
    """Width of the widest graphic in view units (0 when none can be measured)."""
    widths = [measured["width"] for measured in (service.measure(instance) for _entry, instance in placed) if measured]
    return max(widths) if widths else 0.0


def _add_texts(doc, view, config, placed, text_type, width_mm, report):
    """Write each row's text as a note wrapped to the space left of the legend width. Returns {code: note}."""
    service = LegendComponentService(doc, view)
    scale = _scale(view, config)
    graphic_mm = internal_to_mm(_graphic_column(service, placed) / scale)
    try:
        text_mm = text_width_mm(width_mm, graphic_mm, config["layout"]["text_gap_mm"])
    except ValueError as ex:
        raise LegendOperationError(str(ex))
    origin = get_db().XYZ(0, 0, 0)
    texts = {}
    empty = []
    for entry, _instance in placed:
        text = format_text(config["layout"]["text_pattern"], entry)
        if not text:
            empty.append(entry.code)
            continue
        # TextNote.Width is on paper, so the width is not multiplied by the view scale.
        note = service.create_text(origin, text, text_type.Id, mm_to_internal(text_mm))
        write_element_identity(note, build_library_element_payload(config["name"], entry.code, "library_text"))
        texts[entry.code] = note
    if empty:
        report["warnings"].append(
            "No text for {0}. Fill in '{1}' on those family types.".format(
                ", ".join(empty), config["description_parameter"]
            )
        )
    return texts


def _arrange(doc, view, config, heading, placed, texts, report):
    service = LegendComponentService(doc, view)
    scale = _scale(view, config)
    row_gap = mm_to_internal(config["layout"]["row_gap_mm"]) * scale
    heading_gap = mm_to_internal(config["layout"]["heading_gap_mm"]) * scale
    text_x = _graphic_column(service, placed) + mm_to_internal(config["layout"]["text_gap_mm"]) * scale
    heading_height = None
    if heading is not None:
        measured = service.measure(heading)
        heading_height = measured["height"] if measured is not None else 0.0
        if measured is not None:
            service.move_top_left(heading, 0.0, 0.0)
    graphic_heights = []
    text_heights = []
    for entry, instance in placed:
        measured = service.measure(instance)
        if measured is None:
            report["warnings"].append("'{0}' shows nothing in the legend. Check the family type.".format(entry.code))
        graphic_heights.append(measured["height"] if measured is not None else 0.0)
        note = texts.get(entry.code)
        measured_text = service.measure(note) if note is not None else None
        text_heights.append(measured_text["height"] if measured_text is not None else 0.0)
    tops, _bottom = stack_rows(row_heights(graphic_heights, text_heights), row_gap, heading_height, heading_gap)
    for (entry, instance), top in zip(placed, tops):
        if service.measure(instance) is not None:
            service.move_top_left(instance, 0.0, top)
        note = texts.get(entry.code)
        if note is not None and service.measure(note) is not None:
            service.move_top_left(note, text_x, top)


def _new_legend(doc, template, config, sheet, report):
    """Copy a legend view without its contents, then name it and set the scale."""
    DB = get_db()
    try:
        new_id = template.Duplicate(DB.ViewDuplicateOption.Duplicate)
    except Exception as ex:
        raise LegendOperationError(
            "Revit could not copy the template legend '{0}'. {1}".format(template.Name, ex)
        )
    view = doc.GetElement(new_id)
    if view is None:
        raise LegendOperationError("Revit duplicated '{0}' but did not return the new legend.".format(template.Name))
    pattern = config["sheet_output_name_pattern"] if sheet is not None else config["output_name_pattern"]
    view.Name = unique_view_name(doc, apply_pattern(pattern, config["name"], sheet))
    try:
        view.Scale = int(config["scale"])
    except Exception as ex:
        report["warnings"].append("The legend scale could not be set to 1:{0}. {1}".format(config["scale"], ex))
    report["notices"].append("New legend '{0}' made from '{1}'.".format(view.Name, template.Name))
    return view


def _scale(view, config):
    try:
        return float(view.Scale) or float(config["scale"])
    except Exception:
        return float(config["scale"])


def _resolve_sheet(doc, payload):
    unique_id = payload.get("sheet_unique_id")
    if not unique_id:
        return None
    return doc.GetElement(unique_id)


def _sheet_label(sheet):
    if sheet is None:
        return None
    number = getattr(sheet, "SheetNumber", "") or ""
    return "{0} - {1}".format(number, sheet.Name) if number else sheet.Name
