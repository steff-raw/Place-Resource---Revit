# -*- coding: utf-8 -*-
"""Persistent identity for generated legends and the elements they own.

Extensible Storage is the primary store because it travels with the model.
A DataStorage registry is kept as an index. If storage cannot be written, a
local JSON file is used and the report says that it does not travel with the model.

Do not change the schema GUIDs. Existing projects would lose their identity.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

from configuration import extension_root
from errors import LegendOperationError

TOOL_VERSION = "1.0.0"
TOOL_ID = "view_legend_creator"
VENDOR_ID = "PRSC"
VIEW_SCHEMA_GUID = "8f4e2c1a-6b3d-4e7f-9a21-5c8d0e4b7f63"
ELEMENT_SCHEMA_GUID = "3c9a7e52-1d4b-4f86-b0c5-7e2a9d6f4b18"
REGISTRY_SCHEMA_GUID = "d1b6e4a8-0c53-4a9e-8f27-6b5c3d2e1a90"
VIEW_SCHEMA_NAME = "PRLegendView"
ELEMENT_SCHEMA_NAME = "PRLegendElement"
REGISTRY_SCHEMA_NAME = "PRLegendRegistry"


def utc_now():
    """Return a UTC timestamp string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def content_hash(definition_id, schema_version, records, layout):
    """Hash the generated content so unchanged legends can be skipped."""
    normalized = [
        {
            "type_id": record.get("type_id"),
            "display": record.get("display") or {},
        }
        for record in records
    ]
    normalized.sort(key=lambda item: (item.get("type_id") is None, item.get("type_id")))
    payload = {
        "definition_id": definition_id,
        "schema_version": schema_version,
        "layout": layout,
        "records": normalized,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def document_key(doc):
    """Return a stable key for the local JSON fallback registry."""
    path = ""
    title = ""
    try:
        path = doc.PathName or ""
    except Exception:
        path = ""
    try:
        title = doc.Title or ""
    except Exception:
        title = ""
    raw = path or title or "unsaved"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_view_payload(source_view, definition, schema_version, content_hash_value, storage="extensible_storage"):
    """Return the identity stored on a generated legend view."""
    from version_adapter import element_id_value
    return {
        "tool": TOOL_ID,
        "role": "generated_legend",
        "managed": True,
        "source_view_id": element_id_value(source_view.Id),
        "source_view_unique_id": source_view.UniqueId,
        "legend_definition_id": definition["id"],
        "updated_utc": utc_now(),
        "tool_version": TOOL_VERSION,
        "content_hash": content_hash_value,
        "config_schema_version": schema_version,
        "storage": storage,
    }


def build_element_payload(definition_id, source_view_id, type_id, role, label_parameter=None, column_index=0):
    """Return the identity stored on one generated element."""
    return {
        "tool": TOOL_ID,
        "managed": True,
        "role": role,
        "legend_definition_id": definition_id,
        "source_view_id": int(source_view_id),
        "type_id": None if type_id is None else int(type_id),
        "label_parameter": label_parameter,
        "column_index": int(column_index or 0),
        "tool_version": TOOL_VERSION,
    }


def write_view_identity(legend_view, payload, doc):
    """Store legend identity. Returns the storage method that succeeded."""
    try:
        _write_entity(legend_view, VIEW_SCHEMA_GUID, VIEW_SCHEMA_NAME, "Generated legend identity.", payload)
    except Exception as storage_error:
        try:
            _write_json_registry(doc, legend_view, payload)
        except Exception as json_error:
            raise LegendOperationError(
                "The legend identity could not be stored. Extensible Storage failed ({0}). "
                "The local JSON fallback also failed ({1}).".format(storage_error, json_error)
            )
        payload["storage"] = "json_registry"
        return "json_registry"
    try:
        _update_registry(doc, payload, legend_view)
    except Exception:
        # The view entity is the source of truth. A registry index failure is not fatal.
        pass
    return "extensible_storage"


def write_element_identity(element, payload):
    """Mark one generated element. Raises if the element cannot be marked."""
    try:
        _write_entity(element, ELEMENT_SCHEMA_GUID, ELEMENT_SCHEMA_NAME, "Generated legend element.", payload)
    except Exception as ex:
        raise LegendOperationError(
            "Could not mark a generated element as tool-managed, so it was not left in the legend. {0}".format(ex)
        )


def read_view_payload(view):
    """Return the legend identity on a view, or None."""
    payload = _read_entity(view, VIEW_SCHEMA_GUID)
    if payload and payload.get("tool") == TOOL_ID and payload.get("managed"):
        return payload
    return None


def read_element_payload(element):
    """Return managed-element identity, or None when the element is not ours."""
    payload = _read_entity(element, ELEMENT_SCHEMA_GUID)
    if payload and payload.get("tool") == TOOL_ID and payload.get("managed"):
        return payload
    return None


def find_legend(doc, source_view, definition_id):
    """Find the generated legend for a source view and definition."""
    source_id = None
    source_unique = None
    if source_view is not None:
        from version_adapter import element_id_value
        source_id = element_id_value(source_view.Id)
        source_unique = source_view.UniqueId
    for view, payload in iter_generated_legends(doc):
        if payload.get("legend_definition_id") != definition_id:
            continue
        if source_unique and payload.get("source_view_unique_id") == source_unique:
            return view
        if source_id is not None and int(payload.get("source_view_id", -1)) == int(source_id):
            return view
    return _find_legend_in_json(doc, source_unique, source_id, definition_id)


ROLE_VIEW_LEGEND = "generated_legend"
ROLE_LIBRARY_LEGEND = "library_legend"


def iter_generated_legends(doc, role=ROLE_VIEW_LEGEND):
    """Yield (view, payload) for tool-managed legends of one role.

    ``generated_legend`` is the view/sheet type legend. ``library_legend`` is built
    from the Excel library. Pass role=None for both.
    """
    from version_adapter import get_db
    DB = get_db()
    collector = DB.FilteredElementCollector(doc).OfClass(DB.View)
    for view in collector:
        try:
            if view.IsTemplate or view.ViewType != DB.ViewType.Legend:
                continue
        except Exception:
            continue
        payload = read_view_payload(view)
        if not payload:
            continue
        if role is not None and payload.get("role", ROLE_VIEW_LEGEND) != role:
            continue
        yield view, payload


def find_library_legend(doc, category, sheet=None):
    """Find the library legend for a category: the master (sheet None) or the one for ``sheet``."""
    sheet_unique = sheet.UniqueId if sheet is not None else None
    for view, payload in iter_generated_legends(doc, ROLE_LIBRARY_LEGEND):
        if payload.get("category") != category:
            continue
        if payload.get("sheet_unique_id") == sheet_unique:
            return view
    return None


def build_library_view_payload(category, codes, sheet, content_hash_value):
    """Identity stored on a library legend view."""
    from version_adapter import element_id_value
    return {
        "tool": TOOL_ID,
        "role": ROLE_LIBRARY_LEGEND,
        "managed": True,
        "category": category,
        "codes": list(codes),
        "sheet_id": element_id_value(sheet.Id) if sheet is not None else None,
        "sheet_unique_id": sheet.UniqueId if sheet is not None else None,
        "legend_definition_id": "library:{0}".format(category),
        "updated_utc": utc_now(),
        "tool_version": TOOL_VERSION,
        "content_hash": content_hash_value,
        "storage": "extensible_storage",
    }


def build_library_element_payload(category, code, role):
    """Identity stored on each element of a library legend."""
    return {
        "tool": TOOL_ID,
        "managed": True,
        "role": role,
        "legend_definition_id": "library:{0}".format(category),
        "code": code,
        "tool_version": TOOL_VERSION,
    }


def collect_managed_elements(doc, legend_view):
    """Return tool-managed elements owned by the legend view."""
    from version_adapter import element_id_value, get_db
    DB = get_db()
    view_id = element_id_value(legend_view.Id)
    found = []
    seen = set()

    def _consider(element):
        if element is None:
            return
        identity = element_id_value(element.Id)
        if identity in seen:
            return
        owner = getattr(element, "OwnerViewId", None)
        if owner is not None and element_id_value(owner) not in (-1, view_id):
            return
        payload = read_element_payload(element)
        if not payload:
            return
        seen.add(identity)
        found.append((element, payload))

    # Everything the tool creates in a legend (components, text, detail lines,
    # view-specific reference planes, dimensions) is owned by that view. The
    # owner filter is a quick filter and also returns elements hidden in the view.
    # The view-scoped collector is kept as a second pass. Neither scans the model.
    try:
        owned = DB.FilteredElementCollector(doc).WherePasses(DB.ElementOwnerViewFilter(legend_view.Id))
        for element in owned.WhereElementIsNotElementType():
            _consider(element)
    except Exception:
        pass
    try:
        for element in DB.FilteredElementCollector(doc, legend_view.Id).WhereElementIsNotElementType():
            _consider(element)
    except Exception:
        pass
    return found


def delete_managed_elements(doc, elements):
    """Delete elements after proving each one is tool-managed."""
    from System.Collections.Generic import List
    from version_adapter import get_db
    DB = get_db()
    ids = List[DB.ElementId]()
    for element in elements:
        payload = read_element_payload(element)
        if not payload:
            raise LegendOperationError(
                "Refusing to delete element {0}. It is not marked as tool-managed legend content.".format(
                    element.Id
                )
            )
        ids.Add(element.Id)
    if ids.Count:
        doc.Delete(ids)


def try_write_configured_parameter(legend_view, parameter_name, source_view_id, definition_id):
    """Write the optional view parameter when the project already has it.

    The tool does not create project parameters.
    """
    if not parameter_name:
        return None
    parameter = legend_view.LookupParameter(parameter_name)
    if parameter is None or parameter.IsReadOnly:
        return (
            "View parameter '{0}' was not found or is read-only. "
            "Identity is stored with Extensible Storage. The tool did not create a project parameter.".format(
                parameter_name
            )
        )
    value = "{0}|{1}".format(definition_id, int(source_view_id))
    try:
        parameter.Set(value)
    except Exception as ex:
        return "View parameter '{0}' could not be set. {1}".format(parameter_name, ex)
    return None


def _schema(guid_text, name, documentation):
    from System import Guid, String
    from version_adapter import get_db
    DB = get_db()
    guid = Guid(guid_text)
    schema = DB.ExtensibleStorage.Schema.Lookup(guid)
    if schema is not None and schema.IsValidObject:
        return schema
    builder = DB.ExtensibleStorage.SchemaBuilder(guid)
    builder.SetSchemaName(name)
    builder.SetDocumentation(documentation)
    builder.SetVendorId(VENDOR_ID)
    builder.SetReadAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    # Public write is required: pyRevit does not run as a registered vendor add-in.
    builder.SetWriteAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    builder.AddSimpleField("Payload", String)
    return builder.Finish()


def _write_entity(element, guid_text, name, documentation, payload):
    schema = _schema(guid_text, name, documentation)
    from version_adapter import get_db
    DB = get_db()
    entity = DB.ExtensibleStorage.Entity(schema)
    field = schema.GetField("Payload")
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    try:
        entity.Set(field, text)
    except Exception:
        from System import String
        entity.Set[String](field, text)
    element.SetEntity(entity)


def _read_entity(element, guid_text):
    if element is None:
        return None
    try:
        from System import Guid, String
        from version_adapter import get_db
        DB = get_db()
        schema = DB.ExtensibleStorage.Schema.Lookup(Guid(guid_text))
        if schema is None or not schema.IsValidObject:
            return None
        entity = element.GetEntity(schema)
        if entity is None or not entity.IsValid():
            return None
        field = schema.GetField("Payload")
        try:
            text = entity.Get[String](field)
        except Exception:
            text = entity.Get(field)
        if not text:
            return None
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _registry_storage(doc):
    from version_adapter import get_db
    DB = get_db()
    for storage in DB.FilteredElementCollector(doc).OfClass(DB.DataStorage):
        if _read_entity(storage, REGISTRY_SCHEMA_GUID):
            return storage
    created = DB.DataStorage.Create(doc)
    return created


def _update_registry(doc, view_payload, legend_view):
    from version_adapter import element_id_value
    storage = _registry_storage(doc)
    current = _read_entity(storage, REGISTRY_SCHEMA_GUID) or {"tool": TOOL_ID, "legends": []}
    legends = [item for item in current.get("legends", []) if isinstance(item, dict)]
    legend_id = element_id_value(legend_view.Id)
    kept = [item for item in legends if int(item.get("legend_view_id", -1)) != legend_id]
    kept.append({
        "legend_view_id": legend_id,
        "legend_unique_id": legend_view.UniqueId,
        "source_view_id": view_payload.get("source_view_id"),
        "source_view_unique_id": view_payload.get("source_view_unique_id"),
        "legend_definition_id": view_payload.get("legend_definition_id"),
        "content_hash": view_payload.get("content_hash"),
        "updated_utc": view_payload.get("updated_utc"),
    })
    payload = {"tool": TOOL_ID, "managed": True, "legends": kept}
    _write_entity(storage, REGISTRY_SCHEMA_GUID, REGISTRY_SCHEMA_NAME, "Generated legend index.", payload)


def _registry_file(doc):
    folder = os.path.join(extension_root(), "config", "registries")
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return os.path.join(folder, document_key(doc) + ".json")


def _write_json_registry(doc, legend_view, view_payload):
    from version_adapter import element_id_value
    path = _registry_file(doc)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            current = json.load(handle)
    else:
        current = {"legends": []}
    legend_id = element_id_value(legend_view.Id)
    legends = [item for item in current.get("legends", []) if int(item.get("legend_view_id", -1)) != legend_id]
    legends.append({
        "legend_view_id": legend_id,
        "legend_unique_id": legend_view.UniqueId,
        "source_view_id": view_payload.get("source_view_id"),
        "source_view_unique_id": view_payload.get("source_view_unique_id"),
        "legend_definition_id": view_payload.get("legend_definition_id"),
        "content_hash": view_payload.get("content_hash"),
    })
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"legends": legends}, handle, indent=2)
    view_payload["json_registry"] = path


def _find_legend_in_json(doc, source_unique, source_id, definition_id):
    path = _registry_file(doc)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            current = json.load(handle)
    except Exception:
        return None
    from version_adapter import get_db, make_element_id
    DB = get_db()
    for item in current.get("legends", []):
        if item.get("legend_definition_id") != definition_id:
            continue
        unique_match = source_unique and item.get("source_view_unique_id") == source_unique
        id_match = source_id is not None and int(item.get("source_view_id", -1)) == int(source_id)
        if not unique_match and not id_match:
            continue
        view = doc.GetElement(item.get("legend_unique_id"))
        if view is None and item.get("legend_view_id") is not None:
            view = doc.GetElement(make_element_id(item.get("legend_view_id")))
        if view is not None and view.ViewType == DB.ViewType.Legend:
            return view
    return None
