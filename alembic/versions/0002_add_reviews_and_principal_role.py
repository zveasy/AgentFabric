"""add package_reviews and principal role

Revision ID: 0002_reviews_role
Revises: 0001_initial_schema
Create Date: 2026-03-08 01:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_reviews_role"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("principals", sa.Column("role", sa.String(length=32), nullable=False, server_default="viewer"))
    op.create_index("ix_principals_role", "principals", ["role"])

    op.create_table(
        "package_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("package_fqid", sa.String(length=512), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("review_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("moderated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_package_reviews_tenant_id", "package_reviews", ["tenant_id"])
    op.create_index("ix_package_reviews_package_fqid", "package_reviews", ["package_fqid"])
    op.create_index("ix_package_reviews_user_id", "package_reviews", ["user_id"])
    op.create_index("ix_package_reviews_created_at", "package_reviews", ["created_at"])


def downgrade() -> None:
    op.drop_table("package_reviews")
    op.drop_index("ix_principals_role", table_name="principals")
    op.drop_column("principals", "role")
