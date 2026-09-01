"""memory engine: memories (pgvector) + longitudinal snapshots

Revision ID: 0005_memory
Revises: 0004_conversation
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.ai.providers.embedding import EMBEDDING_DIM

revision: str = "0005_memory"
down_revision: str | None = "0004_conversation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("memories", "longitudinal_snapshots")
_MATCH = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR organization_id::text = current_setting('app.current_organization', true)"
)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_tenant ON {table} FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    uid = lambda: postgresql.UUID(as_uuid=True)  # noqa: E731
    ts = lambda: postgresql.TIMESTAMP(timezone=True)  # noqa: E731

    op.create_table(
        "memories",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("content_enc", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("provenance", sa.String(24), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default=sa.text("1.0")),
        sa.Column("sensitivity", sa.String(12), nullable=False, server_default="normal"),
        sa.Column("consent_scope", sa.String(20), nullable=False, server_default="CARE"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("source_conversation_id", uid(), sa.ForeignKey("conversations.id"), nullable=True),
        sa.Column("source_message_id", uid(), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", ts(), nullable=True),
        sa.CheckConstraint("type IN ('WORKING','EPISODIC','SEMANTIC','LONGITUDINAL')", name="ck_memory_type"),
        sa.CheckConstraint(
            "provenance IN ('USER_DECLARED','MODEL_INFERRED','CLINICIAN_VALIDATED','SYSTEM_DERIVED','TEMPORARY')",
            name="ck_memory_provenance",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','UNCERTAIN','EXPIRED','REVOKED','CLINICIAN_VALIDATED')", name="ck_memory_status"
        ),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_memory_confidence"),
    )
    op.create_index("ix_memories_user", "memories", ["user_id", "type", "status"])
    # Index vectoriel HNSW restreint aux mémoires ACTIVES : la récupération ne
    # peut structurellement pas remonter une mémoire révoquée / expirée / incertaine
    # (threat-model-v2 TV-05).
    op.execute(
        "CREATE INDEX ix_memories_embedding ON memories "
        "USING hnsw (embedding vector_cosine_ops) WHERE status = 'ACTIVE'"
    )

    op.create_table(
        "longitudinal_snapshots",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("emotion_trend_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("phq9_trend_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("goal_trend_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("risk_trend_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("engagement_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("computed_at", ts(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_longitudinal_user", "longitudinal_snapshots", ["user_id", "computed_at"])

    for table in _RLS_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.drop_table("longitudinal_snapshots")
    op.drop_table("memories")
    # l'extension vector est laissée en place (peut servir à d'autres objets)
