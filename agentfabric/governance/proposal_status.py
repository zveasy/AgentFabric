"""Proposal status values."""

from __future__ import annotations

from enum import Enum


class ProposalStatus(str, Enum):
    PENDING = "pending"
    AWAITING_HUMAN = "awaiting_human"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"
    EXECUTED = "executed"
    BLOCKED = "blocked"
