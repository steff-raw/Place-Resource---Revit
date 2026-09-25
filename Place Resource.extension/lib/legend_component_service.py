# -*- coding: utf-8 -*-
"""Create legend components by duplicating a seed component.

Revit does not provide a public LegendComponent.Create method. The supported
path is a seed component in the template legend, copied with CopyElement, then
retargeted through the LEGEND_COMPONENT parameter. This module does not draw
detail lines unless the JSON flag fallback_detail_lines is true.
"""

from errors import LegendOperationError, UnsupportedRevitOperationError
from logging_service import get_logger
from units import mm_to_internal

LOGGER = get_logger("legend_component_service")

_DIRECTION_SYNONYMS = {
    "Section": ("section",),
    "FloorPlan": ("floor plan", "floorplan", "plan"),
    "ElevationFront": ("elevation front", "front", "elevation"),
    "ElevationBack": ("elevation back", "back"),
    "ElevationLeft": ("elevation left", "left"),
    "ElevationRight": ("elevation right", "right"),
}


class LegendComponentService(object):
    """Copy and retarget seed legend components inside one legend view."""

    def __init__(self, doc, legend_view):
        self.doc = doc
        self.legend_view = legend_view

    def find_components(self, view=None):
        """Return legend components in a view."""
        from version_adapter import get_db
        DB = get_db()
        target = view or self.legend_view
        collector = DB.FilteredElementCollector(self.doc, target.Id)
        collector = collector.OfCategory(DB.BuiltInCategory.OST_LegendComponents).WhereElementIsNotElementType()
        return list(collector)

    def component_type_id(self, component):
        """Return the ElementId stored on a legend component."""
        parameter = self._component_parameter(component)
        if parameter is None:
            return None
        try:
            return parameter.AsElementId()
        except Exception:
            return None

    def assert_seed_matches_category(self, seed, type_element):
        """Refuse to point a seed at a type from another category."""
        seed_type_id = self.component_type_id(seed)
        seed_type = self.doc.GetElement(seed_type_id) if seed_type_id is not None else None
        if seed_type is None or type_element is None:
            raise LegendOperationError(
                "The seed legend component has no component type. "
                "Open the template legend and set its Component Type before running the tool."
            )
        seed_category = getattr(seed_type, "Category", None)
        type_category = getattr(type_element, "Category", None)
        if seed_category is None or type_category is None:
            raise LegendOperationError("Could not compare the seed component category with the target type.")
        from version_adapter import element_id_value
        if element_id_value(seed_category.Id) != element_id_value(type_category.Id):
            raise LegendOperationError(
                "The template seed is a {0} component, but the legend definition needs {1}. "
                "Place a seed of the correct category in the template legend. "
                "The tool will not draw a substitute.".format(seed_category.Name, type_category.Name)
            )

    def copy_component(self, seed, offset_index):
        """Copy a seed legend component. Raises if Revit refuses."""
        from version_adapter import get_db
        DB = get_db()
        offset = DB.XYZ(float(offset_index + 1) * 10.0, 0, 0)
        try:
            new_id = DB.ElementTransformUtils.CopyElement(self.doc, seed.Id, offset)
        except Exception as ex:
            raise UnsupportedRevitOperationError(
                "Revit could not copy the seed legend component. "
                "Confirm the template legend contains one legend component and that this Revit "
                "version allows ElementTransformUtils.CopyElement for legend components. {0}".format(ex)
            )
        element = self.doc.GetElement(new_id)
        if element is None:
            raise UnsupportedRevitOperationError(
                "Revit copied a legend component but did not return the new element."
            )
        return element

    def assign_type(self, component, type_element):
        """Set LEGEND_COMPONENT and read it back. Raise if Revit rejects the change."""
        from version_adapter import element_id_value
        self._assert_safe_target(component)
        parameter = self._component_parameter(component)
        if parameter is None:
            raise UnsupportedRevitOperationError(
                "This Revit version has no LEGEND_COMPONENT parameter on legend components. "
                "The seed component could not be retargeted."
            )
        if parameter.IsReadOnly:
            raise UnsupportedRevitOperationError(
                "The legend component type parameter is read-only in this Revit version. "
                "The tool did not replace the component with detail lines."
            )
        try:
            wrote = parameter.Set(type_element.Id)
        except Exception as ex:
            raise UnsupportedRevitOperationError(
                "Revit rejected the legend component type change for '{0}'. {1}".format(
                    _element_name(type_element), ex
                )
            )
        if wrote is False:
            raise UnsupportedRevitOperationError(
                "Revit did not accept type '{0}' on the legend component.".format(_element_name(type_element))
            )
        current = parameter.AsElementId()
        if element_id_value(current) != element_id_value(type_element.Id):
            raise UnsupportedRevitOperationError(
                "Revit rejected the legend component type change. Requested '{0}' ({1}) "
                "but the component still reports type id {2}.".format(
                    _element_name(type_element),
                    element_id_value(type_element.Id),
                    element_id_value(current),
                )
            )

    def apply_representation(self, component, representation):
        """Keep the seed view direction unless it already matches the configuration.

        Host length is set only when a writable length parameter exists.
        Returns a list of warnings. It does not invent a view-direction integer.
        """
        warnings = []
        warnings.extend(self._check_view_direction(component, representation.get("view_direction")))
        warnings.extend(self._try_set_host_length(component, representation.get("host_length_mm")))
        return warnings

    def apply_view_settings_on_create(self, representation):
        """Set scale and detail level on a newly duplicated legend view."""
        from version_adapter import get_db
        DB = get_db()
        warnings = []
        detail_name = representation.get("detail_level") or "Fine"
        detail = getattr(DB.ViewDetailLevel, detail_name, None)
        if detail is None:
            warnings.append("Detail level '{0}' is not available in this Revit version.".format(detail_name))
        else:
            try:
                self.legend_view.DetailLevel = detail
            except Exception as ex:
                warnings.append("The legend detail level could not be set. {0}".format(ex))
        try:
            self.legend_view.Scale = int(representation.get("scale"))
        except Exception as ex:
            warnings.append("The legend scale could not be set. {0}".format(ex))
        return warnings

    def create_text(self, position, text, text_type_id, width_internal):
        """Create a text note. Revit rejects empty text, so callers pass a visible token."""
        from version_adapter import get_db
        DB = get_db()
        self._assert_text_type(text_type_id)
        content = text if text else "–"
        try:
            note = DB.TextNote.Create(self.doc, self.legend_view.Id, position, content, text_type_id)
        except Exception as ex:
            raise LegendOperationError(
                "Could not create legend text '{0}'. Confirm the text note type exists and the view is editable. {1}".format(
                    content, ex
                )
            )
        try:
            note.HorizontalAlignment = DB.HorizontalTextAlignment.Left
        except Exception:
            pass
        if width_internal and width_internal > 0:
            try:
                note.Width = float(width_internal)
            except Exception as ex:
                LOGGER.warning("Text note width was not applied: %s", ex)
        return note

    def set_text(self, note, text):
        """Update a managed text note."""
        content = text if text else "–"
        try:
            if note.Text != content:
                note.Text = content
                return True
        except Exception as ex:
            raise LegendOperationError("Could not update legend text. {0}".format(ex))
        return False

    def try_layer_references(self, component, type_element, managed_writer):
        """Create view-specific reference planes when the bbox matches the wall width.

        Returns (elements, warnings). On failure the caller rolls back a subtransaction.
        """
        from version_adapter import get_db
        DB = get_db()
        structure = None
        try:
            structure = type_element.GetCompoundStructure()
        except Exception:
            structure = None
        if structure is None:
            return [], ["Type '{0}' has no compound structure, so layer reference planes were skipped.".format(
                _element_name(type_element)
            )]
        try:
            layers = list(structure.GetLayers())
        except Exception as ex:
            return [], ["Compound structure layers could not be read. {0}".format(ex)]
        if not layers:
            return [], ["Type '{0}' has no layers.".format(_element_name(type_element))]
        bbox = component.get_BoundingBox(self.legend_view)
        if bbox is None:
            return [], ["The legend component has no bounding box, so layer planes were not created."]
        structure_width = 0.0
        for layer in layers:
            structure_width += float(layer.Width)
        width = bbox.Max.X - bbox.Min.X
        height = bbox.Max.Y - bbox.Min.Y
        tolerance = mm_to_internal(5)
        if abs(width - structure_width) <= tolerance:
            axis = "x"
        elif abs(height - structure_width) <= tolerance:
            axis = "y"
        else:
            return [], [(
                "Layer reference planes were not created for '{0}'. "
                "The component bounding box ({1:.1f} mm by {2:.1f} mm) does not match the compound "
                "structure width ({3:.1f} mm). Confirm the seed view direction and host length.".format(
                    _element_name(type_element),
                    width * 304.8,
                    height * 304.8,
                    structure_width * 304.8,
                )
            )]
        created = []
        cursor = 0.0
        spans = [0.0]
        for layer in layers:
            cursor += float(layer.Width)
            spans.append(cursor)
        for offset in spans:
            plane = self._create_plane(DB, bbox, axis, offset)
            created.append(plane)
            managed_writer(plane, "layer_reference")
        dimension = self._create_dimension(DB, bbox, axis, created, structure_width)
        if dimension is not None:
            created.append(dimension)
            managed_writer(dimension, "layer_dimension")
        return created, []

    def create_detail_layer_lines(self, component, type_element, line_style, managed_writer):
        """Draw disconnected layer lines. Used only when JSON explicitly enables the fallback."""
        from version_adapter import get_db
        DB = get_db()
        warnings = [(
            "fallback_detail_lines is enabled. Layer lines are drafting graphics and are not "
            "linked to the wall type. The legend component is still the primary representation."
        )]
        structure = type_element.GetCompoundStructure()
        if structure is None:
            warnings.append("No compound structure was available for detail lines.")
            return [], warnings
        bbox = component.get_BoundingBox(self.legend_view)
        if bbox is None:
            warnings.append("No bounding box was available for detail lines.")
            return [], warnings
        graphics = _line_style(self.doc, line_style)
        created = []
        cursor = bbox.Min.X
        y0 = bbox.Min.Y
        y1 = bbox.Max.Y
        for layer in structure.GetLayers():
            cursor += float(layer.Width)
            line = DB.Line.CreateBound(DB.XYZ(cursor, y0, 0), DB.XYZ(cursor, y1, 0))
            curve = DB.DetailCurve.Create(self.doc, self.legend_view, line)
            if graphics is not None:
                curve.LineStyle = graphics
            created.append(curve)
            managed_writer(curve, "layer_line")
        return created, warnings

    def create_border(self, block, line_style, padding_internal, managed_writer):
        """Draw a managed rectangle around the layout block."""
        from version_adapter import get_db
        DB = get_db()
        graphics = _line_style(self.doc, line_style)
        if graphics is None:
            raise LegendOperationError(
                "Line style '{0}' was not found. Add it to the model or change styles.line_style "
                "in the legend settings.".format(line_style)
            )
        left = block["left"] - padding_internal
        right = block["right"] + padding_internal
        bottom = block["bottom"] - padding_internal
        top = block["top"] + padding_internal
        corners = [
            (DB.XYZ(left, bottom, 0), DB.XYZ(right, bottom, 0)),
            (DB.XYZ(right, bottom, 0), DB.XYZ(right, top, 0)),
            (DB.XYZ(right, top, 0), DB.XYZ(left, top, 0)),
            (DB.XYZ(left, top, 0), DB.XYZ(left, bottom, 0)),
        ]
        created = []
        for start, end in corners:
            curve = DB.DetailCurve.Create(self.doc, self.legend_view, DB.Line.CreateBound(start, end))
            curve.LineStyle = graphics
            created.append(curve)
            managed_writer(curve, "border")
        return created

    def measure(self, element):
        """Return a bounding box dictionary, or None when Revit has no box yet."""
        try:
            bbox = element.get_BoundingBox(self.legend_view)
        except Exception:
            return None
        if bbox is None:
            return None
        return {
            "min_x": bbox.Min.X,
            "min_y": bbox.Min.Y,
            "max_x": bbox.Max.X,
            "max_y": bbox.Max.Y,
            "width": bbox.Max.X - bbox.Min.X,
            "height": bbox.Max.Y - bbox.Min.Y,
        }

    def move_top_left(self, element, target_x, target_y):
        """Move an element so its bounding-box top-left meets the target."""
        from version_adapter import get_db
        DB = get_db()
        measured = self.measure(element)
        if measured is None:
            raise LegendOperationError(
                "Element {0} has no bounding box in the legend, so it could not be aligned.".format(element.Id)
            )
        delta = DB.XYZ(target_x - measured["min_x"], target_y - measured["max_y"], 0)
        if abs(delta.X) < 1e-9 and abs(delta.Y) < 1e-9:
            return
        DB.ElementTransformUtils.MoveElement(self.doc, element.Id, delta)

    def _check_view_direction(self, component, configured):
        if not configured:
            return []
        parameter = self._view_parameter(component)
        if parameter is None:
            return [(
                "View direction '{0}' was not applied. This Revit version has no writable "
                "LEGEND_COMPONENT_VIEW parameter. The seed component direction was kept.".format(configured)
            )]
        try:
            current_text = (parameter.AsValueString() or "").strip().lower()
        except Exception:
            current_text = ""
        accepted = _DIRECTION_SYNONYMS.get(configured, (configured.lower(),))
        if current_text and any(token in current_text or current_text in token for token in accepted):
            return []
        return [(
            "View direction '{0}' was not changed. The seed component reports '{1}'. "
            "The public API does not document a stable integer for legend view direction, "
            "so the tool keeps the seed value. Set the seed component to the required direction.".format(
                configured, parameter.AsValueString() if current_text else "an unreadable value"
            )
        )]

    def _try_set_host_length(self, component, host_length_mm):
        if not host_length_mm:
            return []
        parameter = self._length_parameter(component)
        if parameter is None or parameter.IsReadOnly:
            return [(
                "Host length {0} mm was not applied. No writable length parameter was found on the "
                "legend component. The seed component length was kept.".format(host_length_mm)
            )]
        target = mm_to_internal(host_length_mm)
        try:
            parameter.Set(target)
            current = parameter.AsDouble()
        except Exception as ex:
            return ["Host length could not be set on the legend component. {0}".format(ex)]
        if abs(current - target) > mm_to_internal(1):
            return [(
                "Host length was requested as {0} mm but the component reports {1:.1f} mm after the write.".format(
                    host_length_mm, current * 304.8
                )
            )]
        return []

    def _length_parameter(self, component):
        from version_adapter import builtin_parameter
        for builtin_name in ("LEGEND_COMPONENT_LENGTH",):
            built_in = builtin_parameter(builtin_name)
            if built_in is None:
                continue
            parameter = component.get_Parameter(built_in)
            if parameter is not None and not parameter.IsReadOnly:
                return parameter
        try:
            for parameter in component.Parameters:
                if parameter.IsReadOnly:
                    continue
                definition = parameter.Definition
                if definition is None:
                    continue
                if definition.Name in ("Length", "Host Length"):
                    return parameter
        except Exception:
            return None
        return None

    def _component_parameter(self, component):
        from version_adapter import builtin_parameter
        built_in = builtin_parameter("LEGEND_COMPONENT")
        if built_in is None:
            return None
        return component.get_Parameter(built_in)

    def _view_parameter(self, component):
        from version_adapter import builtin_parameter
        built_in = builtin_parameter("LEGEND_COMPONENT_VIEW")
        if built_in is None:
            return None
        return component.get_Parameter(built_in)

    def _assert_safe_target(self, element):
        from version_adapter import category_id_value, element_id_value, get_db
        DB = get_db()
        category = getattr(element, "Category", None)
        if category is None:
            return
        forbidden = (
            DB.BuiltInCategory.OST_Walls,
            DB.BuiltInCategory.OST_Doors,
            DB.BuiltInCategory.OST_Windows,
            DB.BuiltInCategory.OST_Floors,
            DB.BuiltInCategory.OST_Ceilings,
        )
        current = element_id_value(category.Id)
        for built_in in forbidden:
            if current == category_id_value(built_in):
                raise LegendOperationError(
                    "Refusing to modify element {0} because it is model category {1}.".format(
                        element.Id, category.Name
                    )
                )

    def _assert_text_type(self, text_type_id):
        text_type = self.doc.GetElement(text_type_id)
        if text_type is None:
            raise LegendOperationError(
                "The text note type could not be found. Check styles.text_note_type in the settings file."
            )

    def _create_plane(self, db_module, bbox, axis, offset):
        if axis == "x":
            x_pos = bbox.Min.X + offset
            bubble = db_module.XYZ(x_pos, bbox.Min.Y, 0)
            free = db_module.XYZ(x_pos, bbox.Max.Y, 0)
            cut = db_module.XYZ.BasisZ
        else:
            y_pos = bbox.Min.Y + offset
            bubble = db_module.XYZ(bbox.Min.X, y_pos, 0)
            free = db_module.XYZ(bbox.Max.X, y_pos, 0)
            cut = db_module.XYZ.BasisZ
        try:
            return db_module.ReferencePlane.Create(self.doc, bubble, free, cut, self.legend_view)
        except Exception as ex:
            raise UnsupportedRevitOperationError(
                "Revit could not create a layer reference plane in the legend. "
                "Layer dimensions were rolled back. The legend component was kept. {0}".format(ex)
            )

    def _create_dimension(self, db_module, bbox, axis, planes, structure_width):
        if len(planes) < 2:
            return None
        references = db_module.ReferenceArray()
        for plane in planes:
            try:
                references.Append(plane.GetReference())
            except Exception as ex:
                raise UnsupportedRevitOperationError(
                    "A layer reference plane did not provide a dimension reference. {0}".format(ex)
                )
        if axis == "x":
            y_pos = bbox.Min.Y - mm_to_internal(5)
            start = db_module.XYZ(bbox.Min.X, y_pos, 0)
            end = db_module.XYZ(bbox.Min.X + structure_width, y_pos, 0)
        else:
            x_pos = bbox.Min.X - mm_to_internal(5)
            start = db_module.XYZ(x_pos, bbox.Min.Y, 0)
            end = db_module.XYZ(x_pos, bbox.Min.Y + structure_width, 0)
        line = db_module.Line.CreateBound(start, end)
        try:
            return self.doc.Create.NewDimension(self.legend_view, line, references)
        except Exception as ex:
            raise UnsupportedRevitOperationError(
                "Revit could not create layer dimensions in the legend. {0}".format(ex)
            )


