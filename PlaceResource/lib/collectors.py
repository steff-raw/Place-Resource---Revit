# -*- coding: utf-8 -*-
"""Collect elements that are visible in a source view.

A view-scoped FilteredElementCollector is the primary filter. It is not a
perfect picture of every pixel Revit draws. The differences are recorded on
the result and in the README.
"""

from category_adapter import get_adapter
from parameter_service import ParameterResolver, RevitParameterReader, format_layers


class TypeRecord(object):
    """One unique element type found in the source view."""

    def __init__(self, type_id):
        self.type_id = int(type_id)
        self.type_unique_id = None
        self.family_name = ""
        self.type_name = ""
        self.instance_ids = []
        self.raw = {}
        self.display = {}
        self.resolution = []
        self.layers = []
        self.is_linked = False
        self.link_name = None
        self.warnings = []
        self.notices = []

    def as_hash_record(self):
        return {"type_id": self.type_id, "display": dict(self.display)}


class CollectionResult(object):
    """Visible instances, unique types, and the reasons other elements were skipped."""

    def __init__(self):
        self.instance_count = 0
        self.types = []
        self.excluded = []
        self.warnings = []
        self.notices = []
        self.view_info = {}
        self.errors = []
        self.seen_instances = set()

    @property
    def unique_type_count(self):
        return len(self.types)


def is_sheet(view):
    """Return True for a drawing sheet."""
    try:
        return view.ViewType.ToString() == "DrawingSheet"
    except Exception:
        return False


def sheet_source_views(doc, sheet, view_types):
    """Return the model views placed on ``sheet`` whose view type is in ``view_types``.

    Legends, schedules, drafting views and other view types are skipped. Order is by view name.
    """
    from version_adapter import element_id_value, get_db
    DB = get_db()
    allowed = set(view_types or [])
    views = []
    seen = set()
    try:
        view_ids = list(sheet.GetAllPlacedViews())
    except Exception:
        view_ids = [viewport.ViewId for viewport in DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.Viewport)]
    for view_id in view_ids:
        view = doc.GetElement(view_id)
        if view is None or element_id_value(view.Id) in seen:
            continue
        try:
            if view.IsTemplate or view.ViewType.ToString() not in allowed:
                continue
        except Exception:
            continue
        seen.add(element_id_value(view.Id))
        views.append(view)
    views.sort(key=lambda item: item.Name)
    return views


def source_display_name(view):
    """Return the name used in legend names and reports. Sheets show number and name."""
    if is_sheet(view):
        number = getattr(view, "SheetNumber", "") or ""
        return "{0} - {1}".format(number, view.Name) if number else view.Name
    return view.Name


def type_marks_for_source(doc, source, category_name, view_types):
    """Return the sorted Type Marks of ``category_name`` elements visible in ``source``.

    ``source`` is a model view, or a sheet (its placed views of ``view_types`` are used).
    Elements come from view-scoped collectors, so hidden and filtered elements are left out.
    """
    from errors import ConfigurationError
    from version_adapter import builtin_parameter, element_id_value, get_db
    DB = get_db()
    built_in = getattr(DB.BuiltInCategory, category_name, None)
    if built_in is None:
        raise ConfigurationError("Revit has no built-in category named {0}.".format(category_name))
    views = sheet_source_views(doc, source, view_types) if is_sheet(source) else [source]
    mark_parameter = builtin_parameter("ALL_MODEL_TYPE_MARK")
    marks = set()
    seen_types = set()
    for view in views:
        collector = DB.FilteredElementCollector(doc, view.Id).OfCategory(built_in).WhereElementIsNotElementType()
        for element in collector:
            type_id = element.GetTypeId()
            key = element_id_value(type_id)
            if key < 0 or key in seen_types:
                continue
            seen_types.add(key)
            mark = type_mark(doc.GetElement(type_id), mark_parameter)
            if mark:
                marks.add(mark)
    return sorted(marks)


def type_mark(type_element, mark_parameter=None):
    """Return the Type Mark text of an element type, or ''."""
    if type_element is None:
        return ""
    if mark_parameter is None:
        from version_adapter import builtin_parameter
        mark_parameter = builtin_parameter("ALL_MODEL_TYPE_MARK")
    parameter = None
    try:
        if mark_parameter is not None:
            parameter = type_element.get_Parameter(mark_parameter)
        if parameter is None:
            parameter = type_element.LookupParameter("Type Mark")
        if parameter is None:
            return ""
        return (parameter.AsString() or "").strip()
    except Exception:
        return ""


