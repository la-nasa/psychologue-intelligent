"""phq9: assessments, reminders, and assessment-sourced alerts

Revision ID: 0007_phq9
Revises: 0006_goals
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_phq9"
down_revision: str | None = "0006_goals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("phq9_assessments", "assessment_reminders")
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
        "phq9_assessments",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("instrument_version", sa.String(16), nullable=False),
        sa.Column("answers_enc", sa.Text, nullable=False),
        sa.Column("total_score", sa.Integer, nullable=False),
        sa.Column("item9_score", sa.Integer, nullable=False),
        sa.Column("completed_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("total_score BETWEEN 0 AND 27", name="ck_phq9_total"),
        sa.CheckConstraint("item9_score BETWEEN 0 AND 3", name="ck_phq9_item9"),
    )
    op.create_index("ix_phq9_user_time", "phq9_assessments", ["user_id", "completed_at"])

    op.create_table(
        "assessment_reminders",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("instrument", sa.String(16), nullable=False, server_default="PHQ-9"),
        sa.Column("due_at", ts(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('PENDING','SENT','DONE','CANCELLED')", name="ck_reminder_status"),
    )
    op.create_index("ix_reminder_due", "assessment_reminders", ["status", "due_at"])

    # Les alertes peuvent désormais provenir d'un message OU d'une auto-évaluation.
    op.add_column("alerts", sa.Column("source", sa.String(12), nullable=False, server_default="MESSAGE"))
    op.add_column("alerts", sa.Column("assessment_id", uid(), nullable=True))
    op.create_foreign_key("fk_alerts_assessment", "alerts", "phq9_assessments", ["assessment_id"], ["id"])
    op.alter_column("alerts", "crisis_event_id", nullable=True)
    op.create_check_constraint("ck_alert_source", "alerts", "source IN ('MESSAGE','ASSESSMENT')")
    op.create_check_constraint(
        "ck_alert_has_trigger", "alerts", "(crisis_event_id IS NOT NULL) OR (assessment_id IS NOT NULL)"
    )

    for table in _RLS_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    op.drop_constraint("ck_alert_has_trigger", "alerts", type_="check")
    op.drop_constraint("ck_alert_source", "alerts", type_="check")
    op.alter_column("alerts", "crisis_event_id", nullable=False)
    op.drop_constraint("fk_alerts_assessment", "alerts", type_="foreignkey")
    op.drop_column("alerts", "assessment_id")
    op.drop_column("alerts", "source")

    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.drop_table("assessment_reminders")
    op.drop_table("phq9_assessments")
