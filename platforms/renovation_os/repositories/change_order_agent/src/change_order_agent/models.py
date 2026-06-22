"""Typed change-order domain models."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ScopeDelta:
    description: str


@dataclass(frozen=True)
class CostDelta:
    amount: float


@dataclass(frozen=True)
class ScheduleDelta:
    days: int


@dataclass(frozen=True)
class ApprovalStatus:
    value: str


@dataclass(frozen=True)
class CustomerApproval:
    approver: str
    approved: bool


@dataclass(frozen=True)
class ContractorAcknowledgement:
    contractor: str


@dataclass(frozen=True)
class ChangeOrderAuditRecord:
    action: str
    actor: str
    previous_status: str
    new_status: str


@dataclass
class ChangeOrder:
    change_order_id: str
    scope: ScopeDelta
    cost: CostDelta
    schedule: ScheduleDelta
    status: str = "draft"
    customer_approval: CustomerApproval | None = None
    contractor_acknowledgement: ContractorAcknowledgement | None = None
    audit_records: list[ChangeOrderAuditRecord] = field(default_factory=list)

    def export(self) -> dict[str, object]:
        return asdict(self)