def collect_visible_types(doc, view, definition, aliases):
    """Collect unique types visible in ``view`` for one legend definition.

    When ``view`` is a sheet, every placed view whose type is in the definition's
    source_view_types is collected and the types are merged. A wall seen in
    several views counts once.
    """
    result = CollectionResult()
    adapter = get_adapter(definition["category"])
    result.view_info = _view_info(view)
    if is_sheet(view):
        views = sheet_source_views(doc, view, definition.get("source_view_types"))
        result.view_info["source_views"] = [item.Name for item in views]
        if views:
            result.notices.append("Sheet '{0}': types were collected from {1} view(s): {2}.".format(
                source_display_name(view), len(views), ", ".join(item.Name for item in views)
            ))
        else:
            result.warnings.append(
                "Sheet '{0}' has no {1} view placed on it, so no types were collected.".format(
                    source_display_name(view), " / ".join(definition.get("source_view_types") or [])
                )
            )
    else:
        views = [view]

    include = definition.get("include") or {}
    grouped = {}
    for source in views:
        for notice in _visibility_notices(source):
            if notice not in result.notices:
                result.notices.append(notice)
        _warn_if_category_hidden(doc, source, adapter, result)
        for element in _view_instances(doc, source, adapter):
            _consume_instance(doc, source, adapter, element, include, grouped, result, is_linked=False, link_name=None)

    if include.get("linked_models"):
        for source in views:
            _collect_links(doc, source, adapter, include, definition, grouped, result)
    else:
        result.notices.append("Linked models are excluded by the legend definition.")

    resolver = ParameterResolver(aliases, definition.get("type_rules") or {})
    result.types = _build_records(doc, adapter, grouped, definition, resolver, result)
    _duplicate_mark_warning(result, definition)
    return result


def _view_instances(doc, view, adapter):
    from version_adapter import get_db
    DB = get_db()
    collector = DB.FilteredElementCollector(doc, view.Id)
    collector = collector.OfCategory(adapter.built_in_category()).WhereElementIsNotElementType()
    return list(collector)


def _consume_instance(doc, view, adapter, element, include, grouped, result, is_linked, link_name):
    from version_adapter import element_id_value
    type_id = element.GetTypeId()
    if type_id is None or element_id_value(type_id) < 0:
        result.excluded.append({"element_id": element_id_value(element.Id), "reason": "invalid_type"})
        return
    hidden, hidden_reason = _hidden_in_view(view, element)
    if hidden:
        result.excluded.append({"element_id": element_id_value(element.Id), "reason": hidden_reason})
        return
    try:
        facts = adapter.describe_instance(doc, view, element)
    except Exception as ex:
        result.excluded.append({
            "element_id": element_id_value(element.Id),
            "reason": "describe_failed",
            "detail": str(ex),
        })
        return
    facts["is_linked"] = is_linked or facts.get("is_linked")
    facts["link_name"] = link_name
    included, reason = adapter.include_instance(facts, include)
    if not included:
        result.excluded.append({"element_id": element_id_value(element.Id), "reason": reason})
        return
    if facts.get("kind") == "unknown" and facts["type_id"] not in grouped:
        result.notices.append(
            "A wall with type id {0} has an unrecognised wall kind and was included.".format(facts.get("type_id"))
        )
    instance_key = ("host", element_id_value(element.Id))
    if instance_key in result.seen_instances:
        return
    result.seen_instances.add(instance_key)
    bucket = grouped.get(facts["type_id"])
    if bucket is None:
        grouped[facts["type_id"]] = facts
        facts["instance_ids"] = [element_id_value(element.Id)]
    else:
        bucket["instance_ids"].append(element_id_value(element.Id))
    result.instance_count += 1


