#! python3
# -*- coding: utf-8 -*-
"""Validate or retarget the JSON settings file.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
"""

__title__ = "Legend\nSettings"
__doc__ = (
    "Choose the legend text style, validate the settings file, "
    "or choose a project-specific JSON file."
)
__author__ = "Place Resource"

import os
import sys


def _find_lib():
    """Put the Place Resource lib folder on sys.path.

    A folder qualifies when it holds lib/legend_service.py. Keep config/ next to lib/. Checked in order:
    1. The PLACE_RESOURCE_HOME environment variable.
    2. PlaceResource next to Legends.panel (repository layout).
    3. Documents/Gensler/Python/PlaceResource under OneDrive, then the user profile.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.environ.get("PLACE_RESOURCE_HOME"), os.path.join(here, "..", "..", "PlaceResource")]
    for root in (os.environ.get("OneDriveCommercial"), os.environ.get("OneDrive"), os.path.expanduser("~")):
        if root:
            candidates.append(os.path.join(root, "Documents", "Gensler", "Python", "PlaceResource"))
    for folder in candidates:
        if not folder:
            continue
        lib = os.path.abspath(os.path.join(folder, "lib"))
        if os.path.isfile(os.path.join(lib, "legend_service.py")):
            if lib not in sys.path:
                sys.path.insert(0, lib)
            # Load the current lib code on every click. Edited files then work without
            # a pyRevit Reload, which breaks the CPython engine until Revit restarts.
            prefix = os.path.normcase(lib + os.sep)
            for name, module in list(sys.modules.items()):
                path = getattr(module, "__file__", None) or ""
                if path and os.path.normcase(os.path.abspath(path)).startswith(prefix):
                    del sys.modules[name]
            return lib
    raise ImportError(
        "PlaceResource folder not found. Copy lib and config to "
        "Documents\\Gensler\\Python\\PlaceResource, or set PLACE_RESOURCE_HOME. Looked in: " + "; ".join(os.path.abspath(item) for item in candidates if item)
    )


_find_lib()

from pyrevit import revit

from dialogs import alert
from configuration import (
    default_settings_path,
    load_settings,
    resolve_settings_path,
    set_settings_override,
)
from errors import LegendToolError
from logging_service import get_logger
from reporting import alert_error
from ui_service import choose_settings_action, choose_text_type, pick_settings_file

LOGGER = get_logger("legend_settings")


def main():
    """Validate the current file or point the tool at another JSON file."""
    action = choose_settings_action(revit.doc)
    if action == "Legend text style":
        name = choose_text_type(revit.doc)
        if name:
            alert("Legends in this model will use '{0}'.".format(name), title="Legend Settings")
    elif action == "Check the settings file":
        _validate(resolve_settings_path())
    elif action == "Use a different settings file":
        path = pick_settings_file()
        if not path:
            return
        load_settings(path)
        set_settings_override(path)
        alert("Settings will now come from:\n{0}".format(path), title="Legend Settings")
    elif action == "Use the default settings file":
        set_settings_override(None)
        _validate(default_settings_path())
    elif action == "Where is the settings file?":
        _open(resolve_settings_path())
    elif action:
        raise LegendToolError("Unknown setting '{0}'.".format(action))


def _validate(path):
    settings = load_settings(path)
    names = "\n".join(
        "- {0} ({1})".format(item["display_name"], item["category"])
        for item in settings["data"]["legend_definitions"]
    )
    message = "Settings file is OK.\n\nFile: {0}\nSchema: {1}\nAlias file: {2}\n\nDefinitions:\n{3}".format(
        settings["path"],
        settings["data"]["schema_version"],
        settings["alias_path"],
        names,
    )
    alert(message, title="Legend Settings")


def _open(path):
    # The tool never starts another program. Show the path so the user opens it themselves.
    alert("Settings file:\n{0}".format(path), title="Legend Settings")


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Legend Settings", str(error))
    except Exception as error:
        LOGGER.exception("Legend Settings failed")
        alert_error("Legend Settings", "Something went wrong: {0}".format(error))
