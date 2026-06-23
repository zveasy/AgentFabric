"""Renovation job execution models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class JobPhase(SerializableModel):
    phase_id: str
    name: str
    sequence: int
    duration_days: int
    status: str = "pending"


@dataclass(frozen=True)
class Job(SerializableModel):
    job_id: str
    tenant_id: str
    proposal_id: str
    project_id: str
    title: str
    status: str
    accepted_date: str
    acceptance_reference: str
    phases: tuple[JobPhase, ...]
    current_phase: str
    template_id: str
