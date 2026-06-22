"""Repository type templates."""

from __future__ import annotations

from copy import deepcopy


PROJECT_TEMPLATES = {
    "service": {"architecture": "layered-service", "structure": ("src/", "tests/", "docs/", "deploy/")},
    "library": {"architecture": "modular-library", "structure": ("src/", "tests/", "docs/")},
    "frontend": {"architecture": "component-frontend", "structure": ("src/", "public/", "tests/", "docs/")},
    "cli": {"architecture": "command-application", "structure": ("src/", "tests/", "docs/")},
    "edge": {"architecture": "event-driven-edge", "structure": ("src/", "tests/", "deploy/", "docs/")},
    "infrastructure": {"architecture": "declarative-infrastructure", "structure": ("modules/", "environments/", "tests/", "docs/")},
    "ai_agent": {"architecture": "policy-gated-agent", "structure": ("agent/", "tools/", "tests/", "docs/")},
    "domain_platform": {"architecture": "modular-domain-platform", "structure": ("services/", "packages/", "apps/", "tests/", "docs/")},
}


def project_template(repository_type: str) -> dict[str, object]:
    try:
        return deepcopy(PROJECT_TEMPLATES[repository_type])
    except KeyError as exc:
        raise ValueError(f"unsupported repository type: {repository_type}") from exc
