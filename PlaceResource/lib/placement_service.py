# -*- coding: utf-8 -*-
"""Place an existing generated legend on a sheet.

A legend may appear on more than one sheet. This service refuses a second
viewport on the same sheet and does not move a viewport that is already there.
"""

from errors import LegendOperationError
from transactions import TransactionContext
from units import mm_to_internal
from version_adapter import element_id_value, get_db


def sheets_containing_view(doc, view):
    """Return sheets that already show the given view."""
    DB = get_db()
    target = element_id_value(view.Id)
    sheets = []
    seen = set()
    for viewport in DB.FilteredElementCollector(doc).OfClass(DB.Viewport):
        try:
            if element_id_value(viewport.ViewId) != target:
                continue
            sheet = doc.GetElement(viewport.OwnerViewId)
        except Exception:
            continue
        if sheet is None:
            continue
        identity = element_id_value(sheet.Id)
        if identity in seen:
            continue
        seen.add(identity)
        sheets.append(sheet)
    return sheets


def model_viewports_on_sheet(doc, sheet, definitions):
    """Return (viewport, view) pairs whose view type is supported by a definition."""
    DB = get_db()
    allowed = set()
    for definition in definitions:
        allowed.update(definition.get("source_view_types") or [])
    pairs = []
    for viewport in DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.Viewport):
        view = doc.GetElement(viewport.ViewId)
        if view is None:
            continue
        try:
            token = view.ViewType.ToString()
        except Exception:
            continue
        if token in allowed:
            pairs.append((viewport, view))
    return pairs


def all_sheets(doc):
    """Return drawing sheets in sheet-number order."""
    DB = get_db()
    sheets = []
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            if view.ViewType == DB.ViewType.DrawingSheet and not view.IsTemplate:
                sheets.append(view)
        except Exception:
            continue
    sheets.sort(key=lambda sheet: (getattr(sheet, "SheetNumber", ""), sheet.Name))
    return sheets


def sheet_label(sheet):
    """Return a sheet number and name for dialogs."""
    number = getattr(sheet, "SheetNumber", "") or ""
    name = sheet.Name or ""
    if number and name:
        return "{0} - {1}".format(number, name)
    return name or number or str(sheet.Id)


def legend_viewport_on_sheet(doc, sheet, legend_view):
    """Return the viewport when this legend is already on the sheet."""
    DB = get_db()
    target = element_id_value(legend_view.Id)
    sheet_id = element_id_value(sheet.Id)
    for viewport in DB.FilteredElementCollector(doc, sheet.Id).OfClass(DB.Viewport):
        try:
            if element_id_value(viewport.ViewId) != target:
                continue
            if element_id_value(viewport.OwnerViewId) == sheet_id:
                return viewport
        except Exception:
            continue
    return None


def configured_anchor(definition):
    """Return a sheet point from settings, or None when the user should pick."""
    placement = definition.get("sheet_placement") or {}
    if placement.get("mode") != "configured_point":
        return None
    DB = get_db()
    return DB.XYZ(
        mm_to_internal(placement.get("anchor_x_mm", 0)),
        mm_to_internal(placement.get("anchor_y_mm", 0)),
        0,
    )


def interactive_place(doc, uidoc, source_view, legend_view, definition, active_sheet=None):
    """Choose a sheet and point, then place the legend.

    Returns (viewport, warnings). Returns (None, []) when the user cancels.
    """
    from ui_service import choose_named_item, pick_sheet_point
    if active_sheet is not None:
        sheet = active_sheet
    else:
        sheets = sheets_containing_view(doc, source_view)
        title = "Pick the sheet for the legend"
        if not sheets:
            sheets = all_sheets(doc)
            title = "The view is not on a sheet yet. Pick a sheet for the legend."
        if not sheets:
            raise LegendOperationError("This model has no sheets.")
        sheet = choose_named_item(title, sheets, sheet_label)
        if sheet is None:
            return None, []
    prevent = bool((definition.get("sheet_placement") or {}).get("prevent_duplicate_on_same_sheet", True))
    if prevent and legend_viewport_on_sheet(doc, sheet, legend_view) is not None:
        raise LegendOperationError(
            "Legend '{0}' is already on sheet '{1}'. It was left where it is.".format(
                legend_view.Name, sheet_label(sheet)
            )
        )
    point = configured_anchor(definition)
    if point is None:
        point = _pick_on_sheet(uidoc, sheet)
        if point is None:
            return None, []
    return place_on_sheet(doc, sheet, legend_view, point, prevent_duplicate=prevent)


def _pick_on_sheet(uidoc, sheet):
    from ui_service import pick_sheet_point
    return _with_sheet_open(uidoc, sheet, pick_sheet_point)


def box_top_left_and_width(min_x, min_y, max_x, max_y):
    """Top-left corner and width of a box drawn in any direction. Returns (x, y, width)."""
    return min(min_x, max_x), max(min_y, max_y), abs(max_x - min_x)


def pick_sheet_box(uidoc, sheet):
    """Let the user draw a box on the sheet. Returns (top-left XYZ, width in feet), or None when cancelled."""
    from ui_service import pick_box

    picked = _with_sheet_open(uidoc, sheet, pick_box)
    if picked is None:
        return None
    DB = get_db()
    x, y, width = box_top_left_and_width(picked.Min.X, picked.Min.Y, picked.Max.X, picked.Max.Y)
    return DB.XYZ(x, y, 0), width


