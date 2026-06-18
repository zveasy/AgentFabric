"""Code repository intelligence over sanitized connector results."""

from __future__ import annotations

from .summary_service import SummaryService


class CodeIntelligence:
    def review(self, payload: dict[str, object]) -> dict[str, object]:
        summary = SummaryService().summarize(payload, subject="code repository")
        return {**summary, "review_findings": ["no raw secrets present in sanitized input"]}
