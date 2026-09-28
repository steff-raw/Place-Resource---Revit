# -*- coding: utf-8 -*-
"""Create and update a legend from the types visible in a source view.

Model elements are never modified. Only the generated legend, its tool-managed
annotation, and its sheet viewport position are written.
"""

from collections import Counter

from collectors import collect_visible_types, source_display_name
from configuration import apply_name_pattern
from errors import LegendOperationError, LegendToolError, UnsupportedRevitOperationError
from identity import (
    TOOL_VERSION,
    build_element_payload,
    build_view_payload,
    collect_managed_elements,
    content_hash,
    delete_managed_elements,
    find_legend,
    read_view_payload,
    try_write_configured_parameter,
    write_element_identity,
    write_view_identity,
)
from layout_engine import compute_layout, estimate_measurements, layout_config_to_internal, used_column_count
from legend_component_service import (
    LegendComponentService,
    duplicate_template,
    find_template_legend,
    find_text_type,
    unique_view_name,
)
from logging_service import get_logger
from transactions import TransactionContext, TransactionGroupContext
from units import mm_to_internal
from version_adapter import describe_version, element_id_value, make_element_id

LOGGER = get_logger("legend_service")


def prepare_plan(doc, source_view, definition, settings):
    """Read the view and describe the legend update without changing the model."""
    collection = collect_visible_types(doc, source_view, definition, settings["aliases"])
    existing = find_legend(doc, source_view, definition["id"])
    existing_ids = []
    existing_name = None
    existing_payload = None
    if existing is not None:
        existing_name = existing.Name
        existing_payload = read_view_payload(existing)
        for _element, payload in collect_managed_elements(doc, existing):
            if payload.get("role") == "component" and payload.get("type_id") is not None:
                existing_ids.append(int(payload["type_id"]))
    desired_ids = [record.type_id for record in collection.types]
    to_add = [record for record in collection.types if record.type_id not in set(existing_ids)]
    to_remove = sorted(set(existing_ids) - set(desired_ids))
    to_keep = [record for record in collection.types if record.type_id in set(existing_ids)]
    layout_internal = layout_config_to_internal(definition["layout"])
    estimated_entries = estimate_measurements(
        [{"key": str(record.type_id)} for record in collection.types],
        definition["labels"],
        layout_internal,
    )
    estimate = compute_layout(
        estimated_entries,
        definition["labels"],
        layout_internal,
        show_headers=bool(definition["styles"].get("show_headers")),
    )
    blocking = _blocking_errors(collection, definition)
    return {
        "collection": collection,
        "existing": existing,
        "existing_name": existing_name,
        "existing_payload": existing_payload,
        "existing_type_ids": existing_ids,
        "to_add": to_add,
        "to_remove": to_remove,
        "to_keep": to_keep,
        "estimate": estimate,
        "blocking_errors": blocking,
        "mode": "create" if existing is None else "update",
    }


