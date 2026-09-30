# -*- coding: utf-8 -*-
"""Step log for finding where Revit crashes.

Each step is written to PlaceResource/logs/last_run.txt and flushed to disk
before the next Revit call, so after a crash the last line shows the call that
was running. The file is replaced at the start of every command. Local file
only. Writing it never stops the tool.
"""

import datetime
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(_ROOT, "logs", "last_run.txt")


def start(command):
    """Start a new log for one command."""
    try:
        folder = os.path.dirname(PATH)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(PATH, "w", encoding="utf-8") as handle:
            handle.write("{0}  {1}\n".format(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), command))
    except Exception:
        pass


def step(text):
    """Record the next step and force it to disk."""
    try:
        with open(PATH, "a", encoding="utf-8") as handle:
            handle.write("{0}  {1}\n".format(datetime.datetime.now().strftime("%H:%M:%S"), text))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        pass
