# -*- coding: utf-8 -*-
"""Resolve parameter values without depending on translated UI names.

Order:
1. Built-in parameter from the alias table.
2. Shared parameter GUID.
3. Exact project parameter name.
4. Configured default.
A required parameter that is still missing produces a warning.
"""

from units import format_millimetres


class ResolvedValue(object):
    """One resolved parameter, including where the value came from."""

    def __init__(self, key, raw_value, display_value, source, warning=None, notice=None):
        self.key = key
        self.raw_value = raw_value
        self.display_value = display_value
        self.source = source
        self.warning = warning
        self.notice = notice

    @property
    def missing(self):
        return self.source == "missing" or _is_blank(self.raw_value)


class LookupReader(object):
    """In-memory parameter reader used by tests and preview data."""

    def __init__(self, builtins=None, guids=None, names=None, computed=None):
        self.builtins = builtins or {}
        self.guids = {str(key).lower(): value for key, value in (guids or {}).items()}
        self.names = names or {}
        self.computed = computed or {}

    def read_builtin(self, builtin_name):
        return self.builtins.get(builtin_name)

    def read_guid(self, guid):
        if not guid:
            return None
        return self.guids.get(str(guid).lower())

    def read_name(self, name):
        return self.names.get(name)

    def read_computed(self, key):
        return self.computed.get(key)

    def builtin_available(self, builtin_name):
        return True


class ParameterResolver(object):
    """Resolve configured parameter keys through a reader."""

    def __init__(self, aliases, type_rules=None):
        self.aliases = aliases or {}
        self.type_rules = type_rules or {}

    def resolve(self, key, reader, required=False, default=None, value_format=None, decimals=0):
        """Resolve one key. ``default`` wins over the alias default when provided."""
        spec = self._spec_for(key)
        if default is None and "default" in spec:
            default = spec.get("default")
        raw_value = None
        source = None
        notice = None
        warning = None

        computed = reader.read_computed(key)
        if not _is_blank(computed):
            raw_value = computed
            source = "computed"
        else:
            builtin_name = spec.get("builtin")
            if builtin_name:
                if reader.builtin_available(builtin_name):
                    candidate = reader.read_builtin(builtin_name)
                    if not _is_blank(candidate):
                        raw_value = candidate
                        source = "builtin:" + builtin_name
                else:
                    notice = (
                        "Built-in parameter '{0}' is not available in this Revit version. "
                        "The tool continued with the GUID and name fallbacks.".format(builtin_name)
                    )
            if _is_blank(raw_value) and spec.get("guid"):
                candidate = reader.read_guid(spec.get("guid"))
                if not _is_blank(candidate):
                    raw_value = candidate
                    source = "guid:" + spec.get("guid")
            if _is_blank(raw_value):
                for name in spec.get("names") or []:
                    candidate = reader.read_name(name)
                    if not _is_blank(candidate):
                        raw_value = candidate
                        source = "name:" + name
                        if not spec.get("builtin") and not spec.get("guid"):
                            notice = (
                                "Parameter '{0}' was found by its exact name '{1}'. Add a built-in "
                                "parameter or shared GUID to the alias file so it also works in "
                                "projects in another language.".format(key, name)
                            )
                        break

        unmapped = bool(spec.get("unmapped"))
        if _is_blank(raw_value):
            if not _is_blank(default):
                raw_value = default
                source = "default"
                if required:
                    warning = (
                        "Required parameter '{0}' was not found. The default from the settings was used.".format(key)
                    )
            else:
                source = "missing"
                raw_value = None
                if required or unmapped and self._unmapped_is_error():
                    warning = self._missing_message(key, required, unmapped)
                elif unmapped:
                    warning = self._missing_message(key, required, unmapped)
        elif unmapped and source and source.startswith("name:"):
            notice = (
                "Parameter '{0}' is not in the alias file but was found by its exact name. Add a "
                "built-in parameter or GUID so it also works in other languages.".format(key)
            )

        display = self._display(raw_value, value_format, decimals)
        if source == "missing":
            display = self.type_rules.get("blank_label", "-")
        return ResolvedValue(key, raw_value, display, source, warning=warning, notice=notice)

    def _spec_for(self, key):
        spec = self.aliases.get(key)
        if spec:
            copied = {
                "builtin": spec.get("builtin"),
                "guid": spec.get("guid"),
                "names": list(spec.get("names") or []),
                "default": spec.get("default"),
                "unmapped": False,
            }
            return copied
        return {"builtin": None, "guid": None, "names": [key], "default": None, "unmapped": True}

    def _unmapped_is_error(self):
        return self.type_rules.get("unmapped_parameter") == "error"

    def _missing_message(self, key, required, unmapped):
        if unmapped and self._unmapped_is_error():
            return (
                "Parameter '{0}' is not mapped in the alias file and has no value. "
                "unmapped_parameter is set to error, so the legend was not changed.".format(key)
            )
        if unmapped:
            return (
                "Parameter '{0}' is not mapped in the alias file and was left blank.".format(key)
            )
        if required:
            return (
                "Required parameter '{0}' was not found by built-in parameter, GUID, name or "
                "default.".format(key)
            )
        return None

    def _display(self, raw_value, value_format, decimals):
        if _is_blank(raw_value):
            return self.type_rules.get("blank_label", "-")
        if value_format == "millimetres":
            if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
                return format_millimetres(raw_value, decimals)
            return str(raw_value)
        return str(raw_value)


