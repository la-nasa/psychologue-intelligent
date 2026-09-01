"""EscalationEngine (master prompt §28) — mappe une décision de crise vers une
alerte (idempotente, avec SLA) et une notification. Extrait de `safety.py` pour
nommer explicitement le composant ; comportement inchangé, testé par la suite
`test_safety_pipeline.py`.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.alerts import open_alert, open_alert_from_decision
from app.application.notifications import NotificationOutcome, NotificationProvider, notify_alert
from app.domain.safety.crisis import CrisisDecision
from app.domain.safety.policy import CrisisPolicy

ALERT_LEVELS = ("ORANGE", "RED")


async def escalate(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    patient_id: uuid.UUID,
    crisis_event_id: uuid.UUID,
    decision: CrisisDecision,
    policy: CrisisPolicy,
    idempotency_key: str,
    notification_provider: NotificationProvider,
    request_id: str,
) -> tuple[uuid.UUID | None, bool, tuple[NotificationOutcome, ...]]:
    if decision.level not in ALERT_LEVELS:
        return None, False, ()

    sla_minutes = policy.response_sla_minutes.get(decision.level)
    sla_due_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=sla_minutes) if sla_minutes else None

    alert, created = await open_alert_from_decision(
        session,
        organization_id=organization_id,
        patient_id=patient_id,
        crisis_event_id=crisis_event_id,
        decision=decision,
        idempotency_key=idempotency_key,
        sla_due_at=sla_due_at,
    )
    outcomes: tuple[NotificationOutcome, ...] = ()
    if created:
        outcomes = tuple(
            await notify_alert(
                session,
                alert=alert,
                channels=policy.notification_channels,
                provider=notification_provider,
                request_id=request_id,
            )
        )
    return alert.id, created, outcomes


async def escalate_assessment(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    patient_id: uuid.UUID,
    assessment_id: uuid.UUID,
    level: str,
    score: float,
    policy: CrisisPolicy,
    notification_provider: NotificationProvider,
    request_id: str,
) -> tuple[uuid.UUID | None, bool, tuple[NotificationOutcome, ...]]:
    """Alerte issue d'une auto-évaluation PHQ-9 (item 9 positif ou score total
    élevé). Passe par le même cycle de vie / SLA / notification qu'une alerte de
    message. `assessment_id` sert de clé d'idempotence : re-soumettre la même
    évaluation ne duplique jamais l'alerte."""
    if level not in ALERT_LEVELS:
        return None, False, ()

    sla_minutes = policy.response_sla_minutes.get(level)
    sla_due_at = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=sla_minutes) if sla_minutes else None

    alert, created = await open_alert(
        session,
        organization_id=organization_id,
        patient_id=patient_id,
        idempotency_key=f"phq9:{assessment_id}",
        level=level,
        score=score,
        policy_version=policy.version,
        source="ASSESSMENT",
        assessment_id=assessment_id,
        sla_due_at=sla_due_at,
    )
    outcomes: tuple[NotificationOutcome, ...] = ()
    if created:
        outcomes = tuple(
            await notify_alert(
                session, alert=alert, channels=policy.notification_channels,
                provider=notification_provider, request_id=request_id,
            )
        )
    return alert.id, created, outcomes
