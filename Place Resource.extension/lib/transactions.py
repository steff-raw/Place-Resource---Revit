# -*- coding: utf-8 -*-
"""Transaction helpers.

Transactions are not left open after an exception. Warning messages are
recorded and returned to the report. They are not suppressed.
"""

from logging_service import get_logger

LOGGER = get_logger("transactions")


class _WarningCollector(object):
    """Failures preprocessor that records Revit warnings and lets them through."""

    def __init__(self, db_module):
        self._db = db_module
        self.messages = []

    def PreprocessFailures(self, failures_accessor):
        try:
            for message in failures_accessor.GetFailureMessages():
                description = message.GetDescriptionText()
                severity = message.GetSeverity()
                self.messages.append("{0}: {1}".format(severity, description))
        except Exception as ex:
            self.messages.append("Could not read a Revit failure message: {0}".format(ex))
        return self._db.FailureProcessingResult.Continue


# pythonnet registers a .NET type per class. The CPython engine is shared for
# the whole Revit session, so a second definition with the same name fails.
# The class is kept on ``sys`` because pyRevit may re-import this module.
_COLLECTOR_TYPE_ATTR = "_place_resource_warning_collector_type"


def _warning_collector_type(db_module):
    import sys
    cached = getattr(sys, _COLLECTOR_TYPE_ATTR, None)
    if cached is not None:
        return cached
    collector_type = type(
        "PlaceResourceWarningCollector",
        (_WarningCollector, db_module.IFailuresPreprocessor),
        {"__namespace__": "PlaceResourceLegendCreator"},
    )
    setattr(sys, _COLLECTOR_TYPE_ATTR, collector_type)
    return collector_type


def _bind_warning_collector(db_module):
    """Create a preprocessor instance, or None if this host cannot bind one."""
    try:
        return _warning_collector_type(db_module)(db_module)
    except Exception as ex:
        LOGGER.warning("Revit warning capture was not attached: %s", ex)
        return None


class TransactionContext(object):
    """One Revit transaction that rolls back when the body raises."""

    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        self.warnings = []
        self._transaction = None
        self._collector = None

    def __enter__(self):
        from version_adapter import get_db
        db_module = get_db()
        self._transaction = db_module.Transaction(self.doc, self.name)
        self._transaction.Start()
        self._collector = _bind_warning_collector(db_module)
        if self._collector is not None:
            options = self._transaction.GetFailureHandlingOptions()
            options.SetFailuresPreprocessor(self._collector)
            options.SetClearAfterRollback(True)
            self._transaction.SetFailureHandlingOptions(options)
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._collect_warnings()
        if exc_type:
            self._rollback()
            return False
        try:
            self._transaction.Commit()
        except Exception:
            self._rollback()
            raise
        return False

    def _collect_warnings(self):
        if self._collector is not None:
            self.warnings.extend(self._collector.messages)

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
