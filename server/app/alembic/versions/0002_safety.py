"""safety engine: risk -> crisis -> alert -> notification

Revision ID: 0002_safety
Revises: 0001_foundation
Create Date: 2026-08-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_safety"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("risk_assessments", "crisis_events", "alerts", "alert_actions", "notifications")
_MATCH = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR organization_id::text = current_setting('app.current_organization', true)"
)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_tenant ON {table} FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})")


def upgrade() -> None:
    ts = lambda: postgresql.TIMESTAMP(timezone=True)  # noqa: E731
    uid = lambda: postgresql.UUID(as_uuid=True)  # noqa: E731

    op.create_table(
        "risk_assessments",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("input_reference", sa.String(64), nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("model_available", sa.Boolean, nullable=False),
        sa.Column("emotion_label", sa.String(40), nullable=True),
        sa.Column("emotion_confidence", sa.Float, nullable=True),
        sa.Column("emotion_model_version", sa.String(80), nullable=True),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="ck_risk_score"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_risk_confidence"),
    )
    op.create_index("ix_risk_patient", "risk_assessments", ["patient_id", "created_at"])

    op.create_table(
        "crisis_events",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("risk_assessment_id", uid(), sa.ForeignKey("risk_assessments.id"), nullable=False),
        sa.Column("patient_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("reasons", sa.Text, nullable=False),
        sa.Column("rules_version", sa.String(40), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("level IN ('GREEN','ORANGE','RED')", name="ck_crisis_level"),
    )
    op.create_index("ix_crisis_patient", "crisis_events", ["patient_id", "created_at"])

    op.create_table(
        "alerts",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("crisis_event_id", uid(), sa.ForeignKey("crisis_events.id"), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("sla_due_at", ts(), nullable=True),
        sa.Column("assigned_clinician_id", uid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("acknowledged_at", ts(), nullable=True),
        sa.CheckConstraint("level IN ('ORANGE','RED')", name="ck_alert_level"),
        sa.CheckConstraint(
            "status IN ('OPEN','ACKNOWLEDGED','IN_REVIEW','ESCALATED','RESOLVED','CLOSED','CANCELLED')",
            name="ck_alert_status",
        ),
    )
    op.create_index("ix_alerts_status", "alerts", ["organization_id", "status", "level", "created_at"])
    op.create_index("ix_alerts_assignee", "alerts", ["assigned_clinician_id", "status"])

    op.create_table(
        "alert_actions",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("alert_id", uid(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("actor_id", uid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("justification", sa.Text, nullable=True),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_alert_actions_alert", "alert_actions", ["alert_id", "created_at"])

    op.create_table(
        "notifications",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("alert_id", uid(), sa.ForeignKey("alerts.id"), nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("template_version", sa.String(40), nullable=False),
        sa.Column("delivery_status", sa.String(24), nullable=False),
        sa.Column("provider_ref", sa.String(128), nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("next_retry_at", ts(), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False, unique=True),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "delivery_status IN ('PENDING','SENT','FAILED','SKIPPED_NO_CHANNEL')", name="ck_notification_status"
        ),
    )
    op.create_index("ix_notifications_alert", "notifications", ["alert_id", "channel"])
    op.create_index("ix_notifications_retry", "notifications", ["delivery_status", "next_retry_at"])

    for table in _RLS_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.drop_table("notifications")
    op.drop_table("alert_actions")
    op.drop_table("alerts")
    op.drop_table("crisis_events")
    op.drop_table("risk_assessments")
