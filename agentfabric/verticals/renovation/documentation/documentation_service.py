"""Deterministic field documentation creation and summaries."""

from __future__ import annotations

from hashlib import sha256
import json

from .models import DailyLog, FieldNote, IssueRecord, PhotoRecord


class DocumentationService:
    def photo(self, tenant_id: str, job_id: str, payload: dict[str, object]) -> PhotoRecord:
        if payload.get("content") or payload.get("data"):
            raise ValueError("photo binary content is not accepted; metadata references only")
        required = ("captured_date", "file_name", "storage_reference", "sha256")
        if not all(str(payload.get(key, "")).strip() for key in required):
            raise ValueError("photo metadata is incomplete")
        identity = {"tenant_id": tenant_id, "job_id": job_id, **payload}
        return PhotoRecord(
            photo_record_id=f"photo-{_digest(identity)[:20]}",
            tenant_id=tenant_id,
            job_id=job_id,
            captured_date=str(payload["captured_date"]),
            file_name=str(payload["file_name"]),
            storage_reference=str(payload["storage_reference"]),
            sha256=str(payload["sha256"]),
            caption=str(payload.get("caption", "")),
            phase_id=str(payload.get("phase_id", "")),
        )

    def issue(self, tenant_id: str, job_id: str, payload: dict[str, object]) -> IssueRecord:
        severity = str(payload.get("severity", "medium"))
        status = str(payload.get("status", "open"))
        if severity not in {"low", "medium", "high", "critical"}:
            raise ValueError("invalid issue severity")
        if status not in {"open", "monitoring", "resolved", "closed"}:
            raise ValueError("invalid issue status")
        identity = {"tenant_id": tenant_id, "job_id": job_id, **payload}
        return IssueRecord(
            issue_record_id=f"issue-{_digest(identity)[:20]}",
            tenant_id=tenant_id,
            job_id=job_id,
            reported_date=str(payload["reported_date"]),
            title=str(payload["title"]),
            description=str(payload.get("description", "")),
            severity=severity,
            status=status,
            phase_id=str(payload.get("phase_id", "")),
        )

    def daily_log(
        self,
        tenant_id: str,
        job_id: str,
        payload: dict[str, object],
        photos: tuple[PhotoRecord, ...],
        issues: tuple[IssueRecord, ...],
    ) -> DailyLog:
        if not str(payload.get("work_date", "")).strip() or not str(payload.get("summary", "")).strip():
            raise ValueError("daily log date and summary are required")
        identity = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "work_date": payload["work_date"],
            "summary": payload["summary"],
            "weather": payload.get("weather", ""),
            "crew_hours": float(payload.get("crew_hours", 0)),
            "completed_work": sorted(str(item) for item in payload.get("completed_work", ())),
            "next_steps": sorted(str(item) for item in payload.get("next_steps", ())),
            "photo_ids": sorted(item.photo_record_id for item in photos),
            "issue_ids": sorted(item.issue_record_id for item in issues),
        }
        return DailyLog(
            daily_log_id=f"log-{_digest(identity)[:20]}",
            tenant_id=tenant_id,
            job_id=job_id,
            work_date=str(payload["work_date"]),
            summary=str(payload["summary"]).strip(),
            weather=str(payload.get("weather", "")),
            crew_hours=round(float(payload.get("crew_hours", 0)), 2),
            completed_work=tuple(identity["completed_work"]),
            next_steps=tuple(identity["next_steps"]),
            photo_record_ids=tuple(identity["photo_ids"]),
            issue_record_ids=tuple(identity["issue_ids"]),
        )

    def field_note(
        self,
        tenant_id: str,
        job_id: str,
        payload: dict[str, object],
        photos: tuple[PhotoRecord, ...],
    ) -> FieldNote:
        if not str(payload.get("note_date", "")).strip() or not str(payload.get("note", "")).strip():
            raise ValueError("field note date and content are required")
        identity = {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "note_date": payload["note_date"],
            "author": payload.get("author", ""),
            "note": payload["note"],
            "source": payload.get("source", "field"),
            "photo_ids": sorted(item.photo_record_id for item in photos),
        }
        return FieldNote(
            field_note_id=f"note-{_digest(identity)[:20]}",
            tenant_id=tenant_id,
            job_id=job_id,
            note_date=str(payload["note_date"]),
            author=str(payload.get("author", "")),
            note=str(payload["note"]).strip(),
            source=str(payload.get("source", "field")),
            photo_record_ids=tuple(identity["photo_ids"]),
        )

    def daily_summary(
        self,
        work_date: str,
        logs: list[dict[str, object]],
        notes: list[dict[str, object]],
        photos: list[dict[str, object]],
        issues: list[dict[str, object]],
    ) -> dict[str, object]:
        value = {
            "work_date": work_date,
            "daily_logs": sorted(logs, key=lambda item: str(item["daily_log_id"])),
            "field_notes": sorted(notes, key=lambda item: str(item["field_note_id"])),
            "photos": sorted(photos, key=lambda item: str(item["photo_record_id"])),
            "issues": sorted(issues, key=lambda item: str(item["issue_record_id"])),
        }
        value["summary_hash"] = _digest(value)
        return value


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