def create_or_update(doc, source_view, definition, settings, options):
    """Create or update the generated legend. Rolls back the whole change on failure."""
    options = options or {}
    plan = prepare_plan(doc, source_view, definition, settings)
    report = _empty_report(source_view, definition, plan)
    if plan["blocking_errors"]:
        report["status"] = "failed"
        report["errors"].extend(plan["blocking_errors"])
        return report
    if plan["existing"] is None and not plan["collection"].types and not definition["update"].get("create_when_empty"):
        report["status"] = "skipped"
        report["warnings"].append(
            "No visible types were found, so a legend was not created. "
            "Set update.create_when_empty to true if an empty legend is required."
        )
        return report

    proposed_hash = content_hash(
        definition["id"],
        settings["data"]["schema_version"],
        [record.as_hash_record() for record in plan["collection"].types],
        definition["layout"],
    )
    if (
        options.get("skip_if_unchanged")
        and plan["existing_payload"]
        and plan["existing_payload"].get("content_hash") == proposed_hash
    ):
        report["status"] = "unchanged"
        report["legend_view_id"] = element_id_value(plan["existing"].Id)
        report["legend_view_name"] = plan["existing_name"]
        report["notices"].append("The stored content hash matches the view, so this legend was left unchanged.")
        return report

    allow_delete = bool(options.get("allow_delete")) and bool(definition["update"].get("remove_unused_entries"))
    if plan["to_remove"] and not allow_delete:
        report["warnings"].append(
            "{0} type(s) are no longer visible and were kept because removal is turned off "
            "or was declined.".format(len(plan["to_remove"]))
        )

    try:
        body_type = find_text_type(doc, definition["styles"]["text_note_type"])
        header_type = find_text_type(doc, definition["styles"]["header_text_note_type"])
    except LegendOperationError as ex:
        report["status"] = "failed"
        report["errors"].append(str(ex))
        return report

    template = None
    if plan["existing"] is None or definition["update"].get("full_rebuild"):
        try:
            template = find_template_legend(doc, definition["template_legend_name"])
        except LegendOperationError as ex:
            if plan["existing"] is None:
                report["status"] = "failed"
                report["errors"].append(str(ex))
                return report
            report["warnings"].append(str(ex))

    try:
        _run_changes(
            doc, source_view, definition, settings, plan, report, proposed_hash,
            body_type, header_type, template, allow_delete,
        )
    except (LegendOperationError, UnsupportedRevitOperationError, LegendToolError) as ex:
        report["status"] = "failed"
        report["errors"].append(str(ex))
        report["errors"].append("The legend change was rolled back. The model was not left partially updated.")
        return report
    except Exception as ex:
        LOGGER.exception("Legend update failed")
        report["status"] = "failed"
        report["errors"].append("Unexpected failure: {0}".format(ex))
        report["errors"].append("The legend change was rolled back.")
        return report
    return report


def update_all(doc, settings, options):
    """Update every managed legend whose source view still exists."""
    from identity import iter_generated_legends
    from version_adapter import get_db, make_element_id
    DB = get_db()
    summary = {
        "status": "updated",
        "updated": [],
        "unchanged": [],
        "skipped": [],
        "failed": [],
        "warnings": [],
        "errors": [],
        "version": TOOL_VERSION,
        "host": describe_version(),
    }
    definitions = {item["id"]: item for item in settings["data"]["legend_definitions"]}
    for legend_view, payload in list(iter_generated_legends(doc)):
        definition = definitions.get(payload.get("legend_definition_id"))
        legend_name = legend_view.Name
        if definition is None:
            summary["failed"].append({
                "legend": legend_name,
                "error": "Legend definition '{0}' is no longer in the settings file.".format(
                    payload.get("legend_definition_id")
                ),
            })
            continue
        source = doc.GetElement(payload.get("source_view_unique_id"))
        if source is None and payload.get("source_view_id") is not None:
            source = doc.GetElement(make_element_id(payload.get("source_view_id")))
        if source is None or not isinstance(source, DB.View):
            summary["skipped"].append({
                "legend": legend_name,
                "reason": "Source view {0} was deleted or is not a view.".format(payload.get("source_view_id")),
            })
            summary["warnings"].append(
                "Skipped '{0}' because its source view no longer exists.".format(legend_name)
            )
            continue
        report = create_or_update(doc, source, definition, settings, options)
        entry = {
            "legend": report.get("legend_view_name") or legend_name,
            "source": report.get("source_view_name"),
            "status": report.get("status"),
            "added": report.get("added"),
            "removed": report.get("removed"),
            "warnings": report.get("warnings"),
            "errors": report.get("errors"),
        }
        if report["status"] == "failed":
            summary["failed"].append(entry)
            summary["errors"].extend(report["errors"])
        elif report["status"] == "unchanged":
            summary["unchanged"].append(entry)
        elif report["status"] == "skipped":
            summary["skipped"].append(entry)
        else:
            summary["updated"].append(entry)
        summary["warnings"].extend(report.get("warnings") or [])
    if summary["failed"]:
        summary["status"] = "completed_with_failures"
    return summary


