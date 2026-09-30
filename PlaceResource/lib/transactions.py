# -*- coding: utf-8 -*-
"""Transaction helpers.

Transactions are not left open after an exception. Warning messages are
recorded and returned to the report. They are not suppressed.

No Python class is handed to Revit as a callback (for example an
IFailuresPreprocessor). Under the pyRevit CPython engine, Revit calling back
into Python can fail with "PythonEngine is not initialized" and abort the
command. New warnings are read with Document.GetWarnings() instead: the
warnings present before the transaction are compared with those after commit.
"""

from logging_service import get_logger

LOGGER = get_logger("transactions")


def warning_keys(doc):
    """Return (description, failing element ids) for each warning in the model, or None."""
    from version_adapter import element_id_value
    try:
        warnings = list(doc.GetWarnings())
    except Exception:
        return None
    keys = []
    for warning in warnings:
        try:
            description = warning.GetDescriptionText()
        except Exception:
            continue
        try:
            ids = tuple(sorted(element_id_value(item) for item in warning.GetFailingElements()))
        except Exception:
            ids = ()
        keys.append((description, ids))
    return keys


def new_warning_messages(before, after):
    """Return readable messages for warnings present after but not before."""
    if before is None or after is None:
        return []
    remaining = list(before)
    messages = []
    for key in after:
        if key in remaining:
            remaining.remove(key)
            continue
        description, ids = key
        if ids:
            messages.append("Revit warning: {0} (elements {1})".format(
                description, ", ".join(str(value) for value in ids)
            ))
        else:
            messages.append("Revit warning: {0}".format(description))
    return messages


class TransactionContext(object):
    """One Revit transaction that rolls back when the body raises."""

    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        self.warnings = []
        self._transaction = None
        self._before = None

    def __enter__(self):
        from version_adapter import get_db
        db_module = get_db()
        self._before = warning_keys(self.doc)
        self._transaction = db_module.Transaction(self.doc, self.name)
        self._transaction.Start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type:
            self._rollback()
            return False
        try:
            self._transaction.Commit()
        except Exception:
            self._rollback()
            raise
        self.warnings.extend(new_warning_messages(self._before, warning_keys(self.doc)))
        return False

    def _rollback(self):
        transaction = self._transaction
        if transaction is None:
            return
        try:
            if transaction.HasStarted() and not transaction.HasEnded():
                transaction.RollBack()
        except Exception as ex:
            LOGGER.error("Rollback failed for '%s': %s", self.name, ex)


class TransactionGroupContext(object):
    """Group of transactions undone together when any step raises."""

    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        self._group = None

    def __enter__(self):
        from version_adapter import get_db
        db_module = get_db()
        self._group = db_module.TransactionGroup(self.doc, self.name)
        self._group.Start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._group is None:
            return False
        if exc_type:
            self._rollback()
            return False
        self._group.Assimilate()
        return False

    def rollback(self):
        """Undo the group without raising."""
        self._rollback()

    def _rollback(self):
        try:
            if self._group.HasStarted() and not self._group.HasEnded():
                self._group.RollBack()
        except Exception as ex:
            LOGGER.error("Transaction group rollback failed for '%s': %s", self.name, ex)