def find_template_legend(doc, template_name):
    """Find the real legend view used as the duplication source."""
    from version_adapter import get_db
    DB = get_db()
    matches = []
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            if view.IsTemplate or view.ViewType != DB.ViewType.Legend:
                continue
            if view.Name == template_name:
                matches.append(view)
        except Exception:
            continue
    if not matches:
        raise LegendOperationError(
            "Template legend '{0}' was not found. Create a normal legend view with that exact name "
            "and place one seed legend component in it. Do not use a Revit view template.".format(template_name)
        )
    if len(matches) > 1:
        raise LegendOperationError(
            "More than one legend is named '{0}'. Rename the extras so the template name is unique.".format(
                template_name
            )
        )
    return matches[0]


def duplicate_template(doc, template_view):
    """Duplicate a legend. WithDetailing is preferred so the seed component is copied."""
    from version_adapter import get_db
    DB = get_db()
    errors = []
    for option_name in ("WithDetailing", "Duplicate"):
        option = getattr(DB.ViewDuplicateOption, option_name, None)
        if option is None:
            continue
        try:
            new_id = template_view.Duplicate(option)
            view = doc.GetElement(new_id)
            if view is None:
                errors.append("{0} returned an id that does not resolve.".format(option_name))
                continue
            return view, option_name
        except Exception as ex:
            errors.append("{0}: {1}".format(option_name, ex))
    raise UnsupportedRevitOperationError(
        "Revit could not duplicate template legend '{0}'. {1}".format(
            template_view.Name, " | ".join(errors)
        )
    )


