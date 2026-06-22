"""Build worker output."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerResult:
    worker_id: str
    capability: str
    artifacts: dict[str, str]
    evidence: dict[str, object]

    def as_dict(self, include_contents: bool = False) -> dict[str, object]:
        value: dict[str, object] = {
            "worker_id": self.worker_id,
            "capability": self.capability,
            "artifact_paths": sorted(self.artifacts),
            "evidence": self.evidence,
        }
        if include_contents:
            value["artifacts"] = dict(sorted(self.artifacts.items()))
        return value
