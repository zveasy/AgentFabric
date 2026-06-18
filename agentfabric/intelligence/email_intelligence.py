"""Email intelligence over sanitized connector results."""

from __future__ import annotations

from .summary_service import SummaryService


class EmailIntelligence:
    def analyze(self, payload: dict[str, object]) -> dict[str, object]:
        summary = SummaryService().summarize(payload, subject="email")
        return {**summary, "email_intent": "information_request"}
