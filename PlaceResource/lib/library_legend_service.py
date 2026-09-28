# -*- coding: utf-8 -*-
"""Build legends from the Excel legend library.

Each library row becomes: a graphic (a filled region swatch, or a legend
component for Component rows), a title (the Code, e.g. IWS-105) and a
description. A legend is either the master legend for a category (no sheet)
or a sheet legend (one per category and sheet).

Everything the tool needs is resolved before a transaction starts. The whole
change is one transaction group, so a failure leaves the model unchanged.
Only elements this tool marked are deleted on update; manual notes stay.
"""

from collectors import type_mark
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
from legend_library import (
    GRAPHIC_COMPONENT,
    GRAPHIC_REGION,
    SOURCE_MASTER,
    apply_pattern,
    entries_for_codes,
    layout_rows,
    layout_to_model,
    missing_codes,
    normalize_code,
)
from logging_service import get_logger
from transactions import TransactionContext, TransactionGroupContext
from units import mm_to_internal
from version_adapter import element_id_value, get_db

LOGGER = get_logger("library_legend_service")

LIBRARY_ROLES = ("library_graphic", "library_title", "library_description", "library_heading", "library_seed", "library_row")


def library_hash(category, config, entries):
    """Hash of what a library legend shows, used to skip unchanged legends."""
    records = [{"type_id": index, "display": {"row": entry.as_hash_record()}} for index, entry in enumerate(entries)]
    return content_hash(
        "library:{0}".format(category),
        "1.0",
        records,
        {"layout": config["layout"], "styles": config["styles"], "scale": config["scale"]},
    )


def prepare(doc, config, entries, need_template):
    """Resolve text types, filled region types, component types and the template.

    Returns a dict with "problems" (blocking, listed together) and the resolved objects.
    Nothing in the model changes.
    """
    DB = get_db()
    problems = []
    resolved = {"problems": problems, "text_types": {}, "region_types": {}, "component_types": {}, "template": None}
    styles = config["styles"]
    for key in ("title_text_type", "description_text_type", "heading_text_type"):
        if key == "heading_text_type" and not styles.get("show_heading"):
            continue
        try:
            resolved["text_types"][key] = resolve_text_type(doc, styles[key])
        except LegendOperationError as ex:
            problems.append(str(ex))

    region_names = sorted(set(entry.region_type for entry in entries if entry.graphic == GRAPHIC_REGION))
    if region_names:
        available = {}
        for region_type in DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType):
            try:
                available[region_type.Name] = region_type
            except Exception:
                continue
        missing = [name for name in region_names if name not in available]
        if missing:
            problems.append(
                "Filled Region Type(s) not found in this model: {0}. Create them (Manage > Additional "
                "Settings > Filled Region Types) or fix the names in the Excel library. Available: {1}.".format(
                    ", ".join(missing), ", ".join(sorted(available)[:25]) or "(none)"
                )
            )
        resolved["region_types"] = {name: available[name] for name in region_names if name in available}

    component_entries = [entry for entry in entries if entry.graphic == GRAPHIC_COMPONENT]
    if component_entries:
        category_name = config.get("revit_category")
        if not category_name:
            problems.append(
                "{0} has Component rows ({1}) but no revit_category in library_legends.json. Use Region rows "
                "for this category, or set revit_category.".format(
                    config["name"], ", ".join(entry.code for entry in component_entries)
                )
            )
        else:
            by_mark = _types_by_mark(doc, category_name)
            for entry in component_entries:
                matches = by_mark.get(normalize_code(entry.code)) or []
                if not matches:
                    problems.append(
                        "Component row {0}: no {1} type in this model has Type Mark '{0}'.".format(
                            entry.code, config["name"]
                        )
                    )
                    continue
                resolved["component_types"][entry.code] = matches[0]
                if len(matches) > 1:
                    resolved.setdefault("warnings", []).append(
                        "{0} types have Type Mark '{1}'. '{2}' was used.".format(
                            len(matches), entry.code, _name(matches[0])
                        )
                    )

    if need_template or component_entries:
        try:
            resolved["template"] = find_template_legend(doc, config["template_legend_name"])
        except LegendOperationError as ex:
            problems.append(str(ex))
    return resolved


