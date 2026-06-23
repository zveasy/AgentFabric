from __future__ import annotations

import unittest

from agentfabric.verticals.renovation.templates import TEMPLATE_NAMES, load_template


class RenovationTemplateTests(unittest.TestCase):
    def test_all_templates_are_complete_and_deterministic(self) -> None:
        self.assertEqual(len(TEMPLATE_NAMES), 4)
        for template_id in TEMPLATE_NAMES:
            first = load_template(template_id)
            second = load_template(template_id)
            self.assertEqual(first, second)
            self.assertEqual(first["template_id"], template_id)
            self.assertEqual(
                sum(float(item["percentage"]) for item in first["payment_terms"]),
                100,
            )
            self.assertTrue(first["project_phases"])
            self.assertTrue(first["clauses"])

    def test_template_selection_changes_style(self) -> None:
        standard = load_template("standard_proposal")
        premium = load_template("premium_proposal")
        self.assertEqual(standard["warranty_months"], 12)
        self.assertEqual(premium["warranty_months"], 24)
        with self.assertRaises(ValueError):
            load_template("unknown")
