# -*- coding: utf-8 -*-
"""Actionable exceptions raised by the legend tool."""


class LegendToolError(Exception):
    """Base class for failures the user can act on."""


class ConfigurationError(LegendToolError):
    """The JSON settings are missing, unreadable, or invalid."""


class ValidationError(LegendToolError):
    """The active view or document cannot be used for this command."""


class LegendOperationError(LegendToolError):
    """A legend create or update step failed and was undone."""


class UnsupportedRevitOperationError(LegendToolError):
    """This Revit build refused an operation the tool does not fake."""
