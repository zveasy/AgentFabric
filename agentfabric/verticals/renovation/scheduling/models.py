"""Renovation scheduling models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class PhaseDependency(SerializableModel):
    predecessor_phase_id: str
    successor_phase_id: str
    dependency_type: str = "finish_to_start"
    lag_days: int = 0


@dataclass(frozen=True)
class SchedulePhase(SerializableModel):
    phase_id: str
    name: str
    sequence: int
    duration_days: int
    planned_start: str
    planned_end: str
    status: str
    crew_assignment_ids: tuple[str, ...] = ()
    delivery_ids: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScheduleConflict(SerializableModel):
    conflict_id: str
    conflict_type: str
    severity: str
    phase_id: str
    reference_id: str
    description: str


@dataclass(frozen=True)
class DelayImpact(SerializableModel):
    delay_id: str
    schedule_id: str
    source_type: str
    source_id: str
    phase_id: str
    delay_days: int
    original_completion_date: str
    projected_completion_date: str
    summary: str


@dataclass(frozen=True)
class Schedule(SerializableModel):
    schedule_id: str
    tenant_id: str
    job_id: str
    start_date: str
    original_completion_date: str
    projected_completion_date: str
    status: str
    revision: int
    phases: tuple[SchedulePhase, ...]
    dependencies: tuple[PhaseDependency, ...]
    conflicts: tuple[ScheduleConflict, ...]
    delay_impacts: tuple[DelayImpact, ...]
    schedule_hash: str