def format_layers(layers, decimals=1):
    """Format compound-structure layers as material and thickness text."""
    parts = []
    for layer in layers or []:
        material = layer.get("material") or "No material"
        width = layer.get("width_feet")
        if isinstance(width, (int, float)) and not isinstance(width, bool):
            thickness = format_millimetres(width, decimals)
        else:
            thickness = "?"
        parts.append("{0} {1} mm".format(material, thickness))
    return " / ".join(parts)


def _is_blank(value):
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


class RevitParameterReader(object):
    """Read parameters from one Revit element. Create it inside a Revit command."""

    def __init__(self, element, computed=None):
        self.element = element
        self.computed = computed or {}
        self._unavailable = set()

    def read_computed(self, key):
        return self.computed.get(key)

    def builtin_available(self, builtin_name):
        from version_adapter import builtin_parameter
        available = builtin_parameter(builtin_name) is not None
        if not available:
            self._unavailable.add(builtin_name)
        return available

    def read_builtin(self, builtin_name):
        from version_adapter import builtin_parameter
        built_in = builtin_parameter(builtin_name)
        if built_in is None:
            return None
        parameter = self.element.get_Parameter(built_in)
        value = _read_storage(parameter)
        if _is_blank(value):
            value = _read_known_property(self.element, builtin_name)
        return value

    def read_guid(self, guid):
        if not guid:
            return None
        try:
            from System import Guid
            parameter = self.element.get_Parameter(Guid(str(guid)))
        except Exception:
            return None
        return _read_storage(parameter)

    def read_name(self, name):
        if not name:
            return None
        try:
            for parameter in self.element.Parameters:
                definition = parameter.Definition
                if definition is not None and definition.Name == name:
                    return _read_storage(parameter)
        except Exception:
            return None
        return None


def _read_known_property(element, builtin_name):
    """Use API properties when the matching built-in parameter is empty."""
    try:
        if builtin_name in ("SYMBOL_NAME_PARAM", "ALL_MODEL_TYPE_NAME"):
            return element.Name
        if builtin_name in ("SYMBOL_FAMILY_NAME_PARAM", "ALL_MODEL_FAMILY_NAME"):
            return getattr(element, "FamilyName", None)
    except Exception:
        return None
    return None


def _read_storage(parameter):
    if parameter is None:
        return None
    try:
        if not parameter.HasValue:
            return None
    except Exception:
        return None
    from version_adapter import get_db
    DB = get_db()
    storage = parameter.StorageType
    try:
        if storage == DB.StorageType.Double:
            return parameter.AsDouble()
        if storage == DB.StorageType.Integer:
            text = parameter.AsValueString()
            if text:
                return text
            return parameter.AsInteger()
        if storage == DB.StorageType.String:
            text = parameter.AsString()
            if text is None:
                return parameter.AsValueString()
            return text
        if storage == DB.StorageType.ElementId:
            return parameter.AsValueString()
    except Exception:
        return None
    return None
