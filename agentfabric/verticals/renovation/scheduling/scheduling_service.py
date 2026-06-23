"""Deterministic dependency scheduling and impact analysis."""

from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import json

from agentfabric.verticals.renovation.crews import (
    CrewAssignment,
    CrewAvailability,
    overlaps,
)
from agentfabric.verticals.renovation.deliveries import (
    MaterialDelivery,
    delivery_effective_date,
)
from agentfabric.verticals.renovation.jobs import Job

from .models import (
    DelayImpact,
    PhaseDependency,
    Schedule,
    ScheduleConflict,
    SchedulePhase,
)


DEPENDENCY_TYPES = {"finish_to_start"}
SCHEDULE_STATUSES = {"planned", "active", "delayed", "completed", "cancelled"}


class SchedulingService:
    def create(self, tenant_id: str, job: Job, payload: dict[str, object]) -> Schedule:
        if job.tenant_id != tenant_id:
            raise PermissionError("cross-tenant job access denied")
        start = _date(str(payload.get("start_date", job.accepted_date)))
        status = str(payload.get("status", "planned"))
        if status not in SCHEDULE_STATUSES:
            raise ValueError("invalid schedule status")
        durations = {
            str(key): int(value)
            for key, value in dict(payload.get("phase_durations", {})).items()
        }
        job_phase_ids = {phase.phase_id for phase in job.phases}
        if set(durations) - job_phase_ids:
            raise ValueError("schedule duration override references an unknown phase")
        dependencies = self._dependencies(job, payload)
        ordered = self._ordered_phases(job, dependencies)
        phase_dates: dict[str, tuple[date, date]] = {}
        phases: list[SchedulePhase] = []
        for phase in ordered:
            duration = durations.get(phase.phase_id, phase.duration_days)
            if duration <= 0:
                raise ValueError("schedule phase duration must be positive")
            predecessors = [
                item for item in dependencies if item.successor_phase_id == phase.phase_id
            ]
            phase_start = start
            for dependency in predecessors:
                predecessor_end = phase_dates[dependency.predecessor_phase_id][1]
                phase_start = max(
                    phase_start,
                    predecessor_end + timedelta(days=1 + dependency.lag_days),
                )
            phase_end = phase_start + timedelta(days=duration - 1)
            phase_dates[phase.phase_id] = (phase_start, phase_end)
            phases.append(
                SchedulePhase(
                    phase_id=phase.phase_id,
                    name=phase.name,
                    sequence=phase.sequence,
                    duration_days=duration,
                    planned_start=phase_start.isoformat(),
                    planned_end=phase_end.isoformat(),
                    status=phase.status,
                )
            )
        completion = max((_date(item.planned_end) for item in phases), default=start)
        identity = {
            "tenant_id": tenant_id,
            "job_id": job.job_id,
            "start_date": start.isoformat(),
            "phases": [
                {
                    "phase_id": item.phase_id,
                    "duration_days": item.duration_days,
                }
                for item in phases
            ],
            "dependencies": [item.as_dict() for item in dependencies],
        }
        return _schedule(
            schedule_id=f"schedule-{_digest(identity)[:20]}",
            tenant_id=tenant_id,
            job_id=job.job_id,
            start_date=start.isoformat(),
            original_completion_date=completion.isoformat(),
            projected_completion_date=completion.isoformat(),
            status=status,
            revision=1,
            phases=tuple(phases),
            dependencies=dependencies,
            conflicts=(),
            delay_impacts=(),
        )

    def recalculate(
        self,
        schedule: Schedule,
        assignments: tuple[CrewAssignment, ...],
        availability: tuple[CrewAvailability, ...],
        deliveries: tuple[MaterialDelivery, ...],
        payload: dict[str, object],
    ) -> Schedule:
        status = str(payload.get("status", schedule.status))
        if status not in SCHEDULE_STATUSES:
            raise ValueError("invalid schedule status")
        assignment_map: dict[str, list[CrewAssignment]] = {}
        delivery_map: dict[str, list[MaterialDelivery]] = {}
        for assignment in assignments:
            if assignment.schedule_id == schedule.schedule_id:
                assignment_map.setdefault(assignment.phase_id, []).append(assignment)
        for delivery in deliveries:
            delivery_map.setdefault(delivery.phase_id, []).append(delivery)

        conflicts = self._crew_conflicts(schedule.schedule_id, assignments, availability)
        conflict_map: dict[str, list[ScheduleConflict]] = {}
        for conflict in conflicts:
            conflict_map.setdefault(conflict.phase_id, []).append(conflict)

        baseline_dates: dict[str, tuple[date, date]] = {}
        phase_dates: dict[str, tuple[date, date]] = {}
        recalculated: list[SchedulePhase] = []
        impacts: list[DelayImpact] = []
        for phase in schedule.phases:
            predecessors = [
                item
                for item in schedule.dependencies
                if item.successor_phase_id == phase.phase_id
            ]
            baseline_start = _date(schedule.start_date)
            for dependency in predecessors:
                baseline_predecessor_end = baseline_dates[dependency.predecessor_phase_id][1]
                baseline_start = max(
                    baseline_start,
                    baseline_predecessor_end
                    + timedelta(days=1 + dependency.lag_days),
                )
            baseline_end = baseline_start + timedelta(days=phase.duration_days - 1)
            baseline_dates[phase.phase_id] = (baseline_start, baseline_end)

            phase_start = baseline_start
            for dependency in predecessors:
                predecessor_end = phase_dates[dependency.predecessor_phase_id][1]
                phase_start = max(
                    phase_start,
                    predecessor_end + timedelta(days=1 + dependency.lag_days),
                )

            blocked: list[str] = []
            delivery_delay = 0
            for delivery in sorted(
                delivery_map.get(phase.phase_id, ()),
                key=lambda item: item.delivery_id,
            ):
                effective = delivery_effective_date(delivery)
                required = _date(delivery.required_date)
                late_days = max(0, (effective - required).days)
                if delivery.status in {"delayed", "cancelled"} or late_days:
                    delivery_delay = max(delivery_delay, late_days or 1)
                    blocked.append(f"material delivery {delivery.delivery_id} is {delivery.status}")
                phase_start = max(phase_start, effective)

            phase_conflicts = conflict_map.get(phase.phase_id, ())
            if phase_conflicts:
                phase_start += timedelta(days=len(phase_conflicts))
                blocked.extend(item.description for item in phase_conflicts)

            phase_end = phase_start + timedelta(days=phase.duration_days - 1)
            phase_dates[phase.phase_id] = (phase_start, phase_end)
            delay_days = max(0, (phase_end - baseline_end).days)
            if delay_days:
                if delivery_delay:
                    source_type = "delivery"
                    source_id = sorted(
                        delivery_map[phase.phase_id],
                        key=lambda item: item.delivery_id,
                    )[0].delivery_id
                elif phase_conflicts:
                    source_type = "crew"
                    source_id = sorted(
                        phase_conflicts,
                        key=lambda item: item.conflict_id,
                    )[0].reference_id
                else:
                    source_type = "dependency"
                    source_id = sorted(
                        predecessors,
                        key=lambda item: item.predecessor_phase_id,
                    )[0].predecessor_phase_id
                impact_identity = {
                    "schedule_id": schedule.schedule_id,
                    "phase_id": phase.phase_id,
                    "source_type": source_type,
                    "source_id": source_id,
                    "delay_days": delay_days,
                    "revision": schedule.revision + 1,
                }
                impacts.append(
                    DelayImpact(
                        delay_id=f"delay-{_digest(impact_identity)[:20]}",
                        schedule_id=schedule.schedule_id,
                        source_type=source_type,
                        source_id=source_id,
                        phase_id=phase.phase_id,
                        delay_days=delay_days,
                        original_completion_date=schedule.original_completion_date,
                        projected_completion_date=phase_end.isoformat(),
                        summary=(
                            f"{phase.name} is projected {delay_days} day(s) later "
                            f"because of {source_type} constraints."
                        ),
                    )
                )
            recalculated.append(
                SchedulePhase(
                    phase_id=phase.phase_id,
                    name=phase.name,
                    sequence=phase.sequence,
                    duration_days=phase.duration_days,
                    planned_start=phase_start.isoformat(),
                    planned_end=phase_end.isoformat(),
                    status="blocked" if blocked else phase.status,
                    crew_assignment_ids=tuple(
                        item.assignment_id
                        for item in sorted(
                            assignment_map.get(phase.phase_id, ()),
                            key=lambda item: item.assignment_id,
                        )
                    ),
                    delivery_ids=tuple(
                        item.delivery_id
                        for item in sorted(
                            delivery_map.get(phase.phase_id, ()),
                            key=lambda item: item.delivery_id,
                        )
                    ),
                    blocked_reasons=tuple(sorted(set(blocked))),
                )
            )

        completion = max(
            (_date(item.planned_end) for item in recalculated),
            default=_date(schedule.start_date),
        )
        final_status = "delayed" if completion > _date(schedule.original_completion_date) else status
        normalized_impacts = tuple(
            DelayImpact(
                delay_id=item.delay_id,
                schedule_id=item.schedule_id,
                source_type=item.source_type,
                source_id=item.source_id,
                phase_id=item.phase_id,
                delay_days=item.delay_days,
                original_completion_date=item.original_completion_date,
                projected_completion_date=completion.isoformat(),
                summary=item.summary,
            )
            for item in impacts
        )
        return _schedule(
            schedule_id=schedule.schedule_id,
            tenant_id=schedule.tenant_id,
            job_id=schedule.job_id,
            start_date=schedule.start_date,
            original_completion_date=schedule.original_completion_date,
            projected_completion_date=completion.isoformat(),
            status=final_status,
            revision=schedule.revision + 1,
            phases=tuple(recalculated),
            dependencies=schedule.dependencies,
            conflicts=conflicts,
            delay_impacts=normalized_impacts,
        )

    def customer_summary(self, schedule: Schedule) -> dict[str, object]:
        summary = {
            "schedule_id": schedule.schedule_id,
            "job_id": schedule.job_id,
            "status": schedule.status,
            "start_date": schedule.start_date,
            "projected_completion_date": schedule.projected_completion_date,
            "total_delay_days": max(
                0,
                (
                    _date(schedule.projected_completion_date)
                    - _date(schedule.original_completion_date)
                ).days,
            ),
            "phases": [
                {
                    "name": phase.name,
                    "start_date": phase.planned_start,
                    "end_date": phase.planned_end,
                    "status": phase.status,
                }
                for phase in sorted(
                    schedule.phases,
                    key=lambda item: (item.sequence, item.phase_id),
                )
            ],
            "delay_summaries": [item.summary for item in schedule.delay_impacts],
        }
        return {**summary, "summary_hash": _digest(summary)}

    def _dependencies(
        self,
        job: Job,
        payload: dict[str, object],
    ) -> tuple[PhaseDependency, ...]:
        if "dependencies" in payload:
            dependencies = tuple(
                PhaseDependency(
                    predecessor_phase_id=str(item["predecessor_phase_id"]),
                    successor_phase_id=str(item["successor_phase_id"]),
                    dependency_type=str(item.get("dependency_type", "finish_to_start")),
                    lag_days=int(item.get("lag_days", 0)),
                )
                for item in payload["dependencies"]
            )
        else:
            ordered = sorted(job.phases, key=lambda item: (item.sequence, item.phase_id))
            dependencies = tuple(
                PhaseDependency(
                    predecessor_phase_id=first.phase_id,
                    successor_phase_id=second.phase_id,
                )
                for first, second in zip(ordered, ordered[1:], strict=False)
            )
        phase_ids = {item.phase_id for item in job.phases}
        for dependency in dependencies:
            if dependency.predecessor_phase_id not in phase_ids or dependency.successor_phase_id not in phase_ids:
                raise ValueError("schedule dependency references an unknown phase")
            if dependency.predecessor_phase_id == dependency.successor_phase_id:
                raise ValueError("schedule phase cannot depend on itself")
            if dependency.dependency_type not in DEPENDENCY_TYPES or dependency.lag_days < 0:
                raise ValueError("invalid schedule dependency")
        return tuple(
            sorted(
                dependencies,
                key=lambda item: (
                    item.successor_phase_id,
                    item.predecessor_phase_id,
                    item.lag_days,
                ),
            )
        )

    def _ordered_phases(
        self,
        job: Job,
        dependencies: tuple[PhaseDependency, ...],
    ) -> list[object]:
        phases = {item.phase_id: item for item in job.phases}
        incoming = {phase_id: 0 for phase_id in phases}
        successors: dict[str, list[str]] = {phase_id: [] for phase_id in phases}
        for dependency in dependencies:
            incoming[dependency.successor_phase_id] += 1
            successors[dependency.predecessor_phase_id].append(dependency.successor_phase_id)
        ready = sorted(
            (phases[phase_id] for phase_id, count in incoming.items() if count == 0),
            key=lambda item: (item.sequence, item.phase_id),
        )
        ordered = []
        while ready:
            phase = ready.pop(0)
            ordered.append(phase)
            for successor in sorted(successors[phase.phase_id]):
                incoming[successor] -= 1
                if incoming[successor] == 0:
                    ready.append(phases[successor])
                    ready.sort(key=lambda item: (item.sequence, item.phase_id))
        if len(ordered) != len(phases):
            raise ValueError("schedule dependency graph contains a cycle")
        return ordered

    def _crew_conflicts(
        self,
        schedule_id: str,
        assignments: tuple[CrewAssignment, ...],
        availability: tuple[CrewAvailability, ...],
    ) -> tuple[ScheduleConflict, ...]:
        conflicts: list[ScheduleConflict] = []
        active = sorted(
            (item for item in assignments if item.status != "cancelled"),
            key=lambda item: item.assignment_id,
        )
        for index, first in enumerate(active):
            for second in active[index + 1 :]:
                if (
                    first.crew_id == second.crew_id
                    and first.assignment_id != second.assignment_id
                    and schedule_id in {first.schedule_id, second.schedule_id}
                    and overlaps(
                        first.start_date,
                        first.end_date,
                        second.start_date,
                        second.end_date,
                    )
                ):
                    conflicts.append(
                        _conflict(
                            "crew_overlap",
                            (
                                first.phase_id
                                if first.schedule_id == schedule_id
                                else second.phase_id
                            ),
                            (
                                second.assignment_id
                                if first.schedule_id == schedule_id
                                else first.assignment_id
                            ),
                            f"Crew {first.crew_id} has overlapping assignments.",
                        )
                    )
        for assignment in active:
            if assignment.schedule_id != schedule_id:
                continue
            unavailable = [
                item
                for item in availability
                if item.crew_id == assignment.crew_id
                and item.status in {"unavailable", "limited"}
                and overlaps(
                    assignment.start_date,
                    assignment.end_date,
                    item.start_date,
                    item.end_date,
                )
            ]
            for record in sorted(unavailable, key=lambda item: item.availability_id):
                conflicts.append(
                    _conflict(
                        "crew_unavailable",
                        assignment.phase_id,
                        record.availability_id,
                        f"Crew {assignment.crew_id} is {record.status} during the assignment.",
                    )
                )
        unique = {item.conflict_id: item for item in conflicts}
        return tuple(unique[key] for key in sorted(unique))


def _conflict(
    conflict_type: str,
    phase_id: str,
    reference_id: str,
    description: str,
) -> ScheduleConflict:
    identity = {
        "conflict_type": conflict_type,
        "phase_id": phase_id,
        "reference_id": reference_id,
        "description": description,
    }
    return ScheduleConflict(
        conflict_id=f"conflict-{_digest(identity)[:20]}",
        conflict_type=conflict_type,
        severity="high",
        phase_id=phase_id,
        reference_id=reference_id,
        description=description,
    )


def _schedule(**values: object) -> Schedule:
    value_without_hash = {**values, "schedule_hash": ""}
    provisional = Schedule(**value_without_hash)
    return Schedule(**{**values, "schedule_hash": _digest(provisional.as_dict())})


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