def _collect_links(doc, view, adapter, include, definition, grouped, result):
    from version_adapter import element_id_value, get_db
    DB = get_db()
    result.warnings.append(
        "Linked elements are collected from each loaded link document. "
        "Host view filters, phase filters, crop regions, and temporary hide "
        "do not apply to those elements with the same fidelity as host elements. "
        "A linked type is used only when a host type matches its family and type name."
    )
    try:
        links = DB.FilteredElementCollector(doc, view.Id).OfClass(DB.RevitLinkInstance)
    except Exception as ex:
        result.warnings.append("Linked models could not be read. {0}".format(ex))
        return
    for link in links:
        try:
            if link.IsHidden(view):
                continue
        except Exception:
            pass
        link_doc = None
        try:
            link_doc = link.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is None:
            result.warnings.append("Link '{0}' is not loaded, so its elements were skipped.".format(link.Name))
            continue
        try:
            elements = DB.FilteredElementCollector(link_doc).OfCategory(adapter.built_in_category()).WhereElementIsNotElementType()
        except Exception as ex:
            result.warnings.append("Could not collect elements from link '{0}'. {1}".format(link.Name, ex))
            continue
        for element in elements:
            _consume_linked_element(doc, view, adapter, element, include, definition, grouped, result, link)


def _consume_linked_element(doc, view, adapter, element, include, definition, grouped, result, link):
    from version_adapter import element_id_value
    instance_key = ("link", element_id_value(link.Id), element_id_value(element.Id))
    if instance_key in result.seen_instances:
        return
    try:
        facts = adapter.describe_instance(doc, view, element)
    except Exception:
        facts = {
            "element": element,
            "type_element": None,
            "kind": "unknown",
            "is_in_place": False,
            "is_linked": True,
            "is_demolished": False,
            "is_stacked_member": False,
            "parts_replace_original": False,
            "type_id": element_id_value(element.GetTypeId()),
        }
    facts["is_linked"] = True
    included, reason = adapter.include_instance(facts, include)
    if not included and reason != "linked_model":
        result.excluded.append({"element_id": element_id_value(element.Id), "reason": reason, "link": link.Name})
        return
    type_element = facts.get("type_element")
    if type_element is None:
        try:
            type_element = element.Document.GetElement(element.GetTypeId())
        except Exception:
            type_element = None
    host_type = _match_host_type(doc, adapter, type_element, definition)
    if host_type is None:
        family_name, type_name = _type_names(type_element)
        result.warnings.append(
            "Linked type '{0}: {1}' from '{2}' has no matching type in this model. "
            "It was not added to the legend because a legend component cannot use a type from another document.".format(
                family_name, type_name, link.Name
            )
        )
        return
    result.seen_instances.add(instance_key)
    host_type_id = element_id_value(host_type.Id)
    bucket = grouped.get(host_type_id)
    if bucket is None:
        grouped[host_type_id] = {
            "element": element,
            "type_element": host_type,
            "kind": facts.get("kind"),
            "is_in_place": False,
            "is_linked": True,
            "link_name": link.Name,
            "is_demolished": False,
            "is_stacked_member": False,
            "parts_replace_original": False,
            "type_id": host_type_id,
            "instance_ids": [element_id_value(element.Id)],
        }
    else:
        bucket["instance_ids"].append(element_id_value(element.Id))
        bucket["is_linked"] = True
        bucket["link_name"] = link.Name
    result.instance_count += 1


def _match_host_type(doc, adapter, linked_type, definition):
    if linked_type is None:
        return None
    family_name, type_name = _type_names(linked_type)
    if not type_name:
        return None
    from version_adapter import get_db
    DB = get_db()
    collector = DB.FilteredElementCollector(doc).OfCategory(adapter.built_in_category()).WhereElementIsElementType()
    for host_type in collector:
        host_family, host_name = _type_names(host_type)
        if host_family == family_name and host_name == type_name:
            return host_type
    return None


