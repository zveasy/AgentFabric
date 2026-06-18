"""Tenant profitability reporting."""

from __future__ import annotations

from .margin_analyzer import MarginAnalyzer


class TenantProfitability:
    def __init__(self, analyzer: MarginAnalyzer) -> None:
        self.analyzer = analyzer

    def report(self, tenant_id: str) -> dict[str, object]:
        economics = self.analyzer.tenant_margin(tenant_id)
        return economics.as_dict()