def _run_changes(doc, source_view, definition, settings, plan, report, proposed_hash,
                 body_type, header_type, template, allow_delete):
    created_new = plan["existing"] is None
    with TransactionGroupContext(doc, "Place Resource: View Legend"):
        legend_view = plan["existing"]
        viewports = []
        with TransactionContext(doc, "Prepare legend view") as transaction:
            if legend_view is None:
                legend_view, duplicate_mode = duplicate_template(doc, template)
                report["notices"].append("Template legend duplicated with {0}.".format(duplicate_mode))
                _rename_legend(doc, legend_view, source_view, definition, True)
                service = LegendComponentService(doc, legend_view)
                report["warnings"].extend(service.apply_view_settings_on_create(definition["representation"]))
            else:
                legend_view = plan["existing"]
                if definition["update"].get("sync_legend_name"):
                    _rename_legend(doc, legend_view, source_view, definition, False)
                if definition["update"].get("reset_representation"):
                    report["warnings"].extend(
                        LegendComponentService(doc, legend_view).apply_view_settings_on_create(
                            definition["representation"]
                        )
                    )
                if definition["update"].get("preserve_viewport_position", True):
                    viewports = _capture_viewports(doc, legend_view)
            payload = build_view_payload(
                source_view, definition, settings["data"]["schema_version"], proposed_hash
            )
            storage = write_view_identity(legend_view, payload, doc)
            if storage == "json_registry":
                report["warnings"].append(
                    "Extensible Storage was unavailable. A local JSON registry was written and does not "
                    "travel with the model. Move the model only after storage succeeds."
                )
            parameter_notice = try_write_configured_parameter(
                legend_view,
                definition.get("output_identity_parameter"),
                element_id_value(source_view.Id),
                definition["id"],
            )
            if parameter_notice:
                report["notices"].append(parameter_notice)
            report["warnings"].extend(transaction.warnings)

        with TransactionContext(doc, "Update legend entries") as transaction:
            _populate(
                doc, legend_view, source_view, definition, plan, report,
                body_type, header_type, template, allow_delete,
            )
            doc.Regenerate()
            report["warnings"].extend(transaction.warnings)

        with TransactionContext(doc, "Align legend entries") as transaction:
            _align(doc, legend_view, source_view, definition, plan, report, viewports, proposed_hash, settings)
            doc.Regenerate()
            _record_measured_overlaps(doc, legend_view, report)
            report["warnings"].extend(transaction.warnings)

    report["status"] = "created" if created_new else "updated"
    report["legend_view_id"] = element_id_value(legend_view.Id)
    report["legend_view_name"] = legend_view.Name