def table_corner_on_sheet(doc, viewport):
    """Where the legend table's top-left corner (view point 0,0) is on the sheet.

    Uses Revit's view-to-sheet transforms, so the margin Revit keeps around the
    viewport contents does not matter. Falls back to the top-left of the viewport
    outline when the transforms are not available. Returns an XYZ.
    """
    DB = get_db()
    point = view_point_on_sheet(doc, viewport, 0.0, 0.0)
    if point is not None:
        return point
    outline = viewport.GetBoxOutline()
    return DB.XYZ(outline.MinimumPoint.X, outline.MaximumPoint.Y, 0)


def view_point_on_sheet(doc, viewport, x, y):
    """Sheet position of the view point (x, y), or None when Revit cannot tell (older API)."""
    DB = get_db()
    try:
        view = doc.GetElement(viewport.ViewId)
        to_sheet = viewport.GetProjectionToSheetTransform()
        to_projection = view.GetModelToProjectionTransforms()[0].GetModelToProjectionTransform()
        return to_sheet.OfPoint(to_projection.OfPoint(DB.XYZ(x, y, 0)))
    except Exception:
        return None


def placed_width_check(doc, viewport, width_view, width_mm):
    """Warnings when the table's width on the sheet differs from the asked width by more than 1 mm."""
    from units import internal_to_mm
    # Called after a committed transaction, so the document is already regenerated.
    left = view_point_on_sheet(doc, viewport, 0.0, 0.0)
    right = view_point_on_sheet(doc, viewport, width_view, 0.0)
    if left is None or right is None:
        return []
    placed = internal_to_mm(abs(right.X - left.X))
    if abs(placed - width_mm) <= 1.0:
        return []
    return ["The legend is {0:.0f} mm wide on the sheet but {1:.0f} mm was asked for. Check the legend "
            "view scale.".format(placed, width_mm)]


def move_table_corner_to(doc, viewport, point):
    """Move the viewport so the table's top-left corner sits on ``point``. Needs an open transaction."""
    DB = get_db()
    doc.Regenerate()
    current = table_corner_on_sheet(doc, viewport)
    dx = point.X - current.X
    dy = point.Y - current.Y
    if abs(dx) > 1e-9 or abs(dy) > 1e-9:
        centre = viewport.GetBoxCenter()
        viewport.SetBoxCenter(DB.XYZ(centre.X + dx, centre.Y + dy, centre.Z))


def align_top_left(doc, viewport, point):
    """Put the legend table's top-left corner on ``point`` (the corner of the drawn box). Opens its own transaction."""
    with TransactionContext(doc, "Line up legend with the box") as transaction:
        move_table_corner_to(doc, viewport, point)
    return list(transaction.warnings)


def set_viewport_type(doc, viewport, type_name):
    """Give the viewport the viewport type named ``type_name`` (e.g. No Title). Opens its own transaction.

    Returns a list of warnings. Nothing changes when the type is not in the model.
    """
    if not type_name:
        return []
    wanted = type_name.strip().lower()
    match = None
    try:
        for type_id in viewport.GetValidTypes():
            element = doc.GetElement(type_id)
            name = getattr(element, "Name", "") if element is not None else ""
            if (name or "").strip().lower() == wanted:
                match = type_id
                break
    except Exception:
        match = None
    if match is None:
        return [
            "Viewport type '{0}' is not in this model, so the legend title shows. Load or make that "
            "viewport type, or change viewport_type_name in library_legends.json.".format(type_name)
        ]
    if element_id_value(viewport.GetTypeId()) == element_id_value(match):
        return []
    with TransactionContext(doc, "Legend viewport type") as transaction:
        viewport.ChangeTypeId(match)
    return list(transaction.warnings)


def _with_sheet_open(uidoc, sheet, action):
    """Run ``action(uidoc)`` with the sheet as the active view, then switch back."""
    previous = uidoc.ActiveView
    switched = element_id_value(previous.Id) != element_id_value(sheet.Id)
    if switched:
        try:
            uidoc.ActiveView = sheet
        except Exception as ex:
            raise LegendOperationError(
                "Could not open sheet '{0}'. Open it first and run the command again. {1}".format(
                    sheet_label(sheet), ex
                )
            )
    try:
        return action(uidoc)
    finally:
        if switched:
            try:
                uidoc.ActiveView = previous
            except Exception:
                pass


def place_on_sheet(doc, sheet, legend_view, point, prevent_duplicate=True):
    """Create a viewport for the legend. Raises instead of moving an existing one."""
    DB = get_db()
    if prevent_duplicate:
        existing = legend_viewport_on_sheet(doc, sheet, legend_view)
        if existing is not None:
            raise LegendOperationError(
                "Legend '{0}' is already on sheet '{1}'. It was left where it is.".format(
                    legend_view.Name, sheet_label(sheet)
                )
            )
    try:
        allowed = DB.Viewport.CanAddViewToSheet(doc, sheet.Id, legend_view.Id)
    except Exception as ex:
        raise LegendOperationError(
            "Revit could not check whether '{0}' can be placed on '{1}'. {2}".format(
                legend_view.Name, sheet_label(sheet), ex
            )
        )
    if not allowed:
        raise LegendOperationError(
            "Revit will not put '{0}' on sheet '{1}'.".format(legend_view.Name, sheet_label(sheet))
        )
    with TransactionContext(doc, "Place legend on sheet") as transaction:
        try:
            viewport = DB.Viewport.Create(doc, sheet.Id, legend_view.Id, point)
        except Exception as ex:
            raise LegendOperationError(
                "Revit did not place legend '{0}' on sheet '{1}'. {2}".format(
                    legend_view.Name, sheet_label(sheet), ex
                )
            )
    return viewport, list(transaction.warnings)
