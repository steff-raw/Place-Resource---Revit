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

_LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "lib"))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

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
