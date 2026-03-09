"""add agent project collaboration schema

Revision ID: 0003_agent_projects
Revises: 0002_reviews_role
Create Date: 2026-03-08 02:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_agent_projects"
down_revision = "0002_reviews_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("default_branch", sa.String(length=64), nullable=False, server_default="main"),
        sa.Column("contribution_zones_csv", sa.Text(), nullable=False, server_default=""),
        sa.Column("merge_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("namespace", "project_id", name="uq_agent_project_namespace_project"),
    )
    op.create_index("ix_agent_projects_namespace", "agent_projects", ["namespace"])
    op.create_index("ix_agent_projects_project_id", "agent_projects", ["project_id"])
    op.create_index("ix_agent_projects_created_by", "agent_projects", ["created_by"])
    op.create_index("ix_agent_projects_created_at", "agent_projects", ["created_at"])

    op.create_table(
        "project_maintainers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_ref_id", sa.Integer(), sa.ForeignKey("agent_projects.id"), nullable=False),
        sa.Column("principal_id", sa.String(length=128), nullable=False),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_ref_id", "principal_id", name="uq_project_maintainer"),
    )
    op.create_index("ix_project_maintainers_project_ref_id", "project_maintainers", ["project_ref_id"])
    op.create_index("ix_project_maintainers_principal_id", "project_maintainers", ["principal_id"])
    op.create_index("ix_project_maintainers_added_at", "project_maintainers", ["added_at"])

    op.create_table(
        "project_branches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_ref_id", sa.Integer(), sa.ForeignKey("agent_projects.id"), nullable=False),
        sa.Column("branch_name", sa.String(length=128), nullable=False),
        sa.Column("base_ref", sa.String(length=128), nullable=False, server_default="main"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_ref_id", "branch_name", name="uq_project_branch_name"),
    )
    op.create_index("ix_project_branches_project_ref_id", "project_branches", ["project_ref_id"])
    op.create_index("ix_project_branches_branch_name", "project_branches", ["branch_name"])
    op.create_index("ix_project_branches_status", "project_branches", ["status"])
    op.create_index("ix_project_branches_created_by", "project_branches", ["created_by"])
    op.create_index("ix_project_branches_created_at", "project_branches", ["created_at"])

    op.create_table(
        "project_contributions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_ref_id", sa.Integer(), sa.ForeignKey("agent_projects.id"), nullable=False),
        sa.Column("branch_name", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("contribution_zone", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metrics_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("regressions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("evaluation_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("submitter_id", sa.String(length=128), nullable=False),
        sa.Column("reviewer_id", sa.String(length=128), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("merged_release_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_project_contributions_project_ref_id", "project_contributions", ["project_ref_id"])
    op.create_index("ix_project_contributions_branch_name", "project_contributions", ["branch_name"])
    op.create_index("ix_project_contributions_contribution_zone", "project_contributions", ["contribution_zone"])
    op.create_index("ix_project_contributions_status", "project_contributions", ["status"])
    op.create_index("ix_project_contributions_submitter_id", "project_contributions", ["submitter_id"])
    op.create_index("ix_project_contributions_created_at", "project_contributions", ["created_at"])

    op.create_table(
        "project_releases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_ref_id", sa.Integer(), sa.ForeignKey("agent_projects.id"), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("source_branch", sa.String(length=128), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_ref_id", "version", "channel", name="uq_project_release"),
    )
    op.create_index("ix_project_releases_project_ref_id", "project_releases", ["project_ref_id"])
    op.create_index("ix_project_releases_version", "project_releases", ["version"])
    op.create_index("ix_project_releases_channel", "project_releases", ["channel"])
    op.create_index("ix_project_releases_created_by", "project_releases", ["created_by"])
    op.create_index("ix_project_releases_created_at", "project_releases", ["created_at"])


def downgrade() -> None:
    op.drop_table("project_releases")
    op.drop_table("project_contributions")
    op.drop_table("project_branches")
    op.drop_table("project_maintainers")
    op.drop_table("agent_projects")
