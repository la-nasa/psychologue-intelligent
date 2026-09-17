"""Phase 15 (analytics), Phase 16 (continuous learning governance), Phase 17
(MLOps / model registry) — master prompt §15, §16, §42, §137.

Analytics events are deliberately their own table, populated only from
domain events (never a join against clinical tables), and are written only
for users with an active ANALYTICS consent. Learning samples require an
active LEARNING consent at sampling time and a double approval (one
clinical role, one ML_ENGINEER) before promotion; nothing here trains a
model automatically. Model versions mirror what's registered in the
external MLflow registry so governance state survives even if the MLflow
service is briefly unavailable.

Revision ID: 0012_analytics_learning_mlops
Revises: 0011_ai_review
Create Date: 2026-09-16
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_analytics_learning_mlops"
down_revision: str | None = "0011_ai_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MATCH = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR organization_id::text = current_setting('app.current_organization', true)"
)


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_tenant ON {table} FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})")


def upgrade() -> None:
    uid = lambda: postgresql.UUID(as_uuid=True)  # noqa: E731
    ts = lambda: postgresql.TIMESTAMP(timezone=True)  # noqa: E731

    # --- Phase 15 : analytics produit, séparé des données cliniques ---
    op.create_table(
        "analytics_events",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        # Pseudonyme rotatif (HMAC(user_id, sel hebdomadaire)) — jamais l'UUID utilisateur direct,
        # jamais joint aux tables cliniques (patient_summary, phq9_assessments, etc.).
        sa.Column("pseudonym", sa.String(64), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("properties", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("category IN ('PRODUCT','AI_QUALITY')", name="ck_analytics_category"),
    )
    op.create_index("ix_analytics_org_type_time", "analytics_events", ["organization_id", "event_type", "occurred_at"])
    _rls("analytics_events")

    # --- Phase 16 : gouvernance de l'apprentissage continu (aucun ré-entraînement automatique) ---
    op.create_table(
        "learning_samples",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("source_message_id", uid(), sa.ForeignKey("messages.id"), nullable=False),
        # Contenu anonymisé (jamais le message brut) — chiffré comme le reste des champs sensibles.
        sa.Column("anonymized_prompt_enc", sa.Text, nullable=True),
        sa.Column("anonymized_response_enc", sa.Text, nullable=False),
        sa.Column("model_version", sa.String(80), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("clinical_reviewer_id", uid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("clinical_decision", sa.String(10), nullable=True),
        sa.Column("clinical_reviewed_at", ts(), nullable=True),
        sa.Column("technical_reviewer_id", uid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("technical_decision", sa.String(10), nullable=True),
        sa.Column("technical_reviewed_at", ts(), nullable=True),
        sa.Column("rollback_reason", sa.Text, nullable=True),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('PENDING_REVIEW','APPROVED','REJECTED','PROMOTED','ROLLED_BACK')",
            name="ck_learning_sample_status",
        ),
        sa.CheckConstraint(
            "clinical_decision IS NULL OR clinical_decision IN ('APPROVE','REJECT')",
            name="ck_learning_sample_clinical_decision",
        ),
        sa.CheckConstraint(
            "technical_decision IS NULL OR technical_decision IN ('APPROVE','REJECT')",
            name="ck_learning_sample_technical_decision",
        ),
        sa.UniqueConstraint("source_message_id", name="uq_learning_sample_message"),
    )
    op.create_index("ix_learning_samples_org_status", "learning_samples", ["organization_id", "status", "created_at"])
    _rls("learning_samples")

    # --- Phase 17 : registre de versions de modèle (miroir gouvernance du MLflow Model Registry) ---
    op.create_table(
        "model_versions",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("organization_id", uid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False, server_default="EXPERIMENTAL"),
        sa.Column("mlflow_run_id", sa.String(80), nullable=True),
        sa.Column("mlflow_model_version", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("registered_by", uid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", ts(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "stage IN ('EXPERIMENTAL','STAGING','SHADOW','CANARY','PRODUCTION','RETIRED')",
            name="ck_model_version_stage",
        ),
        sa.UniqueConstraint("organization_id", "name", "version", name="uq_model_version"),
    )
    op.create_index("ix_model_versions_org_stage", "model_versions", ["organization_id", "stage"])
    _rls("model_versions")

    # --- Permissions manquantes pour que RESEARCHER / ML_ENGINEER puissent réellement agir ---
    perms_t = sa.table("permissions", sa.column("id", postgresql.UUID), sa.column("code"), sa.column("description"))
    rp_t = sa.table("role_permissions", sa.column("role_id", postgresql.UUID), sa.column("permission_id", postgresql.UUID))

    op.bulk_insert(
        perms_t,
        [{"id": uuid.uuid4(), "code": "analytics.read", "description": "Lire les tableaux de bord analytics produit"}],
    )

    conn = op.get_bind()
    role_ids = dict(conn.execute(sa.text("SELECT code, id FROM roles")).fetchall())
    existing_perm_ids = dict(conn.execute(sa.text("SELECT code, id FROM permissions")).fetchall())

    grants = [
        ("ML_ENGINEER", "learning.review"),
        ("ML_ENGINEER", "model.approve"),
        ("RESEARCHER", "analytics.read"),
        ("ADMIN", "analytics.read"),
        ("SUPER_ADMIN", "analytics.read"),
    ]
    op.bulk_insert(
        rp_t,
        [
            {"role_id": role_ids[role], "permission_id": existing_perm_ids[perm]}
            for role, perm in grants
        ],
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE code = 'analytics.read'
        )
        """
    )
    op.execute(
        """
        DELETE FROM role_permissions
        WHERE role_id IN (SELECT id FROM roles WHERE code = 'ML_ENGINEER')
          AND permission_id IN (SELECT id FROM permissions WHERE code IN ('learning.review', 'model.approve'))
        """
    )
    op.execute("DELETE FROM permissions WHERE code = 'analytics.read'")

    op.execute("DROP POLICY IF EXISTS model_versions_tenant ON model_versions")
    op.drop_table("model_versions")
    op.execute("DROP POLICY IF EXISTS learning_samples_tenant ON learning_samples")
    op.drop_table("learning_samples")
    op.execute("DROP POLICY IF EXISTS analytics_events_tenant ON analytics_events")
    op.drop_table("analytics_events")
