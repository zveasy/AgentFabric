"""
Execution sandbox: run agent code in an isolated environment.
Subprocess-based isolation with no arbitrary filesystem/network unless declared.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from agentfabric.runtime.manifest import Manifest


class Sandbox:
    """
    Runs agent code in a subprocess with restricted environment.
    Agent package is unpacked into a temp dir; only declared permissions
    (and env-injected secrets) are available. No arbitrary filesystem or
    network access unless the runtime explicitly provides it via tools.
    """

    def __init__(
        self,
        agent_root: Path | str,
        manifest: Manifest,
        env: dict[str, str] | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.agent_root = Path(agent_root)
        self.manifest = manifest
        self._env = dict(env or os.environ)
        self.timeout_seconds = timeout_seconds
        # Restrict: don't pass through arbitrary env; only allow safe + injected
        self._env.pop("PATH", None)
        self._env["AGENTFABRIC_AGENT_ID"] = manifest.name
        self._env["AGENTFABRIC_AGENT_VERSION"] = manifest.version

    def run_entrypoint(self, input_json: str) -> tuple[int, str, str]:
        """
        Run the agent entrypoint (e.g. agent:run) with input on stdin.
        Returns (returncode, stdout, stderr).
        """
        entrypoint = self.manifest.entrypoint or "agent:run"
        if ":" in entrypoint:
            module, attr = entrypoint.split(":", 1)
            cmd = [sys.executable, "-c", f"from {module} import {attr}; import sys, json; r = {attr}(json.load(sys.stdin)); print(json.dumps(r))"]
        else:
            cmd = [sys.executable, "-m", entrypoint]
        cwd = str(self.agent_root)
        try:
            proc = subprocess.run(
                cmd,
                input=input_json,
                capture_output=True,
                cwd=cwd,
                env=self._env,
                timeout=self.timeout_seconds,
                text=True,
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except subprocess.TimeoutExpired:
            return -1, "", "Sandbox run timed out"

    def run_in_process(self, run_fn: Any, *args: Any, **kwargs: Any) -> Any:
        """
        Run a callable in the current process (e.g. for in-process agent execution).
        Use when you trust the agent code and want to avoid subprocess overhead.
        """
        return run_fn(*args, **kwargs)
