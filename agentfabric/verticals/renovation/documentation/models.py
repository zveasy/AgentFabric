"""Renovation job documentation models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class DailyLog(SerializableModel):
    daily_log_id: str
    tenant_id: str
    job_id: str
    work_date: str
    summary: str
    weather: str
    crew_hours: float
    completed_work: tuple[str, ...]
    next_steps: tuple[str, ...]
    photo_record_ids: tuple[str, ...]
    issue_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class FieldNote(SerializableModel):
    field_note_id: str
    tenant_id: str
    job_id: str
    note_date: str
    author: str
    note: str
    source: str
    photo_record_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PhotoRecord(SerializableModel):
    photo_record_id: str
    tenant_id: str
    job_id: str
    captured_date: str
    file_name: str
    storage_reference: str
    sha256: str
    caption: str = ""
    phase_id: str = ""


@dataclass(frozen=True)
class IssueRecord(SerializableModel):
    issue_record_id: str
    tenant_id: str
    job_id: str
    reported_date: str
    title: str
    description: str
    severity: str
    status: str
    phase_id: str = ""
