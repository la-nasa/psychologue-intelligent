"""user platform: consent (versioned), profile, preferences, deletion requests

Revision ID: 0003_user_platform
Revises: 0002_safety
Create Date: 2026-08-29
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_user_platform"
down_revision: str | None = "0002_safety"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("consents", "profiles", "communication_preferences", "deletion_requests")
_MATCH = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR organization_id::text = current_setting('app.current_organization', true)"
)
_PURPOSES = ("CARE", "LEARNING", "AI_EXTERNAL", "VOICE", "ANALYTICS", "RESEARCH")
_PURPOSE_CHECK = "purpose IN ('CARE','LEARNING','AI_EXTERNAL','VOICE','ANALYTICS','RESEARCH')"


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_tenant ON {table} FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})")


def upgrade() -> None:
    uid = lambda: postgresql.UUID(as_uuid=True)  # noqa: E731
    ts = lambda: postgresql.TIMESTAMP(timezone=True)  # noqa: E731

    op.create_table(
        "consent_versions",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("document_ref", sa.String(200), nullable=False, server_default=""),
        sa.Column("published_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("purpose", "version", name="uq_consent_version"),
        sa.CheckConstraint(_PURPOSE_CHECK, name="ck_consent_version_purpose"),
    )

    op.create_table(
        "consents",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("granted_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", ts(), nullable=True),
        sa.Column("evidence_ref", sa.String(64), nullable=True),
        sa.UniqueConstraint("user_id", "purpose", "version", name="uq_consent_decision"),
        sa.CheckConstraint(_PURPOSE_CHECK, name="ck_consent_purpose"),
    )
    op.create_index(
        "ix_consents_active", "consents", ["user_id", "purpose"], postgresql_where=sa.text("revoked_at IS NULL")
    )

    op.create_table(
        "profiles",
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("about_me_enc", sa.Text, nullable=True),
        sa.Column("language", sa.String(8), nullable=False, server_default="fr"),
        sa.Column("onboarding_completed_at", ts(), nullable=True),
        sa.Column("updated_at", ts(), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "communication_preferences",
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("tone", sa.String(16), nullable=False, server_default="warm"),
        sa.Column("response_length", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("question_frequency", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("directiveness", sa.String(16), nullable=False, server_default="balanced"),
        sa.Column("updated_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("tone IN ('warm','neutral','direct')", name="ck_pref_tone"),
        sa.CheckConstraint("response_length IN ('short','medium','detailed')", name="ck_pref_length"),
        sa.CheckConstraint("question_frequency IN ('low','medium','high')", name="ck_pref_qfreq"),
        sa.CheckConstraint("directiveness IN ('reflective','balanced','directive')", name="ck_pref_directive"),
    )

    op.create_table(
        "deletion_requests",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="OPEN"),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('OPEN','COMPLETED','CANCELLED')", name="ck_deletion_status"),
    )
    op.create_index("uq_deletion_open", "deletion_requests", ["user_id"], unique=True, postgresql_where=sa.text("status = 'OPEN'"))

    for table in _RLS_TABLES:
        _enable_rls(table)

    cv = sa.table(
        "consent_versions",
        sa.column("id", postgresql.UUID),
        sa.column("purpose"),
        sa.column("version"),
        sa.column("document_ref"),
    )
    op.bulk_insert(
        cv,
        [
            {"id": uuid.uuid4(), "purpose": p, "version": "1", "document_ref": f"consent/{p.lower()}/v1"}
            for p in _PURPOSES
        ],
    )


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.drop_table("deletion_requests")
    op.drop_table("communication_preferences")
    op.drop_table("profiles")
    op.drop_table("consents")
    op.drop_table("consent_versions")
