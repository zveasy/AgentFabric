from __future__ import annotations

import unittest

from tests.renovation_helpers import DAILY_LOG_PAYLOAD, FIELD_NOTE_PAYLOAD, job_fixture


class RenovationDocumentationTests(unittest.TestCase):
    def test_daily_log_photos_issues_summary_and_history(self) -> None:
        persistence, _, service, context, _, _, job = job_fixture()
        log = service.add_daily_log(context, job.job_id, DAILY_LOG_PAYLOAD)
        self.assertEqual(log.crew_hours, 16)
        self.assertEqual(len(log.photo_record_ids), 1)
        self.assertEqual(len(log.issue_record_ids), 1)
        self.assertEqual(service.replay_daily_log(context, log.daily_log_id), log)
        summary = service.daily_summary(context, job.job_id, "2026-07-08")
        self.assertEqual(len(summary["daily_logs"]), 1)
        self.assertEqual(len(summary["photos"]), 1)
        self.assertEqual(len(summary["issues"]), 1)
        self.assertEqual(len(summary["summary_hash"]), 64)
        photo = persistence.list_tenant("renovation_photo_records", "tenant-a")[0]["artifact"]
        self.assertEqual(photo["storage_reference"], "veil:photo:kitchen-subfloor")
        self.assertNotIn("content", photo)
        history = service.project_history(context, job.job_id)
        self.assertEqual(len(history["daily_logs"]), 1)
        self.assertEqual(len(history["photos"]), 1)
        self.assertEqual(len(history["issues"]), 1)
        self.assertEqual(len(history["history_hash"]), 64)

    def test_field_note_and_photo_metadata_are_deterministic(self) -> None:
        _, _, service, context, _, _, job = job_fixture()
        first = service.add_field_note(context, job.job_id, FIELD_NOTE_PAYLOAD)
        second = service.add_field_note(context, job.job_id, FIELD_NOTE_PAYLOAD)
        self.assertEqual(first.export_json(), second.export_json())
        self.assertEqual(first.field_note_id, second.field_note_id)
        self.assertEqual(len(first.photo_record_ids), 1)
        self.assertEqual(service.replay_field_note(context, first.field_note_id), first)
        bad = {
            **FIELD_NOTE_PAYLOAD,
            "photos": [
                {
                    **FIELD_NOTE_PAYLOAD["photos"][0],
                    "content": "raw-image-data",
                }
            ],
        }
        with self.assertRaises(ValueError):
            service.add_field_note(context, job.job_id, bad)
