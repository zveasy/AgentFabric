"""Build worker capability declaration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerManifest:
    worker_id: str
    capability: str
    allowed_repository_types: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    required_approval: bool = True
    quality_gates: tuple[str, ...] = ()

    def validate(self) -> None:
        if not all((self.worker_id, self.capability, self.allowed_repository_types, self.allowed_domains)):
            raise ValueError("build worker manifest is incomplete")

    def as_dict(self) -> dict[str, object]:
        return {
            "worker_id": self.worker_id,
            "capability": self.capability,
            "allowed_repository_types": list(self.allowed_repository_types),
            "allowed_domains": list(self.allowed_domains),
            "required_approval": self.required_approval,
            "quality_gates": list(self.quality_gates),
        }