def _build_records(doc, adapter, grouped, definition, resolver, result):
    records = []
    labels = definition.get("labels") or []
    sort_parameters = [rule.get("parameter") for rule in definition.get("sort") or []]
    parameter_keys = []
    for key in sort_parameters + [label.get("parameter") for label in labels]:
        if key and key not in parameter_keys:
            parameter_keys.append(key)
    for extra in ("Family Name", "Type Name", "Type Mark", "Description", "Function",
                  "Width", "Fire Rating", "Acoustic Rating", "Assembly Code", "Keynote"):
        if extra not in parameter_keys:
            parameter_keys.append(extra)
    for type_id, facts in grouped.items():
        record = TypeRecord(type_id)
        type_element = facts.get("type_element")
        if type_element is None:
            result.warnings.append("Type id {0} could not be read and was skipped.".format(type_id))
            continue
        record.type_unique_id = getattr(type_element, "UniqueId", None)
        record.family_name, record.type_name = _type_names(type_element)
        record.instance_ids = list(facts.get("instance_ids") or [])
        record.is_linked = bool(facts.get("is_linked"))
        record.link_name = facts.get("link_name")
        record.layers = _compound_layers(doc, type_element)
        layer_text = format_layers(record.layers, decimals=1)
        computed = {}
        if record.layers:
            computed["Compound Structure"] = layer_text
            computed["Material Layers"] = layer_text
            computed["Layer Thicknesses"] = " / ".join(
                "{0} mm".format(layer.get("width_mm")) for layer in record.layers
            )
        reader = RevitParameterReader(type_element, computed=computed)
        label_by_key = {label["parameter"]: label for label in labels}
        for key in parameter_keys:
            label = label_by_key.get(key) or {}
            resolved = resolver.resolve(
                key,
                reader,
                required=bool(label.get("required", False)),
                default=label.get("default"),
                value_format=label.get("format"),
                decimals=label.get("decimals", 0),
            )
            record.raw[key] = resolved.raw_value
            record.display[key] = resolved.display_value
            record.resolution.append({
                "parameter": key,
                "source": resolved.source,
                "warning": resolved.warning,
                "notice": resolved.notice,
            })
            if resolved.warning:
                message = "{0} ({1}: {2}): {3}".format(
                    record.type_name or type_id,
                    record.family_name,
                    key,
                    resolved.warning,
                )
                record.warnings.append(message)
                if label.get("required") or definition.get("type_rules", {}).get("unmapped_parameter") == "error":
                    result.warnings.append(message)
            if resolved.notice:
                record.notices.append(resolved.notice)
        if "Family Name" not in record.display or record.display.get("Family Name") in (None, "", "–"):
            record.display["Family Name"] = record.family_name
            record.raw["Family Name"] = record.family_name
        if "Type Name" not in record.display or record.display.get("Type Name") in (None, "", "–"):
            record.display["Type Name"] = record.type_name
            record.raw["Type Name"] = record.type_name
        records.append(record)
    from layout_engine import sort_records
    return sort_records(records, definition.get("sort") or [], _sort_value)


def _sort_value(record, parameter):
    if parameter == "__type_id__":
        return record.type_id
    if parameter in record.raw and record.raw.get(parameter) is not None:
        return record.raw.get(parameter)
    return record.display.get(parameter)


def _compound_layers(doc, type_element):
    try:
        structure = type_element.GetCompoundStructure()
    except Exception:
        return []
    if structure is None:
        return []
    layers = []
    try:
        raw_layers = structure.GetLayers()
    except Exception:
        return []
    from units import format_millimetres, internal_to_mm
    for layer in raw_layers:
        material_name = "No material"
        try:
            material = doc.GetElement(layer.MaterialId)
            if material is not None:
                material_name = material.Name
        except Exception:
            material_name = "No material"
        try:
            function_name = layer.Function.ToString()
        except Exception:
            function_name = "Unknown"
        try:
            width_feet = float(layer.Width)
        except Exception:
            width_feet = 0.0
        layers.append({
            "function": function_name,
            "material": material_name,
            "width_feet": width_feet,
            "width_mm": round(internal_to_mm(width_feet), 2),
            "width_mm_text": format_millimetres(width_feet, 1),
        })
    return layers


def _duplicate_mark_warning(result, definition):
    groups = {}
    for record in result.types:
        mark = record.display.get("Type Mark")
        if mark in (None, "", "–"):
            continue
        groups.setdefault(str(mark), []).append(record)
    for mark, records in groups.items():
        if len(records) > 1:
            names = ", ".join(record.type_name or str(record.type_id) for record in records)
            result.warnings.append(
                "Type Mark '{0}' is used by {1} types ({2}). "
                "Each type stays as its own legend entry.".format(mark, len(records), names)
            )


