"""Agent organization roles."""

from __future__ import annotations

from enum import Enum


class AgentRole(str, Enum):
    PLANNER = "planner"
    RESEARCHER = "researcher"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    COMPLIANCE_REVIEWER = "compliance_reviewer"
    SECURITY_REVIEWER = "security_reviewer"
    HUMAN_APPROVER = "human_approver"
    OBSERVER = "observer"


AUTHORIZED_VOTING_ROLES = {
    AgentRole.PLANNER.value,
    AgentRole.EXECUTOR.value,
    AgentRole.REVIEWER.value,
    AgentRole.COMPLIANCE_REVIEWER.value,
    AgentRole.SECURITY_REVIEWER.value,
    AgentRole.HUMAN_APPROVER.value,
}
