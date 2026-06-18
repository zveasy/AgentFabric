from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VersionRecord:
    agent_id: str
    version: str
    parent_version: str | None = None
    forked_from: str | None = None


@dataclass(frozen=True)
class MergeProposal:
    proposal_id: str
    source_version: str
    target_version: str
    permission_escalation: bool = False
    evaluation_passed: bool = False