def unique_view_name(doc, base_name):
    """Return a view name that does not already exist."""
    from version_adapter import get_db
    DB = get_db()
    existing = set()
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            existing.add(view.Name)
        except Exception:
            continue
    if base_name not in existing:
        return base_name
    index = 2
    while "{0} ({1})".format(base_name, index) in existing:
        index += 1
    return "{0} ({1})".format(base_name, index)


def find_text_type(doc, type_name):
    """Resolve a text note type by the exact name in the settings file."""
    from version_adapter import get_db
    DB = get_db()
    found = []
    for text_type in DB.FilteredElementCollector(doc).OfClass(DB.TextNoteType):
        try:
            found.append(text_type)
            if text_type.Name == type_name:
                return text_type
        except Exception:
            continue
    available = ", ".join(sorted(item.Name for item in found)[:20]) or "(none)"
    raise LegendOperationError(
        "Text note type '{0}' was not found. Create it in the project or change the settings file. "
        "Available types include: {1}.".format(type_name, available)
    )


def _line_style(doc, style_name):
    from version_adapter import get_db
    DB = get_db()
    try:
        category = DB.Category.GetCategory(doc, DB.BuiltInCategory.OST_Lines)
        for sub_category in category.SubCategories:
            if sub_category.Name == style_name:
                return sub_category.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
    except Exception:
        return None
    return None


def _element_name(element):
    try:
        return element.Name
    except Exception:
        return str(element.Id)
