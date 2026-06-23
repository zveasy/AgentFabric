"""Deterministic proposal-to-job conversion."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json

from agentfabric.verticals.renovation.models import Proposal

from .models import Job, JobPhase


JOB_STATUSES = {"planned", "active", "on_hold", "completed", "cancelled"}
PHASE_STATUSES = {"pending", "active", "completed", "skipped"}


class JobService:
    def create(self, tenant_id: str, proposal: Proposal, payload: dict[str, object]) -> Job:
        if proposal.tenant_id != tenant_id:
            raise PermissionError("cross-tenant proposal access denied")
        if not bool(payload.get("accepted", False)):
            raise ValueError("accepted proposal is required to create a job")
        accepted_date = str(payload["accepted_date"]).strip()
        reference = str(payload["acceptance_reference"]).strip()
        if not accepted_date or not reference:
            raise ValueError("acceptance date and reference are required")
        phases = tuple(
            JobPhase(
                phase_id=f"phase-{index:02d}",
                name=item.phase,
                sequence=item.sequence,
                duration_days=item.duration_days,
                status="active" if index == 1 else "pending",
            )
            for index, item in enumerate(proposal.timeline, start=1)
        )
        identity = {
            "tenant_id": tenant_id,
            "proposal_id": proposal.proposal_id,
            "accepted_date": accepted_date,
            "acceptance_reference": reference,
        }
        return Job(
            job_id=f"job-{_digest(identity)[:20]}",
            tenant_id=tenant_id,
            proposal_id=proposal.proposal_id,
            project_id=proposal.project.project_id,
            title=proposal.project.title,
            status=str(payload.get("status", "active")),
            accepted_date=accepted_date,
            acceptance_reference=reference,
            phases=phases,
            current_phase=phases[0].phase_id if phases else "",
            template_id=proposal.template_id,
        )

    def update(self, job: Job, payload: dict[str, object]) -> Job:
        status = str(payload.get("status", job.status))
        if status not in JOB_STATUSES:
            raise ValueError("invalid renovation job status")
        current_phase = str(payload.get("current_phase", job.current_phase))
        phase_statuses = {
            str(key): str(value)
            for key, value in dict(payload.get("phase_statuses", {})).items()
        }
        phases = []
        phase_ids = {item.phase_id for item in job.phases}
        if current_phase and current_phase not in phase_ids:
            raise ValueError("current job phase does not exist")
        for phase in job.phases:
            phase_status = phase_statuses.get(phase.phase_id, phase.status)
            if phase_status not in PHASE_STATUSES:
                raise ValueError("invalid job phase status")
            phases.append(replace(phase, status=phase_status))
        return replace(job, status=status, current_phase=current_phase, phases=tuple(phases))


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
