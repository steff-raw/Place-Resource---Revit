# -*- coding: utf-8 -*-
"""Category filters. Wall rules are explicit. Other categories share one adapter.

The pure inclusion functions are safe to unit test. Revit calls stay inside methods.
"""


def wall_is_included(kind, is_in_place, is_linked, is_demolished, is_stacked_member,
                     parts_replace_original, include):
    """Return (included, reason_code) for one wall instance."""
    include = include or {}
    if is_demolished and not include.get("demolished", False):
        return False, "demolished"
    if parts_replace_original and not include.get("when_parts_replace_original", False):
        return False, "parts_replace_original"
    if is_stacked_member and not include.get("stacked_wall_members", False):
        return False, "stacked_member"
    if is_in_place and not include.get("in_place_walls", False):
        return False, "in_place"
    if is_linked and not include.get("linked_models", False):
        return False, "linked_model"
    if kind == "curtain" and not include.get("curtain_walls", False):
        return False, "curtain_wall"
    if kind == "stacked" and not include.get("stacked_walls", False):
        return False, "stacked_wall"
    if kind == "basic" and not include.get("basic_walls", True):
        return False, "basic_wall"
    return True, None


def generic_is_included(is_in_place, is_linked, is_demolished, include):
    """Return (included, reason_code) for a non-wall category."""
    include = include or {}
    if is_demolished and not include.get("demolished", False):
        return False, "demolished"
    if is_in_place and not include.get("in_place", False):
        return False, "in_place"
    if is_linked and not include.get("linked_models", False):
        return False, "linked_model"
    return True, None


class WallAdapter(object):
    """Collect wall instances and describe their types."""

    category_name = "OST_Walls"

    def built_in_category(self):
        from version_adapter import get_db
        return get_db().BuiltInCategory.OST_Walls

    def include_instance(self, facts, include):
        return wall_is_included(
            facts.get("kind"),
            facts.get("is_in_place"),
            facts.get("is_linked"),
            facts.get("is_demolished"),
            facts.get("is_stacked_member"),
            facts.get("parts_replace_original"),
            include,
        )

    def describe_instance(self, doc, view, element):
        """Return a fact dictionary for a host-document wall."""
        from version_adapter import element_id_value, get_db
        DB = get_db()
        owner_doc = getattr(element, "Document", None) or doc
        wall_type = owner_doc.GetElement(element.GetTypeId())
        kind = _wall_kind(wall_type)
        return {
            "element": element,
            "type_element": wall_type,
            "kind": kind,
            "is_in_place": _is_in_place(wall_type),
            "is_linked": False,
            "link_name": None,
            "is_demolished": _is_demolished(element),
            "is_stacked_member": _is_stacked_member(element),
            "parts_replace_original": _parts_replace_original(doc, view, element),
            "type_id": element_id_value(element.GetTypeId()),
            "db": DB,
        }


class GenericCategoryAdapter(object):
    """Collect types for categories that do not need wall-kind rules.

    The legend seed in the template must already be a component of this category.
    This path is implemented so the tool can be configured for doors, windows,
    floors, ceilings, furniture, and generic models. It has not been tested in Revit.
    """

    def __init__(self, category_name):
        self.category_name = category_name

    def built_in_category(self):
        from version_adapter import get_db
        DB = get_db()
        category = getattr(DB.BuiltInCategory, self.category_name, None)
        if category is None:
            from errors import ConfigurationError
            raise ConfigurationError(
                "Revit does not have a built-in category named {0}.".format(self.category_name)
            )
        return category

    def include_instance(self, facts, include):
        return generic_is_included(
            facts.get("is_in_place"),
            facts.get("is_linked"),
            facts.get("is_demolished"),
            include,
        )

    def describe_instance(self, doc, view, element):
        from version_adapter import element_id_value
        owner_doc = getattr(element, "Document", None) or doc
        type_element = owner_doc.GetElement(element.GetTypeId())
        return {
            "element": element,
            "type_element": type_element,
            "kind": "generic",
            "is_in_place": _is_in_place(type_element) or _instance_family_is_in_place(element),
            "is_linked": False,
            "link_name": None,
            "is_demolished": _is_demolished(element),
            "is_stacked_member": False,
            "parts_replace_original": False,
            "type_id": element_id_value(element.GetTypeId()),
        }


_GENERIC_CATEGORIES = (
    "OST_Doors",
    "OST_Windows",
    "OST_Floors",
    "OST_Ceilings",
    "OST_Furniture",
    "OST_GenericModel",
    "OST_Columns",
    "OST_StructuralColumns",
    "OST_Roofs",
    "OST_Stairs",
    "OST_Casework",
    "OST_SpecialityEquipment",
)


def get_adapter(category_name):
    """Return the adapter for a configured category name."""
    if category_name == "OST_Walls":
        return WallAdapter()
    if category_name in _GENERIC_CATEGORIES:
        return GenericCategoryAdapter(category_name)
    from errors import ConfigurationError
    raise ConfigurationError(
        "Category {0} does not have an adapter. Walls are the tested target. "
        "Doors, windows, floors, ceilings, furniture, and generic models use the generic adapter "
        "when you add a legend definition and a matching template seed.".format(category_name)
    )


def _wall_kind(wall_type):
    if wall_type is None:
        return "unknown"
    try:
        from version_adapter import get_db
        DB = get_db()
        kind = wall_type.Kind
        if kind == DB.WallKind.Curtain:
            return "curtain"
        if kind == DB.WallKind.Stacked:
            return "stacked"
        if kind == DB.WallKind.Basic:
            return "basic"
    except Exception:
        return "unknown"
    return "unknown"


def _is_in_place(type_element):
    if type_element is None:
        return False
    try:
        family = type_element.Family
        if family is not None and getattr(family, "IsInPlace", False):
            return True
    except Exception:
        pass
    try:
        family_name = type_element.FamilyName or ""
    except Exception:
        family_name = ""
    lowered = family_name.lower()
    return "in-place" in lowered or "in place" in lowered


def _instance_family_is_in_place(element):
    try:
        symbol = element.Symbol
        family = symbol.Family if symbol is not None else None
        return bool(family is not None and family.IsInPlace)
    except Exception:
        return False


def _is_demolished(element):
    from version_adapter import element_id_value
    try:
        demolished = element.DemolishedPhaseId
    except Exception:
        return False
    return element_id_value(demolished) > 0


def _is_stacked_member(element):
    from version_adapter import element_id_value
    try:
        owner = element.StackedWallOwnerId
    except Exception:
        return False
    return element_id_value(owner) > 0


def _parts_replace_original(doc, view, element):
    from version_adapter import get_db
    DB = get_db()
    try:
        if not DB.PartUtils.HasAssociatedParts(doc, element.Id):
            return False
        visibility = view.PartsVisibility
        return visibility == DB.PartsVisibility.ShowPartsOnly
    except Exception:
        return False
