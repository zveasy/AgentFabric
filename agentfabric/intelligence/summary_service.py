"""Safe summary generation over sanitized inputs."""

from __future__ import annotations

from .safety import require_sanitized_input


class SummaryService:
    def summarize(self, payload: dict[str, object], *, subject: str = "content") -> dict[str, object]:
        require_sanitized_input(payload)
        sanitized = dict(payload.get("sanitized_payload", {})) if isinstance(payload.get("sanitized_payload"), dict) else {}
        token_refs = payload.get("veil_token_refs") or sanitized.get("veil_token_refs") or []
        return {
            "summary": f"Summary generated for {subject} from sanitized connector context.",
            "key_points": sorted(str(key) for key in sanitized.keys())[:5],
            "veil_token_refs": list(token_refs) if isinstance(token_refs, (list, tuple)) else [str(token_refs)],
            "classification": "internal",
        }
