"""Ticket intelligence over sanitized connector results."""

from __future__ import annotations

from .summary_service import SummaryService


class TicketIntelligence:
    def analyze(self, payload: dict[str, object]) -> dict[str, object]:
        summary = SummaryService().summarize(payload, subject="ticket")
        return {**summary, "ticket_priority": "medium", "recommended_action": "route for review"}
