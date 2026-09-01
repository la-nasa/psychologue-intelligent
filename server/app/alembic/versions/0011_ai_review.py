"""clinician AI review: structured review of assistant responses

Revision ID: 0011_ai_review
Revises: 0010_clinician
Create Date: 2026-09-01
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_ai_review"
down_revision: str | None = "0010_clinician"
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
        "clinician_response_reviews",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("message_id", uid(), sa.ForeignKey("messages.id"), nullable=False),
        sa.Column("reviewer_id", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("corrected_response_enc", sa.Text, nullable=True),
        sa.Column("scores_json", postgresql.JSONB, nullable=False),
        sa.Column("feedback_category", sa.String(24), nullable=False),
        sa.Column("clinical_comment_enc", sa.Text, nullable=True),
        sa.Column("model_version", sa.String(80), nullable=True),
        sa.Column("policy_version", sa.String(40), nullable=True),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "decision IN ('APPROVE','EDIT','REJECT','FLAG_SAFETY')", name="ck_review_decision"
        ),
        sa.CheckConstraint(
            "decision <> 'EDIT' OR corrected_response_enc IS NOT NULL", name="ck_review_edit_has_correction"
        ),
        sa.UniqueConstraint("message_id", "reviewer_id", name="uq_review_message_reviewer"),
    )
    op.create_index(
        "ix_reviews_org_decision", "clinician_response_reviews", ["organization_id", "decision", "created_at"]
    )
    op.create_index("ix_reviews_model", "clinician_response_reviews", ["model_version", "created_at"])
    op.execute("ALTER TABLE clinician_response_reviews ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE clinician_response_reviews FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY clinician_response_reviews_tenant ON clinician_response_reviews "
        f"FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS clinician_response_reviews_tenant ON clinician_response_reviews")
    op.drop_table("clinician_response_reviews")
