"""personalization: goals + goal progress

Revision ID: 0006_goals
Revises: 0005_memory
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_goals"
down_revision: str | None = "0005_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("goals", "goal_progress")
_MATCH = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR organization_id::text = current_setting('app.current_organization', true)"
)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_tenant ON {table} FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})")


def upgrade() -> None:
    uid = lambda: postgresql.UUID(as_uuid=True)  # noqa: E731
    ts = lambda: postgresql.TIMESTAMP(timezone=True)  # noqa: E731

    op.create_table(
        "goals",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description_enc", sa.Text, nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('ACTIVE','ACHIEVED','PAUSED','DROPPED')", name="ck_goal_status"),
    )
    op.create_index("ix_goals_user", "goals", ["user_id", "status"])

    op.create_table(
        "goal_progress",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("goal_id", uid(), sa.ForeignKey("goals.id"), nullable=False),
        sa.Column("value", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("note_enc", sa.Text, nullable=True),
        sa.Column("recorded_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("value BETWEEN 0 AND 100", name="ck_goal_progress_value"),
    )
    op.create_index("ix_goal_progress_goal", "goal_progress", ["goal_id", "recorded_at"])

    for table in _RLS_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.drop_table("goal_progress")
    op.drop_table("goals")
