"""Release validation suite for production readiness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)


def main() -> int:
    commands = [
        ["ruff", "check", "."],
        ["pytest", "-q"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "scripts/export_openapi.py"],
        [sys.executable, "-m", "pytest", "-q", "tests/test_generation10_release.py"],
    ]
    for command in commands:
        run(command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
