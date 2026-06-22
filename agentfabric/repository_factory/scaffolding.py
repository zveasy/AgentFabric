"""Deterministic repository scaffolding."""

from __future__ import annotations

from .repository_blueprints import RepositoryBlueprint
from .repository_metadata import RepositoryManifest


class RepositoryScaffolder:
    def scaffold(self, manifest: RepositoryManifest) -> RepositoryBlueprint:
        files = {
            "README.md": f"# {manifest.name}\n\n{manifest.purpose}\n",
            "ARCHITECTURE.md": f"# Architecture\n\n{manifest.architecture}\n",
            "repository.manifest.json": manifest.export_json() + "\n",
            "tests/test_smoke.py": "def test_repository_smoke():\n    assert True\n",
        }
        for path in manifest.package_structure:
            files[f"{path.rstrip('/')}/.gitkeep"] = ""
        return RepositoryBlueprint(
            blueprint_id=f"blueprint-{manifest.repository_id.removeprefix('repo-')}",
            manifest=manifest,
            files=files,
        )
