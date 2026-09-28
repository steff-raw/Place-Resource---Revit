#! python3
# -*- coding: utf-8 -*-
"""Report differences between generated legends and their source views.

Requires the pyRevit CPython 3 engine. IronPython is not supported.
This command does not start a transaction.
"""

__title__ = "Audit Generated\nLegends"
__doc__ = "Report missing, extra, and overlapping legend entries without changing the model."
__author__ = "Place Resource"

import os
import sys


def _find_lib():
    """Put the Place Resource lib folder on sys.path.

    A folder qualifies when it holds lib/legend_service.py. Keep config/ next to lib/. Checked in order:
    1. The PLACE_RESOURCE_HOME environment variable.
    2. The extension root, three levels above this script (repository layout).
    3. Documents/Gensler/Python/PlaceResource under OneDrive, then the user profile.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.environ.get("PLACE_RESOURCE_HOME"), os.path.join(here, "..", "..", "..")]
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

from pyrevit import revit

from audit_service import audit_legends
from configuration import load_settings
from errors import LegendToolError
from logging_service import get_logger
from reporting import alert_error, print_audit
from validation import assert_project_document

LOGGER = get_logger("audit_generated_legends")


def main():
    """Print a read-only audit of every tool-managed legend."""
    doc = revit.doc
    assert_project_document(doc)
    settings = load_settings()
    print_audit(audit_legends(doc, settings))


if __name__ == "__main__":
    try:
        main()
    except LegendToolError as error:
        LOGGER.error("%s", error)
        alert_error("Audit Generated Legends", str(error))
    except Exception as error:
        LOGGER.exception("Audit Generated Legends failed")
        alert_error("Audit Generated Legends", "Unexpected failure: {0}".format(error))
