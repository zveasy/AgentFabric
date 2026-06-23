"""Crew coordination models."""

from dataclasses import dataclass

from agentfabric.verticals.renovation.models.base import SerializableModel


@dataclass(frozen=True)
class CrewMember(SerializableModel):
    member_id: str
    name: str
    role: str
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class Crew(SerializableModel):
    crew_id: str
    tenant_id: str
    name: str
    members: tuple[CrewMember, ...]
    skills: tuple[str, ...]
    active: bool = True


@dataclass(frozen=True)
class CrewAvailability(SerializableModel):
    availability_id: str
    tenant_id: str
    crew_id: str
    start_date: str
    end_date: str
    status: str
    note: str = ""


@dataclass(frozen=True)
class CrewAssignment(SerializableModel):
    assignment_id: str
    tenant_id: str
    crew_id: str
    job_id: str
    schedule_id: str
    phase_id: str
    start_date: str
    end_date: str
    status: str = "assigned"
