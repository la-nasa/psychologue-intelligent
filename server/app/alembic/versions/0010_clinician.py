"""clinician platform: patient-clinician relationships

Revision ID: 0010_clinician
Revises: 0009_notification_channels
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_clinician"
down_revision: str | None = "0009_notification_channels"
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
        "patient_clinician_relationships",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("clinician_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="ACTIVE"),
        sa.Column("created_by", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("ended_at", ts(), nullable=True),
        sa.Column("ended_by", uid(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("status IN ('ACTIVE','ENDED')", name="ck_pcr_status"),
    )
    op.create_index(
        "uq_pcr_active",
        "patient_clinician_relationships",
        ["patient_id", "clinician_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index("ix_pcr_clinician", "patient_clinician_relationships", ["clinician_id", "status"])
    op.create_index("ix_pcr_patient", "patient_clinician_relationships", ["patient_id", "status"])

    op.execute("ALTER TABLE patient_clinician_relationships ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE patient_clinician_relationships FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY patient_clinician_relationships_tenant ON patient_clinician_relationships "
        f"FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS patient_clinician_relationships_tenant ON patient_clinician_relationships")
    op.drop_table("patient_clinician_relationships")