def _hidden_in_view(view, element):
    try:
        if element.IsHidden(view):
            return True, "element_hidden"
    except Exception:
        pass
    try:
        from version_adapter import get_db
        DB = get_db()
        if view.IsInTemporaryViewMode(DB.TemporaryViewMode.TemporaryHideIsolate):
            hidden_ids = _temporary_hidden_ids(view)
            from version_adapter import element_id_value
            if hidden_ids is not None and element_id_value(element.Id) in hidden_ids:
                return True, "temporary_hide"
    except Exception:
        pass
    return False, None


def _temporary_hidden_ids(view):
    from version_adapter import element_id_value
    for method_name in ("GetTemporaryHiddenElements", "GetTemporaryViewModeHideIsolateElements"):
        method = getattr(view, method_name, None)
        if method is None:
            continue
        try:
            return set(element_id_value(item) for item in method())
        except Exception:
            continue
    return None


def _warn_if_category_hidden(doc, view, adapter, result):
    from version_adapter import get_db
    DB = get_db()
    try:
        category = DB.Category.GetCategory(doc, adapter.built_in_category())
        if category is not None and view.GetCategoryHidden(category.Id):
            result.warnings.append(
                "The {0} category is hidden in '{1}'. The view-scoped collector will not return those elements.".format(
                    category.Name, view.Name
                )
            )
    except Exception:
        pass


def _view_info(view):
    info = {"view_type": "", "detail_level": "", "discipline": "", "phase": "", "phase_filter": "", "scale": None}
    try:
        info["view_type"] = view.ViewType.ToString()
    except Exception:
        pass
    try:
        info["detail_level"] = view.DetailLevel.ToString()
    except Exception:
        pass
    try:
        info["discipline"] = view.Discipline.ToString()
    except Exception:
        pass
    try:
        info["scale"] = int(view.Scale)
    except Exception:
        pass
    info["phase"] = _parameter_text(view, "VIEW_PHASE")
    info["phase_filter"] = _parameter_text(view, "VIEW_PHASE_FILTER")
    try:
        from version_adapter import element_id_value, get_db
        DB = get_db()
        active = DB.DesignOption.GetActiveDesignOptionId(view.Document)
        info["active_design_option_id"] = element_id_value(active)
    except Exception:
        info["active_design_option_id"] = None
    return info


def _visibility_notices(view):
    notices = [
        "Elements come from a view-scoped collector. Revit applies the view phase, phase filter, "
        "design option visibility, category visibility, view filters that hide elements, permanent "
        "element hide, closed worksets, and the crop region before the tool sees the elements.",
        "Detail level and view discipline are reported but are not an extra filter. "
        "They change graphics more often than they remove elements from the collector.",
        "The active design option in the UI is not used as a filter. The view's own design option visibility is.",
        "Parts shown instead of the original wall are not wall types. When the view is set to Show Parts Only, "
        "the original wall is excluded unless when_parts_replace_original is true.",
    ]
    try:
        from version_adapter import get_db
        DB = get_db()
        if view.IsInTemporaryViewMode(DB.TemporaryViewMode.TemporaryHideIsolate):
            if _temporary_hidden_ids(view) is None:
                notices.append(
                    "Temporary hide/isolate is active. This Revit version did not expose a temporary-hide list, "
                    "so only the view-scoped collector was used for that mode."
                )
            else:
                notices.append("Temporary hide/isolate is active and those hidden elements were excluded.")
    except Exception:
        notices.append(
            "Temporary hide/isolate could not be queried. Visibility follows the view-scoped collector."
        )
    try:
        filters = list(view.GetFilters())
        if filters:
            notices.append(
                "{0} view filter(s) are attached. Filters that hide elements are applied by the collector "
                "and are not evaluated a second time.".format(len(filters))
            )
    except Exception:
        pass
    return notices


def _parameter_text(element, builtin_name):
    from version_adapter import builtin_parameter
    built_in = builtin_parameter(builtin_name)
    if built_in is None:
        return ""
    try:
        parameter = element.get_Parameter(built_in)
        if parameter is None:
            return ""
        return parameter.AsValueString() or ""
    except Exception:
        return ""


def _type_names(type_element):
    if type_element is None:
        return "", ""
    family_name = ""
    try:
        family_name = type_element.FamilyName or ""
    except Exception:
        family_name = ""
    try:
        type_name = type_element.Name or ""
    except Exception:
        type_name = ""
    return family_name, type_name