def _populate(doc, legend_view, source_view, definition, plan, report,
              body_type, header_type, template, allow_delete):
    if template is not None and element_id_value(legend_view.Id) == element_id_value(template.Id):
        raise LegendOperationError("Refusing to modify the template legend '{0}'.".format(template.Name))
    service = LegendComponentService(doc, legend_view)
    full_rebuild = bool(definition["update"].get("full_rebuild"))
    managed = collect_managed_elements(doc, legend_view)
    if full_rebuild and managed:
        delete_managed_elements(doc, [element for element, _payload in managed])
        managed = []
        report["notices"].append("Full rebuild removed previous tool-managed entries before recreating them.")

    components = [(element, payload) for element, payload in managed if payload.get("role") == "component"]
    by_type = {}
    for element, payload in components:
        by_type.setdefault(int(payload.get("type_id")), []).append(element)

    source, source_notice = _copy_source(doc, service, components, template)
    if source_notice:
        report["notices"].append(source_notice)
    if plan["collection"].types and source is None:
        raise LegendOperationError(
            "No seed legend component was found in '{0}' or in template '{1}'. "
            "Place one legend component in the template legend and run the command again.".format(
                legend_view.Name, definition["template_legend_name"]
            )
        )

    representation_notes = []
    fresh_legend = not components
    for index, record in enumerate(plan["collection"].types):
        type_element = doc.GetElement(make_element_id(record.type_id))
        if type_element is None:
            raise LegendOperationError(
                "Type id {0} is no longer in the model, so its legend component could not be created.".format(
                    record.type_id
                )
            )
        existing = by_type.get(record.type_id) or []
        if existing:
            component = existing[0]
            service.assign_type(component, type_element)
            if len(existing) > 1 and allow_delete:
                delete_managed_elements(doc, existing[1:])
                report["removed"].append("{0} duplicate".format(record.type_name))
            elif len(existing) > 1:
                report["warnings"].append(
                    "Type '{0}' has {1} managed legend components. Extra copies were kept because "
                    "removal was declined.".format(_type_label(record), len(existing))
                )
        else:
            if fresh_legend and index == 0:
                service.assert_seed_matches_category(source, type_element)
                component = source
                service.assign_type(component, type_element)
                fresh_legend = False
            else:
                service.assert_seed_matches_category(source, type_element)
                component = service.copy_component(source, index)
                service.assign_type(component, type_element)
            _mark(component, definition, source_view, record.type_id, "component")
            report["added"].append(_type_label(record))
        notes = service.apply_representation(component, definition["representation"])
        if index == 0:
            representation_notes = notes
        by_type[record.type_id] = [component]
    report["warnings"].extend(representation_notes)

    if allow_delete:
        for type_id in plan["to_remove"]:
            doomed = [element for element, payload in managed if int(payload.get("type_id") or -1) == int(type_id)]
            if doomed:
                delete_managed_elements(doc, doomed)
                report["removed"].append(str(type_id))

    if fresh_legend and source is not None and not plan["collection"].types and plan["existing"] is None:
        # The seed came with the template duplicate made in this run, so it is ours to remove.
        _mark(source, definition, source_view, None, "component")
        delete_managed_elements(doc, [source])
        report["notices"].append("The duplicated seed component was removed because the view has no visible types.")

    _sync_labels(
        doc, service, legend_view, source_view, definition, plan, report,
        body_type, header_type, by_type,
    )
    _sync_chrome(doc, legend_view)


def _sync_labels(doc, service, legend_view, source_view, definition, plan, report,
                 body_type, header_type, components_by_type):
    from version_adapter import get_db
    DB = get_db()
    managed = collect_managed_elements(doc, legend_view)
    labels = {(int(payload.get("type_id")), payload.get("label_parameter")): element
              for element, payload in managed if payload.get("role") == "type_label"}
    blank = definition.get("type_rules", {}).get("blank_label", "–")
    origin = DB.XYZ(0, 0, 0)
    for record in plan["collection"].types:
        if record.type_id not in components_by_type:
            continue
        for label in definition["labels"]:
            text = record.display.get(label["parameter"]) or blank
            key = (record.type_id, label["parameter"])
            existing = labels.get(key)
            if existing is not None:
                if service.set_text(existing, text):
                    report["updated"].append("{0} / {1}".format(_type_label(record), label["heading"]))
            else:
                note = service.create_text(
                    origin,
                    text,
                    body_type.Id,
                    mm_to_internal(label["width_mm"]),
                )
                _mark(
                    note, definition, source_view, record.type_id, "type_label",
                    label_parameter=label["parameter"],
                )
    if definition["styles"].get("show_headers"):
        column_count = used_column_count(
            len(plan["collection"].types),
            definition["layout"]["columns"],
            definition["layout"]["direction"],
        )
        existing_headings = {
            (payload.get("label_parameter"), int(payload.get("column_index") or 0)): element
            for element, payload in managed if payload.get("role") == "heading"
        }
        needed = set()
        for column in range(column_count):
            for label in definition["labels"]:
                needed.add((label["parameter"], column))
                note = existing_headings.get((label["parameter"], column))
                if note is None:
                    note = service.create_text(
                        origin,
                        label["heading"],
                        header_type.Id,
                        mm_to_internal(label["width_mm"]),
                    )
                    _mark(
                        note, definition, source_view, None, "heading",
                        label_parameter=label["parameter"], column_index=column,
                    )
                else:
                    service.set_text(note, label["heading"])
        stale = [element for key, element in existing_headings.items() if key not in needed]
        if stale:
            delete_managed_elements(doc, stale)
    else:
        stale = [element for element, payload in managed if payload.get("role") == "heading"]
        if stale:
            delete_managed_elements(doc, stale)


