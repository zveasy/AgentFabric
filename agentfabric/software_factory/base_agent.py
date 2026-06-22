"""Base deterministic software generation agent."""

from __future__ import annotations

from .artifacts import FactoryArtifact


class SoftwareStageAgent:
    stage = "unknown"

    def run(
        self,
        repository_id: str,
        inputs: dict[str, object],
        *,
        signer: str,
    ) -> FactoryArtifact:
        if not inputs:
            raise ValueError(f"{self.stage} stage requires inputs")
        return FactoryArtifact.create(
            self.stage,
            repository_id,
            {
                "stage": self.stage,
                "inputs_digest": _digest(inputs),
                "outputs": self.outputs(inputs),
            },
            signer,
        )

    def outputs(self, inputs: dict[str, object]) -> dict[str, object]:
        return {"status": "complete", "source_keys": sorted(inputs)}


def _digest(value: dict[str, object]) -> str:
    import hashlib
    import json

    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
