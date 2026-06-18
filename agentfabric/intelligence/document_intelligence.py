"""Document intelligence over sanitized connector results."""

from __future__ import annotations

from .summary_service import SummaryService


class DocumentIntelligence:
    def analyze(self, payload: dict[str, object]) -> dict[str, object]:
        summary = SummaryService().summarize(payload, subject="document")
        return {**summary, "document_findings": ["obligations identified from sanitized references"]}
