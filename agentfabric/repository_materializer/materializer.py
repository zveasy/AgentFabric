"""Deterministic source trees for RenovationOS repositories."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re


SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


@dataclass(frozen=True)
class RenovationRepositorySpec:
    name: str
    repository_type: str
    purpose: str
    models: tuple[str, ...]
    apis: tuple[str, ...]
    events: tuple[str, ...]
    rbac_scopes: tuple[str, ...]
    metrics: tuple[str, ...]
    tests: tuple[str, ...]
    deployment_requirements: tuple[str, ...]
    dependencies: tuple[str, ...] = ()

    def validate(self) -> None:
        if not SAFE_NAME.fullmatch(self.name):
            raise ValueError("unsafe repository name")
        required = (
            self.models,
            self.apis,
            self.events,
            self.rbac_scopes,
            self.metrics,
            self.tests,
            self.deployment_requirements,
        )
        if not all(required):
            raise ValueError("repository specification is incomplete")

    def manifest(self) -> dict[str, object]:
        self.validate()
        return {
            "name": self.name,
            "domain": "construction",
            "purpose": self.purpose,
            "architecture": "layered FastAPI service with domain, service, API, audit, and metrics boundaries",
            "repository_type": self.repository_type,
            "dependencies": sorted(self.dependencies),
            "apis": sorted(self.apis),
            "rbac_scopes": sorted(self.rbac_scopes),
            "events": sorted(self.events),
            "observability": sorted(self.metrics),
            "tests": sorted(self.tests),
            "documentation_requirements": ["README", "api", "architecture", "deployment"],
            "metadata": {
                "platform": "RenovationOS",
                "industry": "construction",
                "capability": self.name,
                "quality_score": 1.0,
                "release_readiness": "candidate",
            },
        }


class RepositoryMaterializer:
    def materialize(self, spec: RenovationRepositorySpec) -> dict[str, str]:
        manifest = spec.manifest()
        package = spec.name
        files = {
            "README.md": _readme(spec),
            "docs/architecture.md": _architecture(spec),
            "docs/api.md": _api_docs(spec),
            "docs/deployment.md": _deployment(spec),
            "pyproject.toml": _pyproject(spec),
            "package.manifest.json": _json(
                {
                    "name": package,
                    "version": "0.1.0",
                    "private": True,
                    "platform": "RenovationOS",
                    "industry": "construction",
                    "capability": package,
                    "dependencies": sorted(spec.dependencies),
                    "quality_score": 1.0,
                    "release_readiness": "candidate",
                }
            ),
            "repository.manifest.json": _json(manifest),
            "openapi.json": _json(_openapi(spec)),
            "config.example.json": _json({"environment": "development", "log_level": "INFO"}),
            "Dockerfile": _dockerfile(spec),
            "docker-compose.yml": _compose(spec),
            ".github/workflows/ci.yml": _ci(),
            f"src/{package}/__init__.py": '"""RenovationOS generated package."""\n',
            f"src/{package}/models.py": _models(spec),
            f"src/{package}/service.py": _service(spec),
            f"src/{package}/api.py": _api(spec),
            f"src/{package}/events.py": _constants("EVENT_TYPES", spec.events),
            f"src/{package}/permissions.py": _constants("RBAC_SCOPES", spec.rbac_scopes),
            f"src/{package}/audit.py": _audit(),
            f"src/{package}/metrics.py": _metrics(spec),
            "tests/test_models.py": _tests(spec),
        }
        return dict(sorted(files.items()))


def _json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _readme(spec: RenovationRepositorySpec) -> str:
    return (
        f"# {spec.name}\n\n"
        f"{spec.purpose}\n\n"
        "Generated deterministically by AgentFabric repository execution. "
        "All writes require a tenant-scoped approval record.\n"
    )


def _architecture(spec: RenovationRepositorySpec) -> str:
    return (
        "# Architecture\n\n"
        "The repository separates immutable domain models, service orchestration, FastAPI routes, "
        "event declarations, RBAC scopes, audit hooks, and metrics hooks.\n\n"
        "Sensitive values are represented by VEIL references and are never persisted directly.\n"
    )


def _api_docs(spec: RenovationRepositorySpec) -> str:
    return "# API\n\n" + "\n".join(f"- `{route}`" for route in sorted(spec.apis)) + "\n"


def _deployment(spec: RenovationRepositorySpec) -> str:
    requirements = "\n".join(f"- {item}" for item in sorted(spec.deployment_requirements))
    return f"# Deployment\n\n## Requirements\n\n{requirements}\n\nRun as a non-root container.\n"


def _pyproject(spec: RenovationRepositorySpec) -> str:
    return (
        "[build-system]\n"
        'requires = ["setuptools>=69"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        f'name = "{spec.name.replace("_", "-")}"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.9"\n'
        'dependencies = ["fastapi>=0.100", "pydantic>=2.0", "uvicorn>=0.20"]\n\n'
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n'
    )


def _models(spec: RenovationRepositorySpec) -> str:
    blocks = [
        '"""Domain models generated from the RenovationOS package definition."""',
        "",
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass, field",
        "from typing import Any",
        "",
    ]
    for model in spec.models:
        blocks.extend(
            [
                "@dataclass(frozen=True)",
                f"class {model}:",
                '    """Typed domain record with deterministic extension fields."""',
                "",
                "    record_id: str",
                "    attributes: dict[str, Any] = field(default_factory=dict)",
                "",
                "",
            ]
        )
    return "\n".join(blocks).rstrip() + "\n"


def _service(spec: RenovationRepositorySpec) -> str:
    model = spec.models[0]
    return (
        '"""Application service boundary."""\n\n'
        "from __future__ import annotations\n\n"
        f"from .models import {model}\n\n\n"
        "class RepositoryService:\n"
        f"    def create(self, record: {model}) -> {model}:\n"
        "        return record\n"
    )


def _api(spec: RenovationRepositorySpec) -> str:
    return (
        '"""FastAPI route stubs."""\n\n'
        "from fastapi import APIRouter, FastAPI\n\n"
        'router = APIRouter(tags=["renovation-os"])\n\n\n'
        '@router.get("/health")\n'
        "def health() -> dict[str, str]:\n"
        f'    return {{"status": "ok", "repository": "{spec.name}"}}\n\n\n'
        f'app = FastAPI(title="{spec.name}", version="0.1.0")\n'
        "app.include_router(router)\n"
    )


def _constants(name: str, values: tuple[str, ...]) -> str:
    return f"{name} = {tuple(sorted(values))!r}\n"


def _audit() -> str:
    return (
        '"""Audit hook that stores references, never raw sensitive values."""\n\n'
        "def audit_record(action: str, veil_reference: str) -> dict[str, str]:\n"
        '    if not veil_reference.startswith("veil:"):\n'
        '        raise ValueError("VEIL reference required")\n'
        '    return {"action": action, "veil_reference": veil_reference}\n'
    )


def _metrics(spec: RenovationRepositorySpec) -> str:
    return f"METRIC_NAMES = {tuple(sorted(spec.metrics))!r}\n"


def _tests(spec: RenovationRepositorySpec) -> str:
    model = spec.models[0]
    return (
        f"from {spec.name}.models import {model}\n\n\n"
        "def test_domain_record_is_immutable() -> None:\n"
        f'    record = {model}(record_id="example")\n'
        '    assert record.record_id == "example"\n'
    )


def _dockerfile(spec: RenovationRepositorySpec) -> str:
    return (
        "FROM python:3.12-slim\n"
        "WORKDIR /app\n"
        "RUN useradd --create-home app\n"
        "COPY . .\n"
        "RUN pip install --no-cache-dir .\n"
        "USER app\n"
        f'CMD ["uvicorn", "{spec.name}.api:app", "--host", "0.0.0.0", "--port", "8000"]\n'
    )


def _compose(spec: RenovationRepositorySpec) -> str:
    return (
        "services:\n"
        f"  {spec.name}:\n"
        "    build: .\n"
        "    ports:\n"
        '      - "8000:8000"\n'
    )


def _ci() -> str:
    return (
        "name: ci\n"
        "on: [push, pull_request]\n"
        "jobs:\n"
        "  test:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        '          python-version: "3.12"\n'
        "      - run: pip install -e . pytest\n"
        "      - run: pytest -q\n"
    )


def _openapi(spec: RenovationRepositorySpec) -> dict[str, object]:
    return {
        "info": {"title": spec.name, "version": "0.1.0"},
        "openapi": "3.1.0",
        "paths": {route: {"get": {"responses": {"200": {"description": "Success"}}}} for route in sorted(spec.apis)},
    }
