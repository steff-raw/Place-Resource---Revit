# -*- coding: utf-8 -*-
"""Seed copy handles the collection returned by CopyElement."""

import os
import sys
import unittest
from unittest import mock

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import version_adapter
from errors import UnsupportedRevitOperationError
from legend_component_service import LegendComponentService


class _Seed(object):
    Id = "seed-id"


def _fake_db(copied_ids):
    class _XYZ(object):
        def __init__(self, x, y, z):
            self.X, self.Y, self.Z = x, y, z

    class _Utils(object):
        @staticmethod
        def CopyElement(doc, element_id, offset):
            return copied_ids

    return type("DB", (), {"XYZ": _XYZ, "ElementTransformUtils": _Utils})


class _Doc(object):
    def __init__(self, elements):
        self.elements = elements

    def GetElement(self, element_id):
        return self.elements.get(element_id)


class CopyComponentTests(unittest.TestCase):
    def test_first_copied_id_is_used(self):
        copy = object()
        service = LegendComponentService(_Doc({"new-id": copy}), None)
        with mock.patch.object(version_adapter, "get_db", return_value=_fake_db(["new-id"])):
            self.assertIs(service.copy_component(_Seed(), 0), copy)

    def test_empty_copy_result_raises(self):
        service = LegendComponentService(_Doc({}), None)
        with mock.patch.object(version_adapter, "get_db", return_value=_fake_db([])):
            with self.assertRaises(UnsupportedRevitOperationError):
                service.copy_component(_Seed(), 0)


if __name__ == "__main__":
    unittest.main()