def _sync_chrome(doc, legend_view):
    """Remove managed borders and layer graphics.

    The align pass rebuilds the ones the settings ask for, so they are removed on
    every run. Declining entry removal does not apply here: these are generated
    graphics, not legend entries, and keeping them would stack a copy per update.
    """
    managed = collect_managed_elements(doc, legend_view)
    roles = {"border", "layer_reference", "layer_dimension", "layer_line"}
    doomed = [element for element, payload in managed if payload.get("role") in roles]
    if doomed:
        delete_managed_elements(doc, doomed)


def _align(doc, legend_view, source_view, definition, plan, report, viewports, proposed_hash, settings):
    service = LegendComponentService(doc, legend_view)
    doc.Regenerate()
    managed = collect_managed_elements(doc, legend_view)
    components = {}
    label_elements = {}
    headings = {}
    for element, payload in managed:
        role = payload.get("role")
        if role == "component" and payload.get("type_id") is not None:
            components[int(payload["type_id"])] = element
        elif role == "type_label":
            label_elements[(int(payload.get("type_id")), payload.get("label_parameter"))] = element
        elif role == "heading":
            headings[(payload.get("label_parameter"), int(payload.get("column_index") or 0))] = element

    layout_internal = layout_config_to_internal(definition["layout"])
    entries = []
    for record in plan["collection"].types:
        component = components.get(record.type_id)
        if component is None:
            continue
        measured = service.measure(component)
        if measured is None:
            report["warnings"].append(
                "Legend component for '{0}' has no bounding box. The configured graphic size was used.".format(
                    _type_label(record)
                )
            )
            measured = {
                "width": layout_internal["graphic_width_internal"],
                "height": layout_internal["row_height_internal"],
            }
        label_sizes = []
        for label in definition["labels"]:
            note = label_elements.get((record.type_id, label["parameter"]))
            note_box = service.measure(note) if note is not None else None
            if note_box is None:
                note_box = {
                    "width": mm_to_internal(label["width_mm"]),
                    "height": layout_internal["row_height_internal"],
                }
            label_sizes.append({
                "parameter": label["parameter"],
                "width": note_box["width"],
                "height": note_box["height"],
            })
        entries.append({
            "key": str(record.type_id),
            "component": measured,
            "labels": label_sizes,
        })

    header_height = layout_internal["row_height_internal"]
    if headings:
        heights = []
        for element in headings.values():
            box = service.measure(element)
            if box is not None:
                heights.append(box["height"])
        if heights:
            header_height = max(heights)
    layout = compute_layout(
        entries,
        definition["labels"],
        layout_internal,
        header_height=header_height,
        show_headers=bool(definition["styles"].get("show_headers")),
    )
    report["warnings"].extend(layout["warnings"])
    report["realigned"] = 0
    for record in plan["collection"].types:
        key = str(record.type_id)
        component = components.get(record.type_id)
        position = layout["positions"].get("component:{0}".format(key))
        if component is not None and position is not None:
            service.move_top_left(component, position[0], position[1])
            report["realigned"] += 1
        for label in definition["labels"]:
            note = label_elements.get((record.type_id, label["parameter"]))
            label_position = layout["positions"].get("label:{0}:{1}".format(key, label["parameter"]))
            if note is not None and label_position is not None:
                service.move_top_left(note, label_position[0], label_position[1])
    for (parameter, column), element in headings.items():
        position = layout["positions"].get("heading:{0}:{1}".format(parameter, column))
        if position is not None:
            service.move_top_left(element, position[0], position[1])

    doc.Regenerate()
    if definition["styles"].get("show_border"):
        def _mark_border(element, role):
            _mark(element, definition, source_view, None, role)
        service.create_border(
            layout["block"],
            definition["styles"]["line_style"],
            layout_internal["label_gap_internal"],
            _mark_border,
        )
    if definition["representation"].get("layer_reference_planes"):
        _add_layer_graphics(doc, service, components, plan, definition, source_view, report)

    if viewports and definition["update"].get("preserve_viewport_position", True):
        _restore_viewports(doc, viewports, report)

    payload = build_view_payload(
        source_view, definition, settings["data"]["schema_version"], proposed_hash
    )
    write_view_identity(legend_view, payload, doc)


