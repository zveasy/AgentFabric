"""merge alembic heads

Revision ID: 0003_merge_heads
Revises: 0002_reviews_role, 0002_queue_payment_hardening
Create Date: 2026-03-08 02:00:00.000000
"""

from __future__ import annotations


revision = "0003_merge_heads"
down_revision = ("0002_reviews_role", "0002_queue_payment_hardening")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
