from __future__ import annotations

import unittest

from agentfabric.audit_bundle import AuditBundleExporter

from tests.renovation_helpers import (
    CHANGE_ORDER_PAYLOAD,
    DAILY_LOG_PAYLOAD,
    FIELD_NOTE_PAYLOAD,
    job_fixture,
)


class RenovationOperationsEventTests(unittest.TestCase):
    def test_operations_events_and_audit_bundle(self) -> None:
        persistence, events, service, context, _, _, job = job_fixture()
        service.add_daily_log(context, job.job_id, DAILY_LOG_PAYLOAD)
        service.add_field_note(context, job.job_id, FIELD_NOTE_PAYLOAD)
        order = service.create_change_order(
            context,
            {**CHANGE_ORDER_PAYLOAD, "job_id": job.job_id},
        )
        service.decide_change_order(
            context,
            order.change_order_id,
            "approved",
            {"decision_date": "2026-07-09", "decided_by": "Customer"},
        )
        service.export_change_order(context, order.change_order_id)
        event_types = {event.event_type for event in events.replay()}
        for event_type in {
            "renovation.job_created",
            "renovation.job_updated",
            "renovation.daily_log_created",
            "renovation.field_note_added",
            "renovation.photo_record_added",
            "renovation.issue_record_added",
            "renovation.change_order_created",
            "renovation.change_order_approved",
            "renovation.change_order_exported",
        }:
            self.assertIn(event_type, event_types)
        self.assertTrue(events.validate_integrity())
        bundle = AuditBundleExporter(
            persistence=persistence,
            event_store=events,
        ).export("tenant-a").as_dict()
        self.assertTrue(bundle["renovation_jobs"])
        self.assertTrue(bundle["renovation_daily_logs"])
        self.assertTrue(bundle["renovation_field_notes"])
        self.assertTrue(bundle["renovation_photo_records"])
        self.assertTrue(bundle["renovation_issue_records"])
        self.assertTrue(bundle["renovation_change_orders"])
        self.assertTrue(bundle["renovation_change_order_approvals"])
        self.assertTrue(bundle["renovation_change_order_exports"])
