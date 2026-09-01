"""Balayage SLA (master prompt §31, §137).

Point d'entrée d'un worker périodique (Phase 10 : consommateur RabbitMQ /
planificateur). Une alerte `OPEN` ou `NOTIFIED` dont le délai `sla_due_at` est
dépassé sans avoir été prise en charge est **auto-escaladée** (acteur système),
avec une action d'audit. Idempotent : une alerte déjà `ESCALATED`/`ACKNOWLEDGED`/
`RESOLVED`/`CLOSED` n'est jamais touchée.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.application.alerts import transition_alert
from app.infrastructure.models import Alert

LOGGER = logging.getLogger("pi.alerting")
_SWEEPABLE = ("OPEN", "NOTIFIED")


async def sla_sweep(
    session: AsyncSession, *, request_id: str = "sla-sweep", now: dt.datetime | None = None
) -> list[uuid.UUID]:
    moment = now or dt.datetime.now(dt.UTC)
    rows = (
        await session.execute(
            select(Alert).where(
                Alert.status.in_(_SWEEPABLE),
                Alert.sla_due_at.is_not(None),
                Alert.sla_due_at <= moment,
            )
        )
    ).scalars().all()

    escalated: list[uuid.UUID] = []
    for alert in rows:
        try:
            await transition_alert(
                session, alert_id=alert.id, target="ESCALATED", actor_id=None,
                justification="SLA dépassé sans prise en charge",
            )
        except ValueError:
            # course avec une action humaine : ignorer, l'humain a la priorité
            continue
        await audit.record(
            session, request_id=request_id, action="alert.sla_escalated", resource_type="alert",
            resource_id=str(alert.id), organization_id=alert.organization_id, outcome="SUCCESS",
            metadata={"level": alert.level, "source": alert.source},
        )
        escalated.append(alert.id)
    return escalated
