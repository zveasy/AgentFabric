"""Package metadata and governance flags."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PackageMetadata:
    description: str = ""
    tags: tuple[str, ...] = ()
    private: bool = False
    enterprise_only: bool = False
    deprecated: bool = False
    revoked: bool = False
    high_risk_approved: bool = False
    approval_notes: str = ""
    category: str = "general"
    bundle_id: str | None = None
    compatibility: dict[str, str] = field(default_factory=dict)
    quality_score: float | None = None
    extra: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "description": self.description,
            "tags": list(self.tags),
            "private": self.private,
            "enterprise_only": self.enterprise_only,
            "deprecated": self.deprecated,
            "revoked": self.revoked,
            "high_risk_approved": self.high_risk_approved,
            "approval_notes": self.approval_notes,
            "category": self.category,
            "bundle_id": self.bundle_id,
            "compatibility": dict(self.compatibility),
            "quality_score": self.quality_score,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "PackageMetadata":
        return cls(
            description=str(value.get("description", "")),
            tags=tuple(str(item) for item in value.get("tags", ())),
            private=bool(value.get("private", False)),
            enterprise_only=bool(value.get("enterprise_only", False)),
            deprecated=bool(value.get("deprecated", False)),
            revoked=bool(value.get("revoked", False)),
            high_risk_approved=bool(value.get("high_risk_approved", False)),
            approval_notes=str(value.get("approval_notes", "")),
            category=str(value.get("category", "general")),
            bundle_id=str(value["bundle_id"]) if value.get("bundle_id") else None,
            compatibility={str(key): str(item) for key, item in dict(value.get("compatibility", {})).items()},
            quality_score=float(value["quality_score"]) if value.get("quality_score") is not None else None,
            extra=dict(value.get("extra", {})),
        )
