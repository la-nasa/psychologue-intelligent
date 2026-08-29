"""foundation: tenant, identity, RBAC, audit, RLS

Revision ID: 0001_foundation
Revises:
Create Date: 2026-08-28
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables portant de la donnée de tenant : RLS obligatoire (ADR-008 / threat-model-v2 TV-01).
_RLS_TABLES = ("clinics", "users", "sessions", "user_roles", "audit_logs")

# Rôles RBAC de la plateforme (overview-v2 §12). `PATIENT` n'a jamais accès au
# dashboard clinique ; `RESEARCHER` ne reçoit que des données dé-identifiées.
_ROLES = [
    ("PATIENT", "Personne suivie"),
    ("PSYCHOLOGIST", "Psychologue clinicien"),
    ("CLINICAL_SUPERVISOR", "Superviseur clinique"),
    ("RESEARCHER", "Chercheur (données dé-identifiées uniquement)"),
    ("ML_ENGINEER", "Ingenieur ML / MLOps"),
    ("SECURITY_AUDITOR", "Auditeur securite (lecture)"),
    ("ADMIN", "Administrateur d'organisation"),
    ("SUPER_ADMIN", "Exploitation plateforme (cross-organisation, audit renforce)"),
]

_PERMISSIONS = [
    ("auth.login", "Se connecter"),
    ("profile.read_own", "Lire son profil"),
    ("profile.write_own", "Modifier son profil"),
    ("conversation.participate", "Participer a une conversation"),
    ("assessment.submit_own", "Soumettre une auto-evaluation"),
    ("clinician.dashboard.read", "Acceder au tableau de bord clinicien"),
    ("clinician.patient.read", "Lire le dossier d'un patient suivi"),
    ("alert.act", "Agir sur une alerte"),
    ("learning.review", "Revoir un feedback d'apprentissage"),
    ("model.approve", "Approuver une version de modele"),
    ("admin.users.manage", "Gerer les utilisateurs d'une organisation"),
    ("admin.relationships.manage", "Gerer les relations patient-clinicien"),
    ("platform.operate", "Operer la plateforme (cross-organisation)"),
    ("security.audit.read", "Lire les journaux d'audit et de securite"),
]

_ROLE_PERMISSIONS = {
    "PATIENT": ["auth.login", "profile.read_own", "profile.write_own", "conversation.participate", "assessment.submit_own"],
    "PSYCHOLOGIST": ["auth.login", "clinician.dashboard.read", "clinician.patient.read", "alert.act", "learning.review", "model.approve"],
    "CLINICAL_SUPERVISOR": ["auth.login", "clinician.dashboard.read", "clinician.patient.read", "alert.act", "learning.review", "model.approve"],
    "RESEARCHER": ["auth.login"],
    "ML_ENGINEER": ["auth.login"],
    "SECURITY_AUDITOR": ["auth.login", "security.audit.read"],
    "ADMIN": ["auth.login", "admin.users.manage", "admin.relationships.manage"],
    "SUPER_ADMIN": ["auth.login", "platform.operate", "security.audit.read"],
}


_MATCH = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR organization_id::text = current_setting('app.current_organization', true)"
)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    if table == "audit_logs":
        # Append-only : lecture strictement scopée, insertion autorisée pour sa
        # propre organisation OU une ligne globale (organization_id NULL) ;
        # aucune politique UPDATE/DELETE => modification impossible hors bypass.
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({_MATCH})")
        op.execute(
            f"CREATE POLICY {table}_insert ON {table} FOR INSERT "
            f"WITH CHECK ({_MATCH} OR organization_id IS NULL)"
        )
        return
    op.execute(
        f"CREATE POLICY {table}_tenant ON {table} FOR ALL USING ({_MATCH}) WITH CHECK ({_MATCH})"
    )


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name="ck_org_status"),
    )

    op.create_table(
        "clinics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_clinics_org", "clinics", ["organization_id", "status"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email_normalized", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("mfa_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("mfa_secret_enc", sa.Text, nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('ACTIVE','LOCKED','DISABLED')", name="ck_user_status"),
    )
    op.create_index(
        "uq_users_org_email_active",
        "users",
        ["organization_id", "email_normalized"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_sessions_user", "sessions", ["user_id"])

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("description", sa.String(200), nullable=False, server_default=""),
    )
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.String(200), nullable=False, server_default=""),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("permissions.id"), primary_key=True),
    )
    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("granted_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurred_at", postgresql.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("resource_type", sa.String(60), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("outcome", sa.String(10), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("outcome IN ('SUCCESS','DENIED','FAILURE')", name="ck_audit_outcome"),
    )
    op.create_index("ix_audit_occurred", "audit_logs", ["occurred_at"])
    op.create_index("ix_audit_org_actor", "audit_logs", ["organization_id", "actor_id", "occurred_at"])

    for table in _RLS_TABLES:
        _enable_rls(table)

    # --- Seed RBAC (tables globales, pas de RLS) ---
    roles_t = sa.table("roles", sa.column("id", postgresql.UUID), sa.column("code"), sa.column("description"))
    perms_t = sa.table("permissions", sa.column("id", postgresql.UUID), sa.column("code"), sa.column("description"))
    rp_t = sa.table("role_permissions", sa.column("role_id", postgresql.UUID), sa.column("permission_id", postgresql.UUID))

    role_ids = {code: uuid.uuid4() for code, _ in _ROLES}
    perm_ids = {code: uuid.uuid4() for code, _ in _PERMISSIONS}
    op.bulk_insert(roles_t, [{"id": role_ids[c], "code": c, "description": d} for c, d in _ROLES])
    op.bulk_insert(perms_t, [{"id": perm_ids[c], "code": c, "description": d} for c, d in _PERMISSIONS])
    op.bulk_insert(
        rp_t,
        [
            {"role_id": role_ids[role], "permission_id": perm_ids[perm]}
            for role, perms in _ROLE_PERMISSIONS.items()
            for perm in perms
        ],
    )


def downgrade() -> None:
    for table in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_read ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_insert ON {table}")
    op.drop_table("audit_logs")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("clinics")
    op.drop_table("organizations")
