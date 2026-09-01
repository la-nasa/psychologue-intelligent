"""Cycle de vie d'une alerte — porté de v1 `backend/app/alerts.py`.

Async + SQLAlchemy + scopé au tenant. Transitions d'état atomiques
(`UPDATE ... WHERE id=? AND status=<état lu>` + `rowcount`) : deux cliniciens
qui courent des transitions conflictuelles depuis le même état de départ ne
peuvent plus se clobberer silencieusement — le perdant reçoit une erreur
explicite (leçon SEC-001 / threat-model-v2 TV-15).
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.safety.crisis import CrisisDecision
from app.infrastructure.models import Alert, AlertAction

# Cycle de vie (master prompt §32). `OPEN` = créée mais notification pas encore
# confirmée ; `NOTIFIED` = au moins un canal a confirmé l'envoi (posé
# automatiquement par l'EscalationEngine). Les transitions suivantes sont
# humaines (clinicien) ou système (balayage SLA -> ESCALATED).
TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"NOTIFIED", "ACKNOWLEDGED", "ESCALATED", "CANCELLED"},
    "NOTIFIED": {"ACKNOWLEDGED", "ESCALATED", "CANCELLED"},
    "ACKNOWLEDGED": {"IN_REVIEW", "ESCALATED", "RESOLVED"},
    "IN_REVIEW": {"ESCALATED", "RESOLVED"},
    "ESCALATED": {"RESOLVED"},
    "RESOLVED": {"CLOSED"},
}


async def open_alert(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    patient_id: uuid.UUID,
    idempotency_key: str,
    level: str,
    score: float,
    policy_version: str,
    source: str = "MESSAGE",
    crisis_event_id: uuid.UUID | None = None,
    assessment_id: uuid.UUID | None = None,
    sla_due_at: dt.datetime | None = None,
) -> tuple[Alert, bool]:
    """Une alerte peut provenir d'un message (`crisis_event_id`) OU d'une
    auto-évaluation (`assessment_id`) — jamais des deux ni d'aucun (CHECK en base)."""
    existing = (
        await session.execute(select(Alert).where(Alert.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    alert = Alert(
        id=uuid.uuid4(),
        organization_id=organization_id,
        patient_id=patient_id,
        source=source,
        crisis_event_id=crisis_event_id,
        assessment_id=assessment_id,
        level=level,
        status="OPEN",
        idempotency_key=idempotency_key,
        score=score,
        policy_version=policy_version,
        sla_due_at=sla_due_at,
    )
    session.add(alert)
    await session.flush()
    return alert, True


async def open_alert_from_decision(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    patient_id: uuid.UUID,
    crisis_event_id: uuid.UUID,
    decision: CrisisDecision,
    idempotency_key: str,
    sla_due_at: dt.datetime | None = None,
) -> tuple[Alert, bool]:
    return await open_alert(
        session,
        organization_id=organization_id,
        patient_id=patient_id,
        idempotency_key=idempotency_key,
        level=decision.level,
        score=decision.score,
        policy_version=decision.policy_version,
        source="MESSAGE",
        crisis_event_id=crisis_event_id,
        sla_due_at=sla_due_at,
    )


async def transition_alert(
    session: AsyncSession,
    *,
    alert_id: uuid.UUID,
    target: str,
    actor_id: uuid.UUID | None,
    justification: str,
    assign_to: uuid.UUID | None = None,
) -> Alert:
    """`actor_id=None` => transition système (auto-NOTIFIED, balayage SLA).
    `assign_to` : pose `assigned_clinician_id` **s'il est encore vide** (première
    prise en charge), dans le même UPDATE atomique que le changement d'état."""
    row = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if row is None:
        raise ValueError("alert not found")
    current = row.status
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError("invalid alert transition")

    now = dt.datetime.now(dt.UTC)
    assignee = assign_to if (assign_to is not None and row.assigned_clinician_id is None) else Alert.assigned_clinician_id
    stmt = (
        update(Alert)
        .where(Alert.id == alert_id, Alert.status == current)
        .values(
            status=target,
            acknowledged_at=now if target == "ACKNOWLEDGED" else Alert.acknowledged_at,
            assigned_clinician_id=assignee,
        )
    )
    result = await session.execute(stmt)
    # `execute()` sur un UPDATE renvoie un CursorResult qui expose rowcount ;
    # les stubs SQLAlchemy le typent plus largement.
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise ValueError("alert status changed concurrently; reload and retry")

    session.add(
        AlertAction(
            id=uuid.uuid4(),
            organization_id=row.organization_id,
            alert_id=alert_id,
            actor_id=actor_id,
            action=target,
            justification=justification or ("system" if actor_id is None else None),
        )
    )
    await session.flush()
    await session.refresh(row)
    return row


async def mark_notified(session: AsyncSession, *, alert_id: uuid.UUID) -> None:
    """Posée par l'EscalationEngine quand au moins un canal a confirmé l'envoi.
    Silencieuse si l'alerte a déjà avancé (un humain a été plus rapide)."""
    try:
        await transition_alert(session, alert_id=alert_id, target="NOTIFIED", actor_id=None, justification="")
    except ValueError:
        pass


# Actions autorisées à un clinicien depuis le tableau de bord (master prompt §32).
# `NOTIFIED`/`CLOSED` sont posés par le système, pas par un clinicien.
CLINICIAN_ACTIONS = frozenset({"ACKNOWLEDGED", "IN_REVIEW", "ESCALATED", "RESOLVED", "CANCELLED"})


async def act_on_alert(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    clinician_id: uuid.UUID,
    alert_id: uuid.UUID,
    target: str,
    justification: str,
    request_id: str,
) -> Alert:
    """Action d'un clinicien sur une alerte. Exige une relation `ACTIVE` avec le
    patient (deny by default) ; s'appuie sur la transition atomique de
    `transition_alert` (le perdant d'une course reçoit un 409)."""
    from app.application import audit
    from app.application.relationships import require_active_relationship
    from app.core.errors import ConflictError, DomainError, NotFoundError

    if target not in CLINICIAN_ACTIONS:
        raise DomainError("action not permitted for a clinician", code="invalid_action")

    alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if alert is None:
        raise NotFoundError("alert not found")

    await require_active_relationship(session, clinician_id=clinician_id, patient_id=alert.patient_id)

    try:
        updated = await transition_alert(
            session,
            alert_id=alert_id,
            target=target,
            actor_id=clinician_id,
            justification=justification,
            assign_to=clinician_id,
        )
    except ValueError as exc:
        message = str(exc)
        if "concurrently" in message:
            raise ConflictError("alert status changed concurrently; reload and retry", code="stale_alert") from exc
        raise DomainError("invalid alert transition", code="invalid_transition") from exc

    await audit.record(
        session, request_id=request_id, action="alert.act", resource_type="alert",
        resource_id=str(alert_id), organization_id=organization_id, actor_id=clinician_id, outcome="SUCCESS",
        metadata={"target": target},
    )
    return updated
