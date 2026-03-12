"""queue and payment hardening

Revision ID: 0002_queue_payment_hardening
Revises: 0001_initial_schema
Create Date: 2026-03-08 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_queue_payment_hardening"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "queue_messages",
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "payment_records",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "payment_records",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_payment_records_status", "payment_records", ["status"])
    op.create_index("ix_payment_records_updated_at", "payment_records", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_payment_records_updated_at", table_name="payment_records")
    op.drop_index("ix_payment_records_status", table_name="payment_records")
    op.drop_column("payment_records", "updated_at")
    op.drop_column("payment_records", "status")
    op.drop_column("queue_messages", "last_error")
