#! python3
# -*- coding: utf-8 -*-
"""Validate or retarget the JSON settings file.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Legend\nSettings"
__doc__ = "Validate the legend settings file or choose a project-specific JSON file."
__author__ = "Place Resource"

import os
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from pyrevit import forms

from configuration import (
    default_settings_path,
    load_settings,
    resolve_settings_path,
    set_settings_override,
)
from errors import LegendToolError
from logging_service import get_logger
from reporting import alert_error
from ui_service import choose_settings_action, pick_settings_file

LOGGER = get_logger("legend_settings")


def main():
    """Validate the current file or point the tool at another JSON file."""
    action = choose_settings_action()
    if action == "Validate configuration":
        _validate(resolve_settings_path())
    elif action == "Choose configuration file":
        path = pick_settings_file()
        if not path:
            return
        load_settings(path)
        set_settings_override(path)
        forms.alert("Legend settings will now be read from:\n{0}".format(path), title="Legend Settings")
    elif action == "Use the built-in configuration":
        set_settings_override(None)
        _validate(default_settings_path())
    elif action == "Open configuration file":
        _open(resolve_settings_path())
    elif action:
        raise LegendToolError("Unknown settings action '{0}'.".format(action))


def _validate(path):
    settings = load_settings(path)
    names = "\n".join(
        "- {0} ({1})".format(item["display_name"], item["category"])
        for item in settings["data"]["legend_definitions"]
    )
    message = "Settings are valid.\n\nFile: {0}\nSchema: {1}\nAlias file: {2}\n\nDefinitions:\n{3}".format(
        settings["path"],
        settings["data"]["schema_version"],
        settings["alias_path"],
        names,
    )
    forms.alert(message, title="Legend Settings")


def _open(path):
    if os.name == "nt":
        os.startfile(path)  # pylint: disable=no-member
        return
    forms.alert("Open this file in an editor:\n{0}".format(path), title="Legend Settings")


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Legend Settings", str(error))
    except Exception as error:
        LOGGER.exception("Legend Settings failed")
        alert_error("Legend Settings", "Unexpected failure: {0}".format(error))
