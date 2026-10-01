# -*- coding: utf-8 -*-
"""Reading and writing the stored legend text falls back when one call style fails."""

import os
import sys
import types
import unittest
from unittest import mock

LIB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "lib"))
if LIB not in sys.path:
    sys.path.insert(0, LIB)

import identity


class _Field(object):
    FieldName = "Payload"


class _Generic(object):
    """entity.Get[String] / entity.Set[String]: only the listed argument kinds work."""

    def __init__(self, store, accept):
        self.store = store
        self.accept = accept

    def __getitem__(self, _type):
        def call(key, *value):
            if not isinstance(key, self.accept):
                raise TypeError("No method matches given arguments")
            if value:
                self.store["Payload"] = value[0]
                return None
            return self.store.get("Payload")
        return call


class _Entity(object):
    def __init__(self, accept):
        self.store = {}
        self.Get = _Generic(self.store, accept)
        self.Set = _Generic(self.store, accept)


class EntityTextTests(unittest.TestCase):
    def setUp(self):
        fake = types.ModuleType("System")
        fake.String = str
        fake.Object = object
        fake.Array = {object: list}
        self.patch = mock.patch.dict(sys.modules, {"System": fake})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_field_call_works(self):
        entity = _Entity(accept=_Field)
        identity._entity_set_text(entity, _Field(), '{"a": 1}')
        self.assertEqual(identity._entity_get_text(entity, _Field()), '{"a": 1}')

    def test_falls_back_to_field_name(self):
        entity = _Entity(accept=str)
        entity.store["Payload"] = '{"a": 2}'
        self.assertEqual(identity._entity_get_text(entity, _Field()), '{"a": 2}')

    def test_reports_every_failure(self):
        entity = _Entity(accept=int)
        entity.GetType = lambda: types.SimpleNamespace(GetMethods=lambda: [])
        with self.assertRaises(LookupError) as caught:
            identity._entity_get_text(entity, _Field())
        self.assertIn("not found", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