def build_library_legend(doc, config, entries, sheet=None, legend_view=None):
    """Create or update a library legend. Returns a report dictionary.

    ``sheet`` None builds the master legend for the category.
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
        report["warnings"].append("No library rows were selected, so the legend was not changed.")
        return report
    from_master = entries[0].source == SOURCE_MASTER
    if from_master:
        resolved = _prepare_master(doc, config, entries)
    else:
        resolved = prepare(doc, config, entries, need_template=existing is None)
    report["warnings"].extend(resolved.get("warnings") or [])
    if resolved["problems"]:
        report["errors"].extend(resolved["problems"])
        report["errors"].append("Nothing was changed in the model.")
        return report
    try:
        if from_master:
            view = _run_master(doc, config, entries, sheet, existing, resolved, report)
        else:
            view = _run(doc, config, entries, sheet, existing, resolved, report)
    except LegendToolError as ex:
        report["errors"].append(str(ex))
        report["errors"].append("The change was rolled back. The model was not left partly updated.")
        return report
    except Exception as ex:
        LOGGER.exception("Library legend failed")
        report["errors"].append("Unexpected failure: {0}".format(ex))
        report["errors"].append("The change was rolled back.")
        return report
    report["status"] = "created" if existing is None else "updated"
    report["legend_view_id"] = element_id_value(view.Id)
    report["legend_view_name"] = view.Name
    return report


def update_all_library(doc, library_settings):
    """Rebuild every library legend from its stored codes and the current Excel library."""
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
        codes = payload.get("codes") or []
        library, source_name, problem = _library_for_payload(doc, payload, library_settings)
        if problem:
            summary["skipped"].append({"legend": view.Name, "reason": problem})
            continue
        gone = missing_codes(library, codes)
        if gone:
            summary["warnings"].append("'{0}': code(s) no longer in the {1}: {2}.".format(view.Name, source_name, ", ".join(gone)))
        entries = entries_for_codes(library, codes)
        if payload.get("content_hash") == library_hash(category, config, entries):
            summary["unchanged"].append({"legend": view.Name})
            continue
        report = build_library_legend(doc, config, entries, sheet=sheet, legend_view=view)
        target = summary["failed"] if report["status"] == "failed" else summary["updated"]
        target.append({"legend": view.Name, "status": report["status"], "errors": report["errors"]})
        summary["warnings"].extend(report["warnings"])
    return summary


def audit_library(doc, library_settings):
    """Read-only comparison of library legends with the Excel library and the model."""
    DB = get_db()
    region_names = set()
    for region_type in DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType):
        try:
            region_names.add(region_type.Name)
        except Exception:
            continue
    rows = []
    for view, payload in iter_generated_legends(doc, ROLE_LIBRARY_LEGEND):
        category = payload.get("category")
        config = library_settings["categories"].get(category)
        library, source_name, problem = _library_for_payload(doc, payload, library_settings)
        codes = payload.get("codes") or []
        entries = entries_for_codes(library, codes)
        sheet = _resolve_sheet(doc, payload)
        row = {
            "source": source_name,
            "problem": problem,
            "legend": view.Name,
            "legend_view_id": element_id_value(view.Id),
            "category": category,
            "sheet": _sheet_label(sheet) if sheet is not None else ("Deleted sheet" if payload.get("sheet_unique_id") else "Master"),
            "codes": codes,
            "missing_codes": missing_codes(library, codes),
            "missing_region_types": sorted(set(
                entry.region_type for entry in entries
                if entry.graphic == GRAPHIC_REGION and entry.region_type not in region_names
            )),
            "unlisted_marks": [],
            "outdated": config is not None and payload.get("content_hash") != library_hash(category, config, entries),
            "updated_utc": payload.get("updated_utc"),
        }
        if config is not None and config.get("revit_category") and sheet is not None:
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
            payload["source"] = "excel"
            if write_view_identity(view, payload, doc) == "json_registry":
                report["warnings"].append(
                    "Extensible Storage was unavailable. A local JSON registry was written and does not travel with the model."
                )
        report["warnings"].extend(transaction.warnings)

        with TransactionContext(doc, "Create library legend rows") as transaction:
            created = _create_rows(doc, view, config, entries, resolved, report)
            doc.Regenerate()
        report["warnings"].extend(transaction.warnings)

        with TransactionContext(doc, "Arrange library legend") as transaction:
            _arrange(doc, view, config, created)
            if viewports:
                _restore_viewports(doc, viewports, report)
            doc.Regenerate()
        report["warnings"].extend(transaction.warnings)
    return view


def _library_for_payload(doc, payload, library_settings):
    """Return (entries, source name, problem) for a stored library legend: Excel rows or master legend rows."""
    if payload.get("source") == SOURCE_MASTER:
        master = doc.GetElement(payload.get("master_unique_id") or "")
        if master is None:
            return [], "master legend", "Its master legend was deleted."
        from master_legend_service import read_master
        entries, _notes = read_master(doc, master)
        return entries, "master legend '{0}'".format(master.Name), None
    return library_settings["library"].get(payload.get("category")) or [], "Excel library", None


def _prepare_master(doc, config, entries):
    """Master rows need only the heading text style and the master legend itself."""
    resolved = {"problems": [], "text_types": {}, "master": entries[0].master_view}
    if resolved["master"] is None or not getattr(resolved["master"], "IsValidObject", True):
        resolved["problems"].append("The master legend for {0} is no longer in the model.".format(config["name"]))
    if config["styles"].get("show_heading"):
        try:
            resolved["text_types"]["heading_text_type"] = resolve_text_type(doc, config["styles"]["heading_text_type"])
        except LegendOperationError as ex:
            resolved["problems"].append(str(ex))
    return resolved


def _run_master(doc, config, entries, sheet, existing, resolved, report):
    """Copy the chosen master rows into the legend, stacked top to bottom. The Type Mark is not copied."""
    from legend_service import _capture_viewports, _restore_viewports
    from version_adapter import make_element_id
    from System.Collections.Generic import List
    DB = get_db()
    category = config["name"]
    master = resolved["master"]
    codes = [entry.code for entry in entries]
    viewports = []
    with TransactionGroupContext(doc, "Place Resource: {0} legend".format(category)):
        with TransactionContext(doc, "Prepare legend from master") as transaction:
            if existing is None:
                view = _new_legend(doc, master, config, sheet, report, keep_scale=True)
            else:
                view = existing
                viewports = _capture_viewports(doc, view)
                doomed = [element for element, payload in collect_managed_elements(doc, view)
                          if payload.get("role") in LIBRARY_ROLES]
                if doomed:
                    delete_managed_elements(doc, doomed)
            payload = build_library_view_payload(category, codes, sheet, library_hash(category, config, entries))
            payload["source"] = SOURCE_MASTER
            payload["master_unique_id"] = master.UniqueId
            payload["master_name"] = master.Name
            if write_view_identity(view, payload, doc) == "json_registry":
                report["warnings"].append(
                    "Extensible Storage was unavailable. A local JSON registry was written and does not travel with the model."
                )
        report["warnings"].extend(transaction.warnings)

        with TransactionContext(doc, "Copy rows from master") as transaction:
            service = LegendComponentService(doc, view)
            scale = _scale(view, config)
            cursor = 0.0
            if config["styles"].get("show_heading"):
                heading = service.create_text(
                    DB.XYZ(0, 0, 0), category, resolved["text_types"]["heading_text_type"].Id, 0
                )
                write_element_identity(heading, build_library_element_payload(category, None, "library_heading"))
                doc.Regenerate()
                measured = service.measure(heading)
                if measured is not None:
                    service.move_top_left(heading, 0.0, 0.0)
                    cursor = -(measured["height"] + mm_to_internal(config["layout"]["heading_gap_mm"]) * scale)
            gap = mm_to_internal(config["layout"]["row_gap_mm"]) * scale
            unmarked = 0
            for entry in entries:
                box = entry.box
                ids = List[DB.ElementId]()
                for value in entry.element_ids:
                    ids.Add(make_element_id(value))
                offset = DB.Transform.CreateTranslation(DB.XYZ(0.0 - box["left"], cursor - box["top"], 0))
                try:
                    copied = DB.ElementTransformUtils.CopyElements(master, ids, view, offset, DB.CopyPasteOptions())
                except Exception as ex:
                    raise LegendOperationError(
                        "Revit could not copy row '{0}' from master legend '{1}'. {2}".format(entry.code, master.Name, ex)
                    )
                for copied_id in (list(copied) if copied is not None else []):
                    element = doc.GetElement(copied_id)
                    if element is None:
                        continue
                    try:
                        write_element_identity(element, build_library_element_payload(category, entry.code, "library_row"))
                    except LegendOperationError:
                        unmarked += 1
                cursor -= (box["top"] - box["bottom"]) + gap
            if unmarked:
                report["notices"].append(
                    "{0} copied sub-element(s) could not be marked. They are removed with their parent on update.".format(unmarked)
                )
            if viewports:
                _restore_viewports(doc, viewports, report)
            doc.Regenerate()
        report["warnings"].extend(transaction.warnings)
    report["notices"].append("Rows copied from master legend '{0}'.".format(master.Name))
    return view


def _new_legend(doc, template, config, sheet, report, keep_scale=False):
    """Duplicate a legend without its contents, then name it and (unless keep_scale) set the scale.

    Legends made from a master keep the master's scale so copied text and graphics keep their proportions.
    """
    DB = get_db()
    try:
        new_id = template.Duplicate(DB.ViewDuplicateOption.Duplicate)
    except Exception as ex:
        raise LegendOperationError(
            "Revit could not duplicate template legend '{0}' as an empty legend. {1}".format(template.Name, ex)
        )
    view = doc.GetElement(new_id)
    if view is None:
        raise LegendOperationError("Revit duplicated '{0}' but did not return the new legend.".format(template.Name))
    pattern = config["sheet_output_name_pattern"] if sheet is not None else config["output_name_pattern"]
    view.Name = unique_view_name(doc, apply_pattern(pattern, config["name"], sheet))
    if not keep_scale:
        try:
            view.Scale = int(config["scale"])
        except Exception as ex:
            report["warnings"].append("The legend scale could not be set to 1:{0}. {1}".format(config["scale"], ex))
    report["notices"].append("New legend '{0}' duplicated from '{1}'.".format(view.Name, template.Name))
    return view


def _create_rows(doc, view, config, entries, resolved, report):
    """Create heading, graphics and texts at the origin. Returns what was made, per row."""
    DB = get_db()
    service = LegendComponentService(doc, view)
    styles = config["styles"]
    layout_mm = config["layout"]
    scale = _scale(view, config)
    origin = DB.XYZ(0, 0, 0)
    created = {"heading": None, "rows": [], "scale": scale}
    category = config["name"]

    def _mark(element, code, role):
        write_element_identity(element, build_library_element_payload(category, code, role))

    if styles.get("show_heading"):
        heading = service.create_text(origin, category, resolved["text_types"]["heading_text_type"].Id, 0)
        _mark(heading, None, "library_heading")
        created["heading"] = heading

    seed = None
    if any(entry.graphic == GRAPHIC_COMPONENT for entry in entries):
        seed = _copy_seed(doc, service, resolved["template"])
        _mark(seed, None, "library_seed")

    swatch_width = mm_to_internal(layout_mm["swatch_width_mm"]) * scale
    swatch_height = mm_to_internal(layout_mm["swatch_height_mm"]) * scale
    for index, entry in enumerate(entries):
        if entry.graphic == GRAPHIC_REGION:
            graphic = _create_region(doc, view, resolved["region_types"][entry.region_type].Id, swatch_width, swatch_height)
        else:
            type_element = resolved["component_types"][entry.code]
            service.assert_seed_matches_category(seed, type_element)
            graphic = service.copy_component(seed, index)
            service.assign_type(graphic, type_element)
        _mark(graphic, entry.code, "library_graphic")
        # TextNote width is in paper space (verify in the local Revit SDK help).
        title = service.create_text(
            origin, entry.title, resolved["text_types"]["title_text_type"].Id, mm_to_internal(layout_mm["title_width_mm"])
        )
        _mark(title, entry.code, "library_title")
        description = service.create_text(
            origin, entry.description or "–", resolved["text_types"]["description_text_type"].Id,
            mm_to_internal(layout_mm["description_width_mm"]),
        )
        _mark(description, entry.code, "library_description")
        created["rows"].append({"code": entry.code, "graphic": graphic, "title": title, "description": description})

    if seed is not None:
        delete_managed_elements(doc, [seed])
    return created


def _arrange(doc, view, config, created):
    service = LegendComponentService(doc, view)
    layout_model = layout_to_model(config["layout"], created["scale"], mm_to_internal)
    sizes = []
    for row in created["rows"]:
        sizes.append({key: _size(service, row[key], layout_model) for key in ("graphic", "title", "description")})
    heading_size = _size(service, created["heading"], layout_model) if created["heading"] is not None else None
    positions = layout_rows(sizes, layout_model, heading_size)
    if created["heading"] is not None:
        service.move_top_left(created["heading"], *positions["heading"])
    for row, place in zip(created["rows"], positions["rows"]):
        for key in ("graphic", "title", "description"):
            service.move_top_left(row[key], *place[key])


def _size(service, element, layout_model):
    measured = service.measure(element)
    if measured is None:
        return (layout_model["swatch_width"], layout_model["swatch_height"])
    return (measured["width"], measured["height"])


def _create_region(doc, view, type_id, width, height):
    DB = get_db()
    from System.Collections.Generic import List
    corners = [DB.XYZ(0, 0, 0), DB.XYZ(width, 0, 0), DB.XYZ(width, height, 0), DB.XYZ(0, height, 0)]
    loop = DB.CurveLoop()
    for start, end in zip(corners, corners[1:] + corners[:1]):
        loop.Append(DB.Line.CreateBound(start, end))
    loops = List[DB.CurveLoop]()
    loops.Add(loop)
    try:
        return DB.FilledRegion.Create(doc, type_id, view.Id, loops)
    except Exception as ex:
        raise LegendOperationError("Revit could not create a filled region in legend '{0}'. {1}".format(view.Name, ex))


def _copy_seed(doc, service, template):
    """Copy the template's first legend component into the legend as a temporary seed.

    The seed always comes from the template, never from components already in the
    legend, so a component the user placed by hand is never reused or deleted.
    """
    DB = get_db()
    seeds = LegendComponentService(doc, template).find_components(template)
    if not seeds:
        raise LegendOperationError(
            "Template legend '{0}' has no legend component to copy for Component rows. Place one legend "
            "component of this category in the template.".format(template.Name)
        )
    from System.Collections.Generic import List
    ids = List[DB.ElementId]()
    ids.Add(seeds[0].Id)
    try:
        copied = DB.ElementTransformUtils.CopyElements(
            template, ids, service.legend_view, DB.Transform.Identity, DB.CopyPasteOptions()
        )
    except Exception as ex:
        raise LegendOperationError(
            "Revit could not copy the seed legend component from '{0}'. {1}".format(template.Name, ex)
        )
    copied_ids = list(copied) if copied is not None else []
    seed = doc.GetElement(copied_ids[0]) if copied_ids else None
    if seed is None:
        raise LegendOperationError("Revit did not return the copied seed from '{0}'.".format(template.Name))
    return seed


def _types_by_mark(doc, category_name):
    DB = get_db()
    built_in = getattr(DB.BuiltInCategory, category_name, None)
    if built_in is None:
        raise LegendOperationError("Revit has no built-in category named {0}.".format(category_name))
    result = {}
    for type_element in DB.FilteredElementCollector(doc).OfCategory(built_in).WhereElementIsElementType():
        mark = type_mark(type_element)
        if mark:
            result.setdefault(normalize_code(mark), []).append(type_element)
    return result


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


def _name(element):
    try:
        return element.Name
    except Exception:
        return str(element.Id)
