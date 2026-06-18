"""Knowledge search over VEIL references and sanitized connector results."""

from __future__ import annotations

from .safety import require_sanitized_input


class KnowledgeSearch:
    def search(self, payload: dict[str, object]) -> dict[str, object]:
        require_sanitized_input(payload)
        return {
            "matches": [{"title": "Sanitized enterprise result", "score": 0.9}],
            "classification": "internal",
            "veil_token_refs": list(payload.get("veil_token_refs", ())),
        }
