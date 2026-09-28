#! python3
# -*- coding: utf-8 -*-
"""Shift-click configuration for the Settings button.

pyRevit runs this file when the button is shift-clicked.
"""

import os
import sys

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from pyrevit import forms, script

from configuration import load_settings, set_settings_override
from errors import LegendToolError

config = script.get_config()


def main():
    """Store an optional settings path in the button config and the extension pointer."""
    path = forms.pick_file(file_ext="json", title="Select the legend settings file")
    if not path:
        return
    try:
        load_settings(path)
    except LegendToolError as error:
        forms.alert(str(error), title="Legend Settings")
        return
    set_settings_override(path)
    config.settings_path = path
    script.save_config()
    forms.alert("Saved legend settings path:\n{0}".format(path), title="Legend Settings")


if __name__ == "__main__":
    main()
