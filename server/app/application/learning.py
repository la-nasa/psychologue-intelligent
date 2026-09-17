"""Phase 16 — gouvernance de l'apprentissage continu (master prompt §16, ADR
de portée : sampling gated on LEARNING consent + anonymisation + double revue
humaine + rollback). **Rien ici ne ré-entraîne ou ne modifie un modèle** :
ce module échantillonne des tours de conversation pour une revue humaine
future, avec deux approbations indépendantes (clinique + technique) avant
promotion. L'export réel vers un jeu de données d'entraînement et le
ré-entraînement lui-même restent hors périmètre — aucune infrastructure de
training n'existe dans cet environnement.
"""
from __future__ import annotations

import datetime as dt
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit, consent
from app.core.crypto import decrypt, encrypt
from app.core.errors import ConflictError, DomainError, NotFoundError, PermissionDeniedError
from app.infrastructure.models import LearningSample

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(\+?\d[\d ().-]{7,}\d)")
_DIGIT_RUN_RE = re.compile(r"\d{4,}")

_CLINICAL_ROLES = ("PSYCHOLOGIST", "CLINICAL_SUPERVISOR")
_TECHNICAL_ROLES = ("ML_ENGINEER",)


def _anonymize(text: str) -> str:
    """Rédaction best-effort par motifs (e-mail, téléphone, longues suites de
    chiffres). Ce n'est **pas** une garantie de dé-identification complète —
    seule une revue humaine avant promotion l'atteste (voir `review`)."""
    redacted = _EMAIL_RE.sub("[e-mail masqué]", text)
    redacted = _PHONE_RE.sub("[numéro masqué]", redacted)
    redacted = _DIGIT_RUN_RE.sub("[nombre masqué]", redacted)
    return redacted


async def sample_message(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    patient_id: uuid.UUID,
    message_id: uuid.UUID,
    prompt_text: str | None,
    response_text: str,
    model_version: str | None,
    request_id: str,
) -> LearningSample | None:
    """Échantillonne un tour GREEN pour revue humaine, uniquement si le
    patient a un consentement LEARNING actif. Best-effort : un échec ici ne
    doit jamais interrompre la conversation en cours (appelé comme
    `memory.remember`, jamais sur le chemin critique)."""
    if not await consent.has_active_consent(session, patient_id, "LEARNING"):
        return None

    sample = LearningSample(
        id=uuid.uuid4(),
        organization_id=organization_id,
        source_message_id=message_id,
        anonymized_prompt_enc=encrypt(_anonymize(prompt_text)) if prompt_text else None,
        anonymized_response_enc=encrypt(_anonymize(response_text)) or "",
        model_version=model_version,
        status="PENDING_REVIEW",
    )
    session.add(sample)
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="learning.sample", resource_type="learning_sample",
        resource_id=str(sample.id), organization_id=organization_id, actor_id=patient_id, outcome="SUCCESS",
    )
    return sample


def to_dict(row: LearningSample) -> dict:
    return {
        "id": str(row.id),
        "status": row.status,
        "model_version": row.model_version,
        "anonymized_prompt": decrypt(row.anonymized_prompt_enc) if row.anonymized_prompt_enc else None,
        "anonymized_response": decrypt(row.anonymized_response_enc) or "",
        "clinical_decision": row.clinical_decision,
        "technical_decision": row.technical_decision,
        "rollback_reason": row.rollback_reason,
        "created_at": row.created_at.isoformat(),
    }


async def list_samples(session: AsyncSession, *, organization_id: uuid.UUID, status: str | None = None) -> list[dict]:
    stmt = select(LearningSample).where(LearningSample.organization_id == organization_id)
    if status is not None:
        stmt = stmt.where(LearningSample.status == status)
    rows = (await session.execute(stmt.order_by(LearningSample.created_at.desc()))).scalars().all()
    return [to_dict(r) for r in rows]


def _reviewer_kind(roles: frozenset[str]) -> str | None:
    if roles.intersection(_CLINICAL_ROLES):
        return "clinical"
    if roles.intersection(_TECHNICAL_ROLES):
        return "technical"
    return None


async def review(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    sample_id: uuid.UUID,
    reviewer_id: uuid.UUID,
    reviewer_roles: frozenset[str],
    decision: str,
    request_id: str,
) -> LearningSample:
    if decision not in ("APPROVE", "REJECT"):
        raise DomainError("unknown review decision", code="invalid_decision")
    kind = _reviewer_kind(reviewer_roles)
    if kind is None:
        raise PermissionDeniedError("this role cannot act as a clinical or technical reviewer")

    row = (
        await session.execute(
            select(LearningSample).where(
                LearningSample.id == sample_id, LearningSample.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("learning sample not found")
    if row.status != "PENDING_REVIEW":
        raise ConflictError("this sample is no longer pending review", code="not_pending")

    now = dt.datetime.now(dt.UTC)
    if kind == "clinical":
        if row.clinical_decision is not None:
            raise ConflictError("you have already reviewed this sample", code="already_reviewed")
        row.clinical_decision = decision
        row.clinical_reviewer_id = reviewer_id
        row.clinical_reviewed_at = now
    else:
        if row.technical_decision is not None:
            raise ConflictError("you have already reviewed this sample", code="already_reviewed")
        row.technical_decision = decision
        row.technical_reviewer_id = reviewer_id
        row.technical_reviewed_at = now

    if decision == "REJECT":
        row.status = "REJECTED"
    elif row.clinical_decision == "APPROVE" and row.technical_decision == "APPROVE":
        row.status = "APPROVED"

    await session.flush()
    await audit.record(
        session, request_id=request_id, action="learning.review", resource_type="learning_sample",
        resource_id=str(row.id), organization_id=organization_id, actor_id=reviewer_id, outcome="SUCCESS",
        metadata={"kind": kind, "decision": decision, "resulting_status": row.status},
    )
    return row


async def promote(
    session: AsyncSession, *, organization_id: uuid.UUID, sample_id: uuid.UUID, actor_id: uuid.UUID, request_id: str
) -> LearningSample:
    row = (
        await session.execute(
            select(LearningSample).where(
                LearningSample.id == sample_id, LearningSample.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("learning sample not found")
    if row.status != "APPROVED":
        raise ConflictError("only a doubly-approved sample can be promoted", code="not_approved")

    row.status = "PROMOTED"
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="learning.promote", resource_type="learning_sample",
        resource_id=str(row.id), organization_id=organization_id, actor_id=actor_id, outcome="SUCCESS",
    )
    return row


async def rollback(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    sample_id: uuid.UUID,
    actor_id: uuid.UUID,
    reason: str,
    request_id: str,
) -> LearningSample:
    row = (
        await session.execute(
            select(LearningSample).where(
                LearningSample.id == sample_id, LearningSample.organization_id == organization_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("learning sample not found")
    if row.status != "PROMOTED":
        raise ConflictError("only a promoted sample can be rolled back", code="not_promoted")

    row.status = "ROLLED_BACK"
    row.rollback_reason = reason
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="learning.rollback", resource_type="learning_sample",
        resource_id=str(row.id), organization_id=organization_id, actor_id=actor_id, outcome="SUCCESS",
        metadata={"reason": reason},
    )
    return row
