# -*- coding: utf-8 -*-
"""Warning-collector class is defined once per session."""

import os
import sys
import unittest

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import transactions


class _FakeDB(object):
    class IFailuresPreprocessor(object):
        pass


class WarningCollectorTypeTests(unittest.TestCase):
    def setUp(self):
        if hasattr(sys, transactions._COLLECTOR_TYPE_ATTR):
            delattr(sys, transactions._COLLECTOR_TYPE_ATTR)

    tearDown = setUp

    def test_type_is_created_once(self):
        first = transactions._warning_collector_type(_FakeDB)
        second = transactions._warning_collector_type(_FakeDB)
        self.assertIs(first, second)

    def test_bound_collector_is_usable(self):
        collector = transactions._bind_warning_collector(_FakeDB)
        self.assertIsNotNone(collector)
        self.assertEqual(collector.messages, [])


if __name__ == "__main__":
    unittest.main()