def _add_layer_graphics(doc, service, components, plan, definition, source_view, report):
    from version_adapter import get_db
    DB = get_db()
    for record in plan["collection"].types:
        component = components.get(record.type_id)
        type_element = doc.GetElement(make_element_id(record.type_id))
        if component is None or type_element is None:
            continue
        sub = DB.SubTransaction(doc)
        sub.Start()
        try:
            def _mark_layer(element, role, type_id=record.type_id):
                _mark(element, definition, source_view, type_id, role)
            _created, warnings = service.try_layer_references(component, type_element, _mark_layer)
            report["warnings"].extend(warnings)
            sub.Commit()
        except Exception as ex:
            sub.RollBack()
            report["warnings"].append(
                "Layer reference planes for '{0}' were rolled back. {1}".format(_type_label(record), ex)
            )
            if definition["representation"].get("fallback_detail_lines"):
                fallback = DB.SubTransaction(doc)
                fallback.Start()
                try:
                    def _mark_line(element, role, type_id=record.type_id):
                        _mark(element, definition, source_view, type_id, role)
                    _created, warnings = service.create_detail_layer_lines(
                        component, type_element, definition["styles"]["line_style"], _mark_line
                    )
                    report["warnings"].extend(warnings)
                    fallback.Commit()
                except Exception as line_error:
                    fallback.RollBack()
                    report["warnings"].append(
                        "Detail-line fallback for '{0}' failed and was rolled back. {1}".format(
                            _type_label(record), line_error
                        )
                    )


def _copy_source(doc, service, managed_components, template):
    if managed_components:
        return managed_components[0][0], None
    local = service.find_components()
    if local:
        if len(local) > 1:
            return local[0], (
                "The legend contains {0} legend components. The first one was used as the seed. "
                "Keep a single seed in the template so extra components are not copied into new legends.".format(
                    len(local)
                )
            )
        return local[0], None
    if template is None:
        return None, None
    from version_adapter import get_db
    DB = get_db()
    template_service = LegendComponentService(doc, template)
    seeds = template_service.find_components(template)
    if not seeds:
        return None, "Template legend '{0}' has no legend component.".format(template.Name)
    try:
        from System.Collections.Generic import List
        ids = List[DB.ElementId]()
        ids.Add(seeds[0].Id)
        copied = DB.ElementTransformUtils.CopyElements(
            template,
            ids,
            service.legend_view,
            DB.Transform.Identity,
            DB.CopyPasteOptions(),
        )
    except Exception as ex:
        raise UnsupportedRevitOperationError(
            "Revit could not copy the seed legend component from '{0}' into the generated legend. {1}".format(
                template.Name, ex
            )
        )
    if not copied:
        return None, None
    element = doc.GetElement(list(copied)[0])
    notice = None
    if len(seeds) > 1:
        notice = "Template '{0}' has more than one legend component. Only the first was copied.".format(template.Name)
    return element, notice


def _mark(element, definition, source_view, type_id, role, label_parameter=None, column_index=0):
    payload = build_element_payload(
        definition["id"],
        element_id_value(source_view.Id),
        type_id,
        role,
        label_parameter=label_parameter,
        column_index=column_index,
    )
    write_element_identity(element, payload)


def _rename_legend(doc, legend_view, source_view, definition, always):
    if not always and not definition["update"].get("sync_legend_name"):
        return
    name = apply_name_pattern(definition["output_name_pattern"], {
        "source_view_name": source_display_name(source_view),
        "definition_id": definition["id"],
        "view_type": source_view.ViewType.ToString(),
    })
    if legend_view.Name == name:
        return
    legend_view.Name = unique_view_name(doc, name)


