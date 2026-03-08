"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-08 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "principals",
        sa.Column("principal_id", sa.String(length=128), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("principal_type", sa.String(length=32), nullable=False),
        sa.Column("scopes_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tokens",
        sa.Column("token_id", sa.String(length=64), primary_key=True),
        sa.Column("principal_id", sa.String(length=128), sa.ForeignKey("principals.principal_id"), nullable=False),
        sa.Column("token_hash", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tokens_principal_id", "tokens", ["principal_id"])
    op.create_index("ix_tokens_expires_at", "tokens", ["expires_at"])
    op.create_index("ix_tokens_token_hash", "tokens", ["token_hash"])

    op.create_table(
        "packages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("package_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("permissions_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("payload_digest", sa.String(length=128), nullable=False),
        sa.Column("signature", sa.Text(), nullable=False),
        sa.Column("sbom_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("namespace", "package_id", "version", name="uq_package_version"),
    )
    op.create_index("ix_packages_namespace", "packages", ["namespace"])
    op.create_index("ix_packages_package_id", "packages", ["package_id"])
    op.create_index("ix_packages_version", "packages", ["version"])
    op.create_index("ix_packages_category", "packages", ["category"])
    op.create_index("ix_packages_created_at", "packages", ["created_at"])

    op.create_table(
        "installs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("package_fqid", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_installs_tenant_id", "installs", ["tenant_id"])
    op.create_index("ix_installs_user_id", "installs", ["user_id"])
    op.create_index("ix_installs_package_fqid", "installs", ["package_fqid"])

    op.create_table(
        "billing_events",
        sa.Column("idempotency_key", sa.String(length=256), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("package_fqid", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_billing_events_tenant_id", "billing_events", ["tenant_id"])
    op.create_index("ix_billing_events_event_type", "billing_events", ["event_type"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("subtotal", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_invoice_lines_tenant_id", "invoice_lines", ["tenant_id"])

    op.create_table(
        "queue_messages",
        sa.Column("message_id", sa.String(length=64), primary_key=True),
        sa.Column("queue_name", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_queue_messages_queue_name", "queue_messages", ["queue_name"])
    op.create_index("ix_queue_messages_status", "queue_messages", ["status"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("target", sa.String(length=256), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("previous_hash", sa.String(length=128), nullable=False),
        sa.Column("event_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])

    op.create_table(
        "payment_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_txn_id", sa.String(length=256), nullable=False, unique=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("idempotency_key", sa.String(length=256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_records_tenant_id", "payment_records", ["tenant_id"])
    op.create_index("ix_payment_records_provider", "payment_records", ["provider"])
    op.create_index("ix_payment_records_created_at", "payment_records", ["created_at"])


def downgrade() -> None:
    op.drop_table("payment_records")
    op.drop_table("audit_events")
    op.drop_table("queue_messages")
    op.drop_table("invoice_lines")
    op.drop_table("billing_events")
    op.drop_table("installs")
    op.drop_table("packages")
    op.drop_table("tokens")
    op.drop_table("principals")
