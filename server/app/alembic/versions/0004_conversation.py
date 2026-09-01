"""conversation engine: conversations, messages, conversation_state

Revision ID: 0004_conversation
Revises: 0003_user_platform
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_conversation"
down_revision: str | None = "0003_user_platform"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("conversations", "messages", "conversation_state")
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
        "conversations",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('ACTIVE','CLOSED')", name="ck_conversation_status"),
    )
    op.create_index("ix_conversations_patient", "conversations", ["patient_id", "created_at"])

    op.create_table(
        "messages",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("conversation_id", uid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("author_type", sa.String(10), nullable=False),
        sa.Column("content_enc", sa.Text, nullable=False),
        sa.Column("sequence_no", sa.Integer, nullable=False),
        sa.Column("responder_version", sa.String(80), nullable=True),
        sa.Column("generation_path", sa.String(10), nullable=True),
        sa.Column("llm_provider", sa.String(40), nullable=True),
        sa.Column("crisis_event_id", uid(), sa.ForeignKey("crisis_events.id"), nullable=True),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("author_type IN ('PATIENT','ASSISTANT')", name="ck_message_author"),
        sa.CheckConstraint(
            "generation_path IS NULL OR generation_path IN ('FAST','DEEP','TEMPLATE')", name="ck_message_path"
        ),
        sa.UniqueConstraint("conversation_id", "sequence_no", name="uq_message_sequence"),
    )
    op.create_index("ix_messages_conversation", "messages", ["conversation_id", "sequence_no"])

    op.create_table(
        "conversation_state",
        sa.Column("conversation_id", uid(), sa.ForeignKey("conversations.id"), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False, server_default="WELCOME"),
        sa.Column("current_topic", sa.String(120), nullable=True),
        sa.Column("risk_state", sa.String(10), nullable=False, server_default="GREEN"),
        sa.Column("last_question", sa.Text, nullable=True),
        sa.Column("interaction_style_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("language", sa.String(8), nullable=False, server_default="fr"),
        sa.Column("updated_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "stage IN ('WELCOME','EXPLORATION','CLARIFICATION','REFLECTION','SUPPORT',"
            "'ACTION','FOLLOW_UP','CRISIS','HANDOFF','CLOSURE')",
            name="ck_state_stage",
        ),
    )

    for table in _RLS_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
    op.drop_table("conversation_state")
    op.drop_table("messages")
    op.drop_table("conversations")
