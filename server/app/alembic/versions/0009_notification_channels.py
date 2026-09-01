"""notifications: per-org channels + delivery target on notification rows

Revision ID: 0009_notification_channels
Revises: 0008_alert_lifecycle
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_notification_channels"
down_revision: str | None = "0008_alert_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MATCH = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR organization_id::text = current_setting('app.current_organization', true)"
)


def upgrade() -> None:
    uid = lambda: postgresql.UUID(as_uuid=True)  # noqa: E731
    ts = lambda: postgresql.TIMESTAMP(timezone=True)  # noqa: E731

    op.create_table(
        "notification_channels",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("target_enc", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('email','sms','push','log')", name="ck_channel_kind"),
        sa.UniqueConstraint("organization_id", "name", name="uq_channel_org_name"),
    )
    op.create_index("ix_channels_org_active", "notification_channels", ["organization_id", "is_active"])
    op.execute("ALTER TABLE notification_channels ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notification_channels FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY notification_channels_tenant ON notification_channels FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})")

    op.add_column("notifications", sa.Column("channel_kind", sa.String(12), nullable=False, server_default="log"))
    op.add_column("notifications", sa.Column("target_enc", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "target_enc")
    op.drop_column("notifications", "channel_kind")
    op.execute("DROP POLICY IF EXISTS notification_channels_tenant ON notification_channels")
    op.drop_table("notification_channels")
