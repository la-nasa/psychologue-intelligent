"""PHQ-9 : soumission, historique, tendance, rappels (master prompt §8, §136).

L'item 9 est isolé et évalué comme signal de sûreté : un score positif (ou un
score total élevé) crée une alerte via l'`EscalationEngine`, avec le **même**
cycle de vie / SLA / notification qu'une alerte issue d'un message. Les seuils
viennent de la politique de crise versionnée (`phq9_alert`), pas du code.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.application.escalation import escalate_assessment
from app.application.notifications import NotificationProvider
from app.application.safety import SafetyConfig
from app.core.crypto import decrypt, encrypt
from app.core.errors import DomainError, NotFoundError
from app.domain.assessment.phq9 import Phq9Result, score, severity_band
from app.infrastructure.models import AssessmentReminder, Phq9Assessment


def _alert_level(result: Phq9Result, policy) -> str | None:
    p = policy.phq9_alert
    if result.item9_score >= p.item9_red_at:
        return "RED"
    if result.item9_score >= p.item9_orange_at or result.total_score >= p.total_orange_at:
        return "ORANGE"
    return None


async def submit_phq9(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    answers: list[int],
    config: SafetyConfig,
    notification_provider: NotificationProvider,
    request_id: str,
) -> dict:
    try:
        result = score(answers)
    except ValueError as exc:
        raise DomainError(str(exc), code="invalid_phq9") from exc

    assessment_id = uuid.uuid4()
    session.add(
        Phq9Assessment(
            id=assessment_id, organization_id=organization_id, user_id=user_id,
            instrument_version=result.instrument_version, answers_enc=encrypt(json.dumps(answers)) or "",
            total_score=result.total_score, item9_score=result.item9_score,
        )
    )
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="assessment.phq9.submit", resource_type="phq9_assessment",
        resource_id=str(assessment_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
        metadata={"total": result.total_score, "item9": result.item9_score},
    )

    level = _alert_level(result, config.policy)
    alert_id = None
    alert_created = False
    if level is not None:
        alert_id, alert_created, _ = await escalate_assessment(
            session, organization_id=organization_id, patient_id=user_id, assessment_id=assessment_id,
            level=level, score=float(result.total_score) / 27.0, policy=config.policy,
            notification_provider=notification_provider, request_id=request_id,
        )

    return {
        "id": str(assessment_id),
        "instrument_version": result.instrument_version,
        "total_score": result.total_score,
        "item9_score": result.item9_score,
        "severity_band": result.severity_band,
        "alert_level": level,
        "alert_created": alert_created,
        "alert_id": str(alert_id) if alert_id else None,
    }


def _row_dict(row: Phq9Assessment) -> dict:
    return {
        "id": str(row.id),
        "total_score": row.total_score,
        "item9_score": row.item9_score,
        "severity_band": severity_band(row.total_score),
        "completed_at": row.completed_at.isoformat(),
    }


async def history(session: AsyncSession, user_id: uuid.UUID, *, limit: int = 24) -> list[dict]:
    rows = (
        await session.execute(
            select(Phq9Assessment)
            .where(Phq9Assessment.user_id == user_id)
            .order_by(Phq9Assessment.completed_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_row_dict(r) for r in rows]


async def trend(session: AsyncSession, user_id: uuid.UUID) -> dict:
    rows = (
        await session.execute(
            select(Phq9Assessment)
            .where(Phq9Assessment.user_id == user_id)
            .order_by(Phq9Assessment.completed_at.desc())
            .limit(2)
        )
    ).scalars().all()
    if not rows:
        return {"latest": None, "previous": None, "delta": None, "direction": "no_data"}
    latest = _row_dict(rows[0])
    if len(rows) == 1:
        return {"latest": latest, "previous": None, "delta": None, "direction": "first"}
    previous = _row_dict(rows[1])
    delta = latest["total_score"] - previous["total_score"]
    # Corrélation statistique, jamais un diagnostic (overview-v2 §6, master prompt §58).
    direction = "improving" if delta < 0 else ("worsening" if delta > 0 else "stable")
    return {"latest": latest, "previous": previous, "delta": delta, "direction": direction}


async def latest_severity_band(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    row = (
        await session.execute(
            select(Phq9Assessment.total_score)
            .where(Phq9Assessment.user_id == user_id)
            .order_by(Phq9Assessment.completed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return severity_band(row) if row is not None else None


async def answers_for(session: AsyncSession, user_id: uuid.UUID, assessment_id: uuid.UUID) -> list[int]:
    row = (
        await session.execute(
            select(Phq9Assessment).where(
                Phq9Assessment.id == assessment_id, Phq9Assessment.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError("no such assessment for this user")
    return json.loads(decrypt(row.answers_enc) or "[]")


async def schedule_reminder(
    session: AsyncSession, *, organization_id: uuid.UUID, user_id: uuid.UUID, due_at: dt.datetime, request_id: str
) -> uuid.UUID:
    if due_at <= dt.datetime.now(dt.UTC):
        raise DomainError("reminder due date must be in the future", code="invalid_due_at")
    reminder_id = uuid.uuid4()
    session.add(
        AssessmentReminder(
            id=reminder_id, organization_id=organization_id, user_id=user_id,
            instrument="PHQ-9", due_at=due_at, status="PENDING",
        )
    )
    await session.flush()
    await audit.record(
        session, request_id=request_id, action="assessment.reminder.schedule", resource_type="assessment_reminder",
        resource_id=str(reminder_id), organization_id=organization_id, actor_id=user_id, outcome="SUCCESS",
    )
    return reminder_id


async def list_reminders(session: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            select(AssessmentReminder)
            .where(AssessmentReminder.user_id == user_id)
            .order_by(AssessmentReminder.due_at)
        )
    ).scalars().all()
    return [
        {"id": str(r.id), "instrument": r.instrument, "due_at": r.due_at.isoformat(), "status": r.status}
        for r in rows
    ]
