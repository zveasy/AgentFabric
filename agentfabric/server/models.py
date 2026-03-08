"""SQLAlchemy ORM models for Postgres-backed services."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agentfabric.server.database import Base


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class Principal(Base):
    __tablename__ = "principals"

    principal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    principal_type: Mapped[str] = mapped_column(String(32), default="user")
    role: Mapped[str] = mapped_column(String(32), default="viewer", index=True)
    scopes_csv: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    tokens: Mapped[list["Token"]] = relationship(back_populates="principal")


class Token(Base):
    __tablename__ = "tokens"

    token_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    principal_id: Mapped[str] = mapped_column(ForeignKey("principals.principal_id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    principal: Mapped[Principal] = relationship(back_populates="tokens")


class Package(Base):
    __tablename__ = "packages"
    __table_args__ = (
        UniqueConstraint("namespace", "package_id", "version", name="uq_package_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    namespace: Mapped[str] = mapped_column(String(128), index=True)
    package_id: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(128), index=True)
    permissions_csv: Mapped[str] = mapped_column(Text, default="")
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    signature: Mapped[str] = mapped_column(Text, nullable=False)
    sbom_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class Install(Base):
    __tablename__ = "installs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    package_fqid: Mapped[str] = mapped_column(String(512), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BillingEvent(Base):
    __tablename__ = "billing_events"

    idempotency_key: Mapped[str] = mapped_column(String(256), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    actor_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    package_fqid: Mapped[str] = mapped_column(String(512), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class QueueMessage(Base):
    __tablename__ = "queue_messages"

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid4().hex)
    queue_name: Mapped[str] = mapped_column(String(128), index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(128), index=True)
    target: Mapped[str] = mapped_column(String(256), index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    previous_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    event_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    provider_txn_id: Mapped[str] = mapped_column(String(256), unique=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    idempotency_key: Mapped[str] = mapped_column(String(256), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class PackageReview(Base):
    __tablename__ = "package_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    package_fqid: Mapped[str] = mapped_column(String(512), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    review_text: Mapped[str] = mapped_column(Text, default="")
    moderated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class AgentProject(Base):
    __tablename__ = "agent_projects"
    __table_args__ = (
        UniqueConstraint("namespace", "project_id", name="uq_agent_project_namespace_project"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    namespace: Mapped[str] = mapped_column(String(128), index=True)
    project_id: Mapped[str] = mapped_column(String(128), index=True)
    display_name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    default_branch: Mapped[str] = mapped_column(String(64), default="main")
    contribution_zones_csv: Mapped[str] = mapped_column(Text, default="")
    merge_policy_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    maintainers: Mapped[list["ProjectMaintainer"]] = relationship(back_populates="project")
    branches: Mapped[list["ProjectBranch"]] = relationship(back_populates="project")
    contributions: Mapped[list["ProjectContribution"]] = relationship(back_populates="project")
    releases: Mapped[list["ProjectRelease"]] = relationship(back_populates="project")


class ProjectMaintainer(Base):
    __tablename__ = "project_maintainers"
    __table_args__ = (
        UniqueConstraint("project_ref_id", "principal_id", name="uq_project_maintainer"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_ref_id: Mapped[int] = mapped_column(ForeignKey("agent_projects.id"), index=True)
    principal_id: Mapped[str] = mapped_column(String(128), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    project: Mapped[AgentProject] = relationship(back_populates="maintainers")


class ProjectBranch(Base):
    __tablename__ = "project_branches"
    __table_args__ = (
        UniqueConstraint("project_ref_id", "branch_name", name="uq_project_branch_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_ref_id: Mapped[int] = mapped_column(ForeignKey("agent_projects.id"), index=True)
    branch_name: Mapped[str] = mapped_column(String(128), index=True)
    base_ref: Mapped[str] = mapped_column(String(128), default="main")
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    created_by: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    project: Mapped[AgentProject] = relationship(back_populates="branches")


class ProjectContribution(Base):
    __tablename__ = "project_contributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_ref_id: Mapped[int] = mapped_column(ForeignKey("agent_projects.id"), index=True)
    branch_name: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(256))
    summary: Mapped[str] = mapped_column(Text, default="")
    contribution_zone: Mapped[str] = mapped_column(String(64), index=True)
    manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    regressions_json: Mapped[str] = mapped_column(Text, default="{}")
    evaluation_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    submitter_id: Mapped[str] = mapped_column(String(128), index=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_notes: Mapped[str] = mapped_column(Text, default="")
    merged_release_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[AgentProject] = relationship(back_populates="contributions")


class ProjectRelease(Base):
    __tablename__ = "project_releases"
    __table_args__ = (
        UniqueConstraint("project_ref_id", "version", "channel", name="uq_project_release"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_ref_id: Mapped[int] = mapped_column(ForeignKey("agent_projects.id"), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)
    source_branch: Mapped[str] = mapped_column(String(128))
    changelog: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    project: Mapped[AgentProject] = relationship(back_populates="releases")