def _capture_viewports(doc, legend_view):
    from version_adapter import get_db
    DB = get_db()
    target = element_id_value(legend_view.Id)
    captured = []
    for viewport in DB.FilteredElementCollector(doc).OfClass(DB.Viewport):
        try:
            if element_id_value(viewport.ViewId) != target:
                continue
            captured.append((viewport.Id, viewport.GetBoxCenter()))
        except Exception:
            continue
    return captured


def _restore_viewports(doc, captured, report):
    restored = 0
    for viewport_id, center in captured:
        viewport = doc.GetElement(viewport_id)
        if viewport is None:
            continue
        try:
            viewport.SetBoxCenter(center)
            restored += 1
        except Exception as ex:
            report["warnings"].append("A legend viewport position could not be restored. {0}".format(ex))
    if restored:
        report["notices"].append("Preserved the sheet position of {0} legend viewport(s).".format(restored))


def _record_measured_overlaps(doc, legend_view, report):
    service = LegendComponentService(doc, legend_view)
    boxes = []
    for element, payload in collect_managed_elements(doc, legend_view):
        if payload.get("role") not in ("component", "type_label", "heading"):
            continue
        measured = service.measure(element)
        if measured is None:
            continue
        boxes.append({
            "id": "{0}:{1}".format(payload.get("role"), payload.get("type_id")),
            "left": measured["min_x"],
            "right": measured["max_x"],
            "top": measured["max_y"],
            "bottom": measured["min_y"],
        })
    from layout_engine import find_overlaps
    overlaps = find_overlaps(boxes, mm_to_internal(0.5))
    for first_id, second_id in overlaps:
        report["warnings"].append(
            "After alignment, '{0}' still overlaps '{1}'.".format(first_id, second_id)
        )


def _blocking_errors(collection, definition):
    if definition.get("type_rules", {}).get("unmapped_parameter") != "error":
        return []
    errors = []
    for record in collection.types:
        for item in record.resolution:
            warning = item.get("warning") or ""
            if "not mapped" in warning and "error" in warning:
                errors.append(warning)
    return errors


def _empty_report(source_view, definition, plan):
    collection = plan["collection"]
    counts = Counter(item.get("reason") for item in collection.excluded)
    return {
        "status": "preview",
        "source_view_id": element_id_value(source_view.Id),
        "source_view_name": source_display_name(source_view),
        "source_view_type": collection.view_info.get("view_type"),
        "legend_view_id": element_id_value(plan["existing"].Id) if plan["existing"] is not None else None,
        "legend_view_name": plan["existing_name"],
        "definition_id": definition["id"],
        "definition_name": definition["display_name"],
        "mode": plan["mode"],
        "instance_count": collection.instance_count,
        "unique_type_count": collection.unique_type_count,
        "added": [],
        "updated": [],
        "removed": [],
        "realigned": 0,
        "warnings": list(collection.warnings),
        "errors": list(collection.errors),
        "notices": list(collection.notices),
        "types": [_record_summary(record) for record in collection.types],
        "excluded_counts": dict(counts),
        "planned_add": [_type_label(record) for record in plan["to_add"]],
        "planned_remove": [str(type_id) for type_id in plan["to_remove"]],
        "estimate": plan["estimate"]["block"],
        "version": TOOL_VERSION,
        "host": describe_version(),
    }


def _record_summary(record):
    return {
        "type_id": record.type_id,
        "family_name": record.family_name,
        "type_name": record.type_name,
        "type_mark": record.display.get("Type Mark"),
        "display": dict(record.display),
        "instance_count": len(record.instance_ids),
        "layers": record.layers,
        "is_linked": record.is_linked,
        "warnings": list(record.warnings),
    }


def _type_label(record):
    mark = record.display.get("Type Mark")
    if mark and mark != "–":
        return "{0} {1}".format(mark, record.type_name or record.type_id)
    return record.type_name or str(record.type_id)
