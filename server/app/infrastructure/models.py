from __future__ import annotations

import datetime as dt
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.providers.embedding import EMBEDDING_DIM
from app.core.db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> Mapped[dt.datetime]:
    return mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


# --------------------------------------------------------------------------- #
# Tenant & identité (foundation — Phase 2)                                     #
# --------------------------------------------------------------------------- #


class Organization(Base):
    """Frontière d'isolation. Table GLOBALE (pas de RLS)."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (CheckConstraint("status IN ('ACTIVE','SUSPENDED')", name="ck_org_status"),)


class Clinic(Base):
    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (Index("ix_clinics_org", "organization_id", "status"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    mfa_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    mfa_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _now()
    deleted_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        # Unicité de l'e-mail par organisation, parmi les comptes non supprimés.
        Index(
            "uq_users_org_email_active",
            "organization_id",
            "email_normalized",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint("status IN ('ACTIVE','LOCKED','DISABLED')", name="ck_user_status"),
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (Index("ix_sessions_user", "user_id"),)


# --------------------------------------------------------------------------- #
# RBAC — tables GLOBALES (catalogue plateforme)                               #
# --------------------------------------------------------------------------- #


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True)


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    granted_at: Mapped[dt.datetime] = _now()

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_role"),)


# --------------------------------------------------------------------------- #
# Audit — append-only                                                         #
# --------------------------------------------------------------------------- #


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    occurred_at: Mapped[dt.datetime] = _now()
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(60), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    __table_args__ = (
        CheckConstraint("outcome IN ('SUCCESS','DENIED','FAILURE')", name="ck_audit_outcome"),
        Index("ix_audit_occurred", "occurred_at"),
        Index("ix_audit_org_actor", "organization_id", "actor_id", "occurred_at"),
    )


# --------------------------------------------------------------------------- #
# Plateforme utilisateur : consentement, profil, préférences, suppression      #
# (Phase 3). Porté/étendu de v1 (migration 002/011).                           #
# --------------------------------------------------------------------------- #

# Finalités de consentement (data-model-v2 §3, ADR-007). AI_EXTERNAL et VOICE
# sont nouvelles vs v1.
CONSENT_PURPOSES = ("CARE", "LEARNING", "AI_EXTERNAL", "VOICE", "ANALYTICS", "RESEARCH")


class ConsentVersion(Base):
    """Texte de consentement versionné. Table GLOBALE (catalogue plateforme)."""

    __tablename__ = "consent_versions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    document_ref: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    published_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        UniqueConstraint("purpose", "version", name="uq_consent_version"),
        CheckConstraint(
            "purpose IN ('CARE','LEARNING','AI_EXTERNAL','VOICE','ANALYTICS','RESEARCH')",
            name="ck_consent_version_purpose",
        ),
    )


class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    purpose: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    granted_at: Mapped[dt.datetime] = _now()
    revoked_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "purpose", "version", name="uq_consent_decision"),
        CheckConstraint(
            "purpose IN ('CARE','LEARNING','AI_EXTERNAL','VOICE','ANALYTICS','RESEARCH')",
            name="ck_consent_purpose",
        ),
        Index("ix_consents_active", "user_id", "purpose", postgresql_where=text("revoked_at IS NULL")),
    )


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    about_me_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="fr")
    onboarding_completed_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[dt.datetime] = _now()


class CommunicationPreference(Base):
    __tablename__ = "communication_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    tone: Mapped[str] = mapped_column(String(16), nullable=False, default="warm")
    response_length: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    question_frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    directiveness: Mapped[str] = mapped_column(String(16), nullable=False, default="balanced")
    updated_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("tone IN ('warm','neutral','direct')", name="ck_pref_tone"),
        CheckConstraint("response_length IN ('short','medium','detailed')", name="ck_pref_length"),
        CheckConstraint("question_frequency IN ('low','medium','high')", name="ck_pref_qfreq"),
        CheckConstraint("directiveness IN ('reflective','balanced','directive')", name="ck_pref_directive"),
    )


class Phq9Assessment(Base):
    __tablename__ = "phq9_assessments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    instrument_version: Mapped[str] = mapped_column(String(16), nullable=False)
    answers_enc: Mapped[str] = mapped_column(Text, nullable=False)
    total_score: Mapped[int] = mapped_column(nullable=False)
    item9_score: Mapped[int] = mapped_column(nullable=False)
    completed_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("total_score BETWEEN 0 AND 27", name="ck_phq9_total"),
        CheckConstraint("item9_score BETWEEN 0 AND 3", name="ck_phq9_item9"),
        Index("ix_phq9_user_time", "user_id", "completed_at"),
    )


class AssessmentReminder(Base):
    __tablename__ = "assessment_reminders"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    instrument: Mapped[str] = mapped_column(String(16), nullable=False, server_default="PHQ-9")
    due_at: Mapped[dt.datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="PENDING")
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("status IN ('PENDING','SENT','DONE','CANCELLED')", name="ck_reminder_status"),
        Index("ix_reminder_due", "status", "due_at"),
    )


class Goal(Base):
    """Objectif de travail choisi par la personne (master prompt §56 : jamais imposé)."""

    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="ACTIVE")
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','ACHIEVED','PAUSED','DROPPED')", name="ck_goal_status"),
        Index("ix_goals_user", "user_id", "status"),
    )


class GoalProgress(Base):
    __tablename__ = "goal_progress"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    goal_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("goals.id"), nullable=False)
    value: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    note_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("value BETWEEN 0 AND 100", name="ck_goal_progress_value"),
        Index("ix_goal_progress_goal", "goal_id", "recorded_at"),
    )


class DeletionRequest(Base):
    __tablename__ = "deletion_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="OPEN")
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("status IN ('OPEN','COMPLETED','CANCELLED')", name="ck_deletion_status"),
        Index("uq_deletion_open", "user_id", unique=True, postgresql_where=text("status = 'OPEN'")),
    )


# --------------------------------------------------------------------------- #
# Moteur de sûreté : risque -> crise -> alerte -> notification (Phase B)       #
# Porté de v1 (migrations 004/005/008/009), + organization_id + RLS.           #
# --------------------------------------------------------------------------- #


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    input_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_available: Mapped[bool] = mapped_column(nullable=False)
    emotion_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    emotion_confidence: Mapped[float | None] = mapped_column(nullable=True)
    emotion_model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 1", name="ck_risk_score"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_risk_confidence"),
        Index("ix_risk_patient", "patient_id", "created_at"),
    )


class CrisisEvent(Base):
    __tablename__ = "crisis_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("risk_assessments.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    reasons: Mapped[str] = mapped_column(Text, nullable=False)
    rules_version: Mapped[str] = mapped_column(String(40), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("level IN ('GREEN','ORANGE','RED')", name="ck_crisis_level"),
        Index("ix_crisis_patient", "patient_id", "created_at"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(12), nullable=False, server_default="MESSAGE")
    crisis_event_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("crisis_events.id"), nullable=True)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("phq9_assessments.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    score: Mapped[float] = mapped_column(nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    sla_due_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    assigned_clinician_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[dt.datetime] = _now()
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("level IN ('ORANGE','RED')", name="ck_alert_level"),
        CheckConstraint("source IN ('MESSAGE','ASSESSMENT')", name="ck_alert_source"),
        CheckConstraint(
            "status IN ('OPEN','NOTIFIED','ACKNOWLEDGED','IN_REVIEW','ESCALATED','RESOLVED','CLOSED','CANCELLED')",
            name="ck_alert_status",
        ),
        CheckConstraint(
            "(crisis_event_id IS NOT NULL) OR (assessment_id IS NOT NULL)", name="ck_alert_has_trigger"
        ),
        Index("ix_alerts_status", "organization_id", "status", "level", "created_at"),
        Index("ix_alerts_assignee", "assigned_clinician_id", "status"),
    )


class AlertAction(Base):
    __tablename__ = "alert_actions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    alert_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alerts.id"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (Index("ix_alert_actions_alert", "alert_id", "created_at"),)


# --------------------------------------------------------------------------- #
# Moteur de mémoire (Phase 5) — data-model-v2 §5, overview-v2 §6.               #
# --------------------------------------------------------------------------- #

MEMORY_TYPES = ("WORKING", "EPISODIC", "SEMANTIC", "LONGITUDINAL")
MEMORY_PROVENANCE = ("USER_DECLARED", "MODEL_INFERRED", "CLINICIAN_VALIDATED", "SYSTEM_DERIVED", "TEMPORARY")
MEMORY_STATUSES = ("ACTIVE", "UNCERTAIN", "EXPIRED", "REVOKED", "CLINICIAN_VALIDATED")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    content_enc: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    provenance: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, server_default=text("1.0"))
    sensitivity: Mapped[str] = mapped_column(String(12), nullable=False, server_default="normal")
    consent_scope: Mapped[str] = mapped_column(String(20), nullable=False, server_default="CARE")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()
    expires_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("type IN ('WORKING','EPISODIC','SEMANTIC','LONGITUDINAL')", name="ck_memory_type"),
        CheckConstraint(
            "provenance IN ('USER_DECLARED','MODEL_INFERRED','CLINICIAN_VALIDATED','SYSTEM_DERIVED','TEMPORARY')",
            name="ck_memory_provenance",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','UNCERTAIN','EXPIRED','REVOKED','CLINICIAN_VALIDATED')", name="ck_memory_status"
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_memory_confidence"),
        Index("ix_memories_user", "user_id", "type", "status"),
    )


class LongitudinalSnapshot(Base):
    __tablename__ = "longitudinal_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    emotion_trend_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    phq9_trend_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    goal_trend_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    risk_trend_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    engagement_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    computed_at: Mapped[dt.datetime] = _now()

    __table_args__ = (Index("ix_longitudinal_user", "user_id", "computed_at"),)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ACTIVE")
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','CLOSED')", name="ck_conversation_status"),
        Index("ix_conversations_patient", "patient_id", "created_at"),
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    author_type: Mapped[str] = mapped_column(String(10), nullable=False)
    content_enc: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_no: Mapped[int] = mapped_column(nullable=False)
    responder_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    generation_path: Mapped[str | None] = mapped_column(String(10), nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    crisis_event_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("crisis_events.id"), nullable=True)
    created_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint("author_type IN ('PATIENT','ASSISTANT')", name="ck_message_author"),
        CheckConstraint("generation_path IS NULL OR generation_path IN ('FAST','DEEP','TEMPLATE')", name="ck_message_path"),
        UniqueConstraint("conversation_id", "sequence_no", name="uq_message_sequence"),
        Index("ix_messages_conversation", "conversation_id", "sequence_no"),
    )


class ConversationState(Base):
    __tablename__ = "conversation_state"

    conversation_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("conversations.id"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, default="WELCOME")
    current_topic: Mapped[str | None] = mapped_column(String(120), nullable=True)
    risk_state: Mapped[str] = mapped_column(String(10), nullable=False, default="GREEN")
    last_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    interaction_style_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="fr")
    updated_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint(
            "stage IN ('WELCOME','EXPLORATION','CLARIFICATION','REFLECTION','SUPPORT',"
            "'ACTION','FOLLOW_UP','CRISIS','HANDOFF','CLOSURE')",
            name="ck_state_stage",
        ),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    organization_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    alert_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("alerts.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    template_version: Mapped[str] = mapped_column(String(40), nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    next_retry_at: Mapped[dt.datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = _now()
    updated_at: Mapped[dt.datetime] = _now()

    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('PENDING','SENT','FAILED','SKIPPED_NO_CHANNEL')",
            name="ck_notification_status",
        ),
        Index("ix_notifications_alert", "alert_id", "channel"),
        Index("ix_notifications_retry", "delivery_status", "next_retry_at"),
    )
