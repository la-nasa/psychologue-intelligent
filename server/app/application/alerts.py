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

# Transitions autorisées (porté verbatim de v1).
TRANSITIONS: dict[str, set[str]] = {
    "OPEN": {"ACKNOWLEDGED", "ESCALATED", "CANCELLED"},
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
    crisis_event_id: uuid.UUID,
    decision: CrisisDecision,
    idempotency_key: str,
    sla_due_at: dt.datetime | None = None,
) -> tuple[Alert, bool]:
    existing = (
        await session.execute(select(Alert).where(Alert.idempotency_key == idempotency_key))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    alert = Alert(
        id=uuid.uuid4(),
        organization_id=organization_id,
        patient_id=patient_id,
        crisis_event_id=crisis_event_id,
        level=decision.level,
        status="OPEN",
        idempotency_key=idempotency_key,
        score=decision.score,
        policy_version=decision.policy_version,
        sla_due_at=sla_due_at,
    )
    session.add(alert)
    await session.flush()
    return alert, True


async def transition_alert(
    session: AsyncSession,
    *,
    alert_id: uuid.UUID,
    target: str,
    actor_id: uuid.UUID,
    justification: str,
) -> Alert:
    row = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if row is None:
        raise ValueError("alert not found")
    current = row.status
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError("invalid alert transition")

    now = dt.datetime.now(dt.UTC)
    stmt = (
        update(Alert)
        .where(Alert.id == alert_id, Alert.status == current)
        .values(
            status=target,
            acknowledged_at=now if target == "ACKNOWLEDGED" else Alert.acknowledged_at,
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
            justification=justification or None,
        )
    )
    await session.flush()
    await session.refresh(row)
    return row
