# -*- coding: utf-8 -*-
"""Build legends from the category's symbol family.

Each chosen family type (one per code, e.g. IWS-105) is placed once in the
legend, stacked top to bottom under an optional heading. The family draws the
graphic and the description, so editing and reloading the family updates every
legend without running the tool again.

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
    write_element_identity,
    write_view_identity,
)
from legend_component_service import LegendComponentService, find_template_legend, resolve_text_type, unique_view_name
from legend_library import apply_pattern, entries_for_codes, missing_codes, normalize_code, stack_rows
from logging_service import get_logger
from symbol_library import family_entries, symbols_by_code
from transactions import TransactionContext, TransactionGroupContext
from units import mm_to_internal
from version_adapter import element_id_value, get_db

LOGGER = get_logger("library_legend_service")

# Roles written by this and earlier versions (Excel and master-legend rows), so updates clear them all.
LIBRARY_ROLES = (
    "library_row", "library_heading",
    "library_graphic", "library_title", "library_description", "library_seed",
)
SOURCE_FAMILY = "family"


def library_hash(category, config, entries):
    """Hash of what a library legend shows, used to skip unchanged legends."""
    records = [{"type_id": index, "display": {"row": entry.as_hash_record()}} for index, entry in enumerate(entries)]
    return content_hash(
        "library:{0}".format(category),
        "2.0",
        records,
        {"family": config["family_name"], "layout": config["layout"], "styles": config["styles"]},
    )


def prepare(doc, config, entries, need_template):
    """Resolve family types, heading text type and template. Nothing in the model changes."""
    problems = []
    resolved = {"problems": problems, "symbols": {}, "heading_type": None, "template": None}
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
    if need_template:
        try:
            resolved["template"] = find_template_legend(doc, config["template_legend_name"])
        except LegendOperationError as ex:
            problems.append(str(ex))
    return resolved


def build_library_legend(doc, config, entries, sheet=None, legend_view=None):
    """Create or update a library legend. Returns a report dictionary.

    ``sheet`` None builds the category legend that is not tied to a sheet.
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
        "warnings": [],
        "errors": [],
        "notices": [],
    }
    if not entries:
        report["status"] = "skipped"
        report["warnings"].append("No rows were ticked, so the legend was not changed.")
        return report
    resolved = prepare(doc, config, entries, need_template=existing is None)
    if resolved["problems"]:
        report["errors"].extend(resolved["problems"])
        report["errors"].append("Nothing was changed in the model.")
        return report
    try:
        view = _run(doc, config, entries, sheet, existing, resolved, report)
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
        if payload.get("source") == SOURCE_FAMILY and payload.get("content_hash") == library_hash(category, config, entries):
            summary["unchanged"].append({"legend": view.Name})
            continue
        report = build_library_legend(doc, config, entries, sheet=sheet, legend_view=view)
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
                or payload.get("content_hash") != library_hash(category, config, entries)
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


def _run(doc, config, entries, sheet, existing, resolved, report):
    from legend_service import _capture_viewports, _restore_viewports
    DB = get_db()
    category = config["name"]
    codes = [entry.code for entry in entries]
    viewports = []
    with TransactionGroupContext(doc, "Place Resource: {0} legend".format(category)):
        with TransactionContext(doc, "Prepare library legend") as transaction:
            if existing is None:
                view = _new_legend(doc, resolved["template"], config, sheet, report)
            else:
                view = existing
                viewports = _capture_viewports(doc, view)
                doomed = [element for element, payload in collect_managed_elements(doc, view)
                          if payload.get("role") in LIBRARY_ROLES]
                if doomed:
                    delete_managed_elements(doc, doomed)
            payload = build_library_view_payload(category, codes, sheet, library_hash(category, config, entries))
            payload["source"] = SOURCE_FAMILY
            payload["family_name"] = config["family_name"]
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
                heading = service.create_text(origin, category, resolved["heading_type"].Id, 0)
                write_element_identity(heading, build_library_element_payload(category, None, "library_heading"))
            for entry in entries:
                symbol = resolved["symbols"][entry.code]
                instance = _place_symbol(doc, view, symbol, origin, entry.code)
                write_element_identity(instance, build_library_element_payload(category, entry.code, "library_row"))
                placed.append((entry.code, instance))
            doc.Regenerate()
        report["warnings"].extend(transaction.warnings)

        with TransactionContext(doc, "Arrange legend symbols") as transaction:
            _arrange(doc, view, config, heading, placed, report)
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


def _arrange(doc, view, config, heading, placed, report):
    service = LegendComponentService(doc, view)
    scale = _scale(view, config)
    row_gap = mm_to_internal(config["layout"]["row_gap_mm"]) * scale
    heading_gap = mm_to_internal(config["layout"]["heading_gap_mm"]) * scale
    heading_height = None
    if heading is not None:
        measured = service.measure(heading)
        heading_height = measured["height"] if measured is not None else 0.0
        if measured is not None:
            service.move_top_left(heading, 0.0, 0.0)
    heights = []
    for code, instance in placed:
        measured = service.measure(instance)
        if measured is None:
            report["warnings"].append("'{0}' shows nothing in the legend. Check the family type.".format(code))
            heights.append(0.0)
        else:
            heights.append(measured["height"])
    tops, _bottom = stack_rows(heights, row_gap, heading_height, heading_gap)
    for (code, instance), top in zip(placed, tops):
        if service.measure(instance) is not None:
            service.move_top_left(instance, 0.0, top)


def _new_legend(doc, template, config, sheet, report):
    """Duplicate the template legend without its contents, then name it and set the scale."""
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
