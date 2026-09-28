#! python3
# -*- coding: utf-8 -*-
"""Shift-click configuration for the Settings button.

pyRevit runs this file when the button is shift-clicked.
"""

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
            return lib
    raise ImportError(
        "Place Resource lib folder was not found. Copy 'lib' and 'config' to "
        "Documents\\Gensler\\Python\\PlaceResource, or set PLACE_RESOURCE_HOME to the folder that "
        "contains them. Checked: " + "; ".join(os.path.abspath(item) for item in candidates if item)
    )


_find_lib()

from configuration import load_settings, set_settings_override
from dialogs import alert, pick_file
from errors import LegendToolError


def main():
    """Pick a settings JSON file and store it in config/user_settings_path.txt."""
    path = pick_file("Select the legend settings file")
    if not path:
        return
    try:
        load_settings(path)
    except LegendToolError as error:
        alert(str(error), title="Legend Settings")
        return
    set_settings_override(path)
    alert("Saved legend settings path:\n{0}".format(path), title="Legend Settings")


if __name__ == "__main__":
    main()
