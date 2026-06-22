"""Deterministic package structure builders."""

from __future__ import annotations

from .project_templates import project_template


def build_package_structure(repository_type: str, name: str) -> tuple[str, ...]:
    template = project_template(repository_type)
    root = name.replace("-", "_").lower()
    return tuple(f"{root}/{item}" for item in template["structure"])
