from __future__ import annotations

import unittest

from agentfabric.verticals.renovation.models import Room

from tests.renovation_helpers import ESTIMATE_PAYLOAD, service_fixture


class RenovationEstimateTests(unittest.TestCase):
    def test_deterministic_estimate_math_and_serialization(self) -> None:
        _, _, service, context = service_fixture()
        first = service.create_estimate(context, ESTIMATE_PAYLOAD)
        second = service.create_estimate(context, ESTIMATE_PAYLOAD)
        self.assertEqual(first.export_json(), second.export_json())
        self.assertEqual(first.estimate_id, second.estimate_id)
        self.assertEqual(first.material_total, 6050.0)
        self.assertEqual(first.labor_total, 5460.0)
        self.assertEqual(first.subtotal, 11510.0)
        self.assertEqual(first.contingency, 1151.0)
        self.assertEqual(first.tax, 432.06)
        self.assertEqual(first.total, 13093.06)
        self.assertEqual(first.as_dict()["rate_table_version"], "renovation-rates-v1")

    def test_room_dimensions_and_invalid_inputs(self) -> None:
        self.assertEqual(Room("Kitchen", 20, 15).area_sqft, 300.0)
        _, _, service, context = service_fixture()
        with self.assertRaises(ValueError):
            service.create_estimate(context, {**ESTIMATE_PAYLOAD, "scope_description": ""})
        with self.assertRaises(ValueError):
            service.create_estimate(context, {**ESTIMATE_PAYLOAD, "labor_rate": 0})
