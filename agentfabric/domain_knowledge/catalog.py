"""Versioned domain knowledge packs."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


KNOWLEDGE_DOMAINS = {"construction", "treasury", "trust", "energy", "manufacturing", "aerospace"}


@dataclass(frozen=True)
class DomainKnowledgePack:
    domain: str
    version: str
    terminology: tuple[str, ...]
    entities: tuple[str, ...]
    workflows: tuple[str, ...]
    metrics: tuple[str, ...]
    common_apis: tuple[str, ...]
    compliance_references: tuple[str, ...]

    @property
    def pack_id(self) -> str:
        return f"knowledge-{sha256(self.export_json().encode()).hexdigest()[:16]}"

    def as_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "version": self.version,
            "terminology": sorted(self.terminology),
            "entities": sorted(self.entities),
            "workflows": sorted(self.workflows),
            "metrics": sorted(self.metrics),
            "common_apis": sorted(self.common_apis),
            "compliance_references": sorted(self.compliance_references),
        }

    def export_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


class DomainKnowledgeCatalog:
    def __init__(self) -> None:
        self._packs = {domain: _pack(domain) for domain in sorted(KNOWLEDGE_DOMAINS)}

    def get(self, domain: str) -> DomainKnowledgePack:
        try:
            return self._packs[domain]
        except KeyError as exc:
            raise KeyError(f"knowledge pack not found: {domain}") from exc

    def list(self) -> list[DomainKnowledgePack]:
        return [self._packs[key] for key in sorted(self._packs)]


def _pack(domain: str) -> DomainKnowledgePack:
    return DomainKnowledgePack(
        domain=domain,
        version="1.0.0",
        terminology=(f"{domain}_resource", "evidence", "approval"),
        entities=(f"{domain.title()}Account", f"{domain.title()}Record", "Tenant"),
        workflows=("create", "review", "approve", "archive"),
        metrics=("latency", "quality", "cost", "compliance"),
        common_apis=(f"/{domain}/resources", f"/{domain}/reports"),
        compliance_references=("tenant_isolation", "audit_integrity", "VEIL_boundary"),
    )
