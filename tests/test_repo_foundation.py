from __future__ import annotations

import importlib
import re
import unittest
from pathlib import Path

from veil_client import MockVeilClient, PolicyCheckRequest, SanitizeContextRequest, TokenIssueRequest


class RepoFoundationTests(unittest.TestCase):
    def test_roadmap_packages_are_importable(self) -> None:
        for package_name in (
            "runtime",
            "registry",
            "scheduler",
            "orchestration",
            "memory",
            "evaluations",
            "versioning",
            "marketplace",
            "connectors",
            "veil_client",
        ):
            module = importlib.import_module(package_name)
            self.assertIsNotNone(module)

    def test_veil_client_mock_exposes_required_operations(self) -> None:
        client = MockVeilClient()
        sanitized = client.sanitize_context(
            SanitizeContextRequest(agent_id="a1", tenant_id="t1", context={"message": "safe"})
        )
        self.assertEqual(sanitized.sanitized_context["message"], "safe")
        self.assertTrue(client.check_policy(PolicyCheckRequest(agent_id="a1", action="run")).allowed)
        token = client.issue_agent_token(TokenIssueRequest(agent_id="a1"))
        self.assertIn("mock-token:a1", token.token)

    def test_no_module_imports_veil_directly_outside_client_boundary(self) -> None:
        repo_root = Path(__file__).resolve().parent.parent
        violations: list[str] = []
        direct_import_pattern = re.compile(r"(^|\n)\s*(import\s+veil\b|from\s+veil(?:\s+import|\.)\b)")
        source_roots = (
            "agentfabric",
            "runtime",
            "registry",
            "scheduler",
            "orchestration",
            "memory",
            "evaluations",
            "versioning",
            "marketplace",
            "connectors",
            "tests",
        )
        for root_name in source_roots:
            root = repo_root / root_name
            for path in root.rglob("*.py"):
                normalized = path.relative_to(repo_root).as_posix()
                content = path.read_text(encoding="utf-8")
                if direct_import_pattern.search(content):
                    violations.append(normalized)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
