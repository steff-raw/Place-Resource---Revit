# -*- coding: utf-8 -*-
"""Logging that works inside pyRevit and in local unit tests."""

import logging


def get_logger(name="view_legend_creator"):
    """Return the pyRevit logger, or a standard logger outside Revit."""
    try:
        from pyrevit import script
        logger = script.get_logger()
        if logger:
            return logger
    except Exception:
        pass
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
