"""Rappels d'auto-évaluation dus — point d'entrée du worker (Phase 10).

`send_due_reminders` marque `SENT` les rappels échus et journalise l'événement.
**Limite assumée** : l'envoi effectif au patient (e-mail) n'est pas branché —
il demande le canal du patient et une décision produit sur la fréquence
acceptable. Documenté plutôt que simulé.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.infrastructure.models import AssessmentReminder

LOGGER = logging.getLogger("pi.reminders")


async def send_due_reminders(
    session: AsyncSession, *, now: dt.datetime | None = None, request_id: str = "reminder-worker"
) -> list[str]:
    moment = now or dt.datetime.now(dt.UTC)
    rows = (
        await session.execute(
            select(AssessmentReminder).where(
                AssessmentReminder.status == "PENDING", AssessmentReminder.due_at <= moment
            )
        )
    ).scalars().all()
    sent: list[str] = []
    for reminder in rows:
        reminder.status = "SENT"
        await audit.record(
            session, request_id=request_id, action="assessment.reminder.sent", resource_type="assessment_reminder",
            resource_id=str(reminder.id), organization_id=reminder.organization_id, actor_id=reminder.user_id,
            outcome="SUCCESS", metadata={"instrument": reminder.instrument},
        )
        LOGGER.info("reminder due user=%s instrument=%s (delivery not wired)", reminder.user_id, reminder.instrument)
        sent.append(str(reminder.id))
    await session.flush()
    return sent
