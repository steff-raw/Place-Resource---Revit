# -*- coding: utf-8 -*-
"""Decide whether the active view is a valid legend source."""

from errors import ValidationError


def assert_project_document(doc):
    """Reject family documents and read-only models before any transaction."""
    if doc is None:
        raise ValidationError("There is no active document.")
    if getattr(doc, "IsFamilyDocument", False):
        raise ValidationError("Open a project document. Legend creation does not run in the family editor.")
    if getattr(doc, "IsReadOnly", False):
        raise ValidationError("The document is read-only. Open a writable model before creating a legend.")


def view_type_token(view):
    """Return the Revit view type name, such as FloorPlan or Section."""
    try:
        return view.ViewType.ToString()
    except Exception:
        return str(view.ViewType)


def assert_supported_source_view(view, definition):
    """Raise when the view cannot be the source for this legend definition."""
    if view is None:
        raise ValidationError("There is no active view. Open a plan, section, or elevation.")
    try:
        if view.IsTemplate:
            raise ValidationError("The active view is a view template. Open the model view itself.")
    except ValidationError:
        raise
    except Exception:
        pass
    token = view_type_token(view)
    if token == "DrawingSheet":
        raise ValidationError(
            "The active view is a sheet. Open a plan, section, or elevation, "
            "or run Place Legend on Sheet and pick a viewport."
        )
    if token == "Legend":
        raise ValidationError(
            "A legend cannot be the source view. Open the model view whose visible types should be listed."
        )
    allowed = list(definition.get("source_view_types") or [])
    if token not in allowed:
        raise ValidationError(
            "View '{0}' is a {1} view. '{2}' supports: {3}.".format(
                _view_name(view),
                token,
                definition.get("display_name") or definition.get("id"),
                ", ".join(allowed),
            )
        )
    return token


def definitions_for_view(settings, view):
    """Return legend definitions whose source_view_types include this view."""
    token = view_type_token(view)
    matched = []
    for definition in settings["data"]["legend_definitions"]:
        if token in definition.get("source_view_types", []):
            matched.append(definition)
    return matched


def _view_name(view):
    try:
        return view.Name
    except Exception:
        return "(unnamed view)"
