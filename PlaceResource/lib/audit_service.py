# -*- coding: utf-8 -*-
"""Read-only audit of tool-managed legends. This module does not start a transaction."""

from collections import Counter

from collectors import collect_visible_types
from identity import collect_managed_elements, iter_generated_legends, read_element_payload
from layout_engine import find_overlaps
from placement_service import sheets_containing_view, sheet_label
from units import mm_to_internal
from version_adapter import element_id_value, make_element_id


def audit_legends(doc, settings):
    """Compare every managed legend with the types visible in its source view."""
    definitions = {item["id"]: item for item in settings["data"]["legend_definitions"]}
    rows = []
    warnings = []
    for legend_view, payload in iter_generated_legends(doc):
        rows.append(_audit_one(doc, settings, legend_view, payload, definitions))
    if not rows:
        warnings.append("No tool-managed legends were found in this model.")
    return {"rows": rows, "warnings": warnings}


def _audit_one(doc, settings, legend_view, payload, definitions):
    definition_id = payload.get("legend_definition_id")
    definition = definitions.get(definition_id)
    source = _source_view(doc, payload)
    sheets = sheets_containing_view(doc, legend_view)
    managed = collect_managed_elements(doc, legend_view)
    components = [(element, item) for element, item in managed if item.get("role") == "component"]
    represented = []
    for element, item in components:
        represented.append(int(item.get("type_id")))
    duplicate_ids = [type_id for type_id, count in Counter(represented).items() if count > 1]
    row = {
        "legend_view_id": element_id_value(legend_view.Id),
        "legend_view_name": legend_view.Name,
        "definition_id": definition_id,
        "definition_name": definition["display_name"] if definition else None,
        "source_view_id": payload.get("source_view_id"),
        "source_view_name": source.Name if source is not None else None,
        "source_missing": source is None,
        "sheets": [sheet_label(sheet) for sheet in sheets],
        "sheet_ids": [element_id_value(sheet.Id) for sheet in sheets],
        "updated_utc": payload.get("updated_utc"),
        "tool_version": payload.get("tool_version"),
        "content_hash": payload.get("content_hash"),
        "represented_type_ids": represented,
        "visible_type_ids": [],
        "missing_type_ids": [],
        "obsolete_type_ids": [],
        "duplicate_type_ids": duplicate_ids,
        "missing_parameters": [],
        "overlaps": [],
        "warnings": [],
    }
    if definition is None:
        row["warnings"].append(
            "Definition '{0}' is not in the current settings file.".format(definition_id)
        )
        return row
    if source is None:
        row["warnings"].append("The source view was deleted or cannot be resolved.")
        return row
    try:
        collection = collect_visible_types(doc, source, definition, settings["aliases"])
    except Exception as ex:
        row["warnings"].append("Visible types could not be collected. {0}".format(ex))
        return row
    visible = [record.type_id for record in collection.types]
    row["visible_type_ids"] = visible
    row["visible_types"] = [
        {"type_id": record.type_id, "name": record.type_name, "mark": record.display.get("Type Mark")}
        for record in collection.types
    ]
    visible_set = set(visible)
    represented_set = set(represented)
    row["missing_type_ids"] = sorted(visible_set - represented_set)
    row["obsolete_type_ids"] = sorted(represented_set - visible_set)
    for record in collection.types:
        for item in record.resolution:
            if item.get("warning"):
                row["missing_parameters"].append("{0}: {1}".format(record.type_name, item["warning"]))
    row["warnings"].extend(collection.warnings)
    row["overlaps"] = _overlap_pairs(legend_view, managed)
    for element, item in components:
        if not _component_type_matches(element, item.get("type_id")):
            row["warnings"].append(
                "Managed component {0} does not report the stored type id {1}.".format(
                    element_id_value(element.Id), item.get("type_id")
                )
            )
    return row


def _source_view(doc, payload):
    from version_adapter import get_db
    DB = get_db()
    source = doc.GetElement(payload.get("source_view_unique_id"))
    if source is None and payload.get("source_view_id") is not None:
        source = doc.GetElement(make_element_id(payload.get("source_view_id")))
    if source is None or not isinstance(source, DB.View):
        return None
    return source


def _component_type_matches(element, type_id):
    if type_id is None:
        return False
    try:
        from legend_component_service import LegendComponentService
        from version_adapter import element_id_value as value_of
        owner = element.Document
        view = owner.GetElement(element.OwnerViewId)
        service = LegendComponentService(owner, view)
        current = service.component_type_id(element)
        if current is None:
            return False
        return value_of(current) == int(type_id)
    except Exception:
        return False


def _overlap_pairs(legend_view, managed):
    from legend_component_service import LegendComponentService
    service = LegendComponentService(legend_view.Document, legend_view)
    boxes = []
    for element, payload in managed:
        if payload.get("role") not in ("component", "type_label", "heading"):
            continue
        # Confirm the element is still managed before measuring it.
        if read_element_payload(element) is None:
            continue
        measured = service.measure(element)
        if measured is None:
            continue
        boxes.append({
            "id": "{0}:{1}:{2}".format(payload.get("role"), payload.get("type_id"), payload.get("label_parameter")),
            "left": measured["min_x"],
            "right": measured["max_x"],
            "top": measured["max_y"],
            "bottom": measured["min_y"],
        })
    return find_overlaps(boxes, mm_to_internal(0.5))
