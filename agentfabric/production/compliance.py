"""Enterprise compliance and legal workflows."""

from __future__ import annotations

import json
from pathlib import Path

from agentfabric.production.store import ProductionStore


class ComplianceService:
    """GDPR-style deletion workflows and SIEM export."""

    def __init__(self, store: ProductionStore) -> None:
        self._store = store

    def request_deletion(self, tenant_id: str, user_id: str | None, reason: str) -> str:
        return self._store.create_deletion_request(tenant_id=tenant_id, user_id=user_id, reason=reason)

    def process_pending_deletions(self) -> list[str]:
        processed: list[str] = []
        for request in self._store.pending_deletion_requests():
            self._store.execute_deletion_request(request["request_id"])
            processed.append(request["request_id"])
        return processed

    def export_audit_for_siem(self, output_file: str) -> str:
        target = Path(output_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        events = self._store.audit_events()
        with target.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, sort_keys=True) + "\n")
        return str(target)


class LegalPolicyService:
    """Tracks legal documents (ToS/privacy) and user acceptance."""

    def __init__(self, store: ProductionStore) -> None:
        self._store = store

    def publish_document(self, doc_type: str, version: str, content: str) -> None:
        self._store.set_legal_document(doc_type, version, content)

    def current_document(self, doc_type: str) -> dict[str, str]:
        return self._store.get_legal_document(doc_type)

    def accept(self, doc_type: str, principal_id: str) -> dict[str, str]:
        doc = self._store.get_legal_document(doc_type)
        self._store.accept_legal_document(doc_type=doc_type, version=doc["version"], principal_id=principal_id)
        return doc
