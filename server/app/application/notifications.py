"""Livraison de notification d'alerte — porté de v1 `backend/app/notifications.py`.

Idempotent par (alert_id, channel, template_version). Retry synchrone borné,
puis reprise en arrière-plan avec backoff exponentiel jusqu'à une lettre morte
durable (threat-model-v2 TH-06/TM-08). Async + SQLAlchemy + scopé au tenant.

Cible V2 (data-model-v2 §4) : outbox strictement transactionnelle — la ligne
`PENDING` est écrite dans la même transaction que l'alerte, l'envoi est fait par
un worker RabbitMQ (Phase 10). Ce port conserve d'abord le comportement v1 ;
le worker et l'outbox stricte arrivent en Phase 10.
"""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.application import audit
from app.infrastructure.models import Alert, Notification

LOGGER = logging.getLogger("pi.notifications")
TEMPLATE_VERSION = "alert-notice-1"
MAX_ATTEMPTS = 3
MAX_TOTAL_ATTEMPTS = 10
BACKOFF_CAP_SECONDS = 21_600  # 6 h


class NotificationProvider(Protocol):
    async def send(self, channel: str, target: str, payload: dict) -> str: ...


class LogNotificationProvider:
    """Développement uniquement : ne contacte jamais un canal réel, prouve seulement
    le contrat de livraison (idempotence, retry, audit) de bout en bout. Un vrai
    fournisseur Email/SMS/Push doit le remplacer avant tout pilote."""

    async def send(self, channel: str, target: str, payload: dict) -> str:
        LOGGER.info("dev notification channel=%s alert_id=%s", channel, payload.get("alert_id"))
        return f"dev-ref-{uuid.uuid4()}"


@dataclass(frozen=True)
class NotificationOutcome:
    channel: str
    status: str
    provider_ref: str | None


def _backoff_seconds(attempt_count: int) -> int:
    return min(60 * (2 ** max(attempt_count - 1, 0)), BACKOFF_CAP_SECONDS)


def _next_retry_at(status: str, attempt_count: int, *, base: dt.datetime) -> dt.datetime | None:
    if status == "SENT" or attempt_count >= MAX_TOTAL_ATTEMPTS:
        return None
    return base + dt.timedelta(seconds=_backoff_seconds(attempt_count))


async def notify_alert(
    session: AsyncSession,
    *,
    alert: Alert,
    channels: tuple[str, ...],
    provider: NotificationProvider,
    request_id: str,
) -> list[NotificationOutcome]:
    if not channels:
        outcome = await _skip_no_channel(session, alert)
        await audit.record(
            session, request_id=request_id, action="notification.skipped_no_channel",
            resource_type="alert", resource_id=str(alert.id), organization_id=alert.organization_id, outcome="SUCCESS",
        )
        return [outcome]
    return [await _notify_one(session, alert, channel, provider, request_id) for channel in channels]


async def _skip_no_channel(session: AsyncSession, alert: Alert) -> NotificationOutcome:
    key = f"{alert.id}:none:{TEMPLATE_VERSION}"
    existing = (await session.execute(select(Notification).where(Notification.idempotency_key == key))).scalar_one_or_none()
    if existing is not None:
        return NotificationOutcome("none", existing.delivery_status, existing.provider_ref)
    session.add(
        Notification(
            id=uuid.uuid4(), organization_id=alert.organization_id, alert_id=alert.id, channel="none",
            template_version=TEMPLATE_VERSION, delivery_status="SKIPPED_NO_CHANNEL", attempt_count=0, idempotency_key=key,
        )
    )
    await session.flush()
    return NotificationOutcome("none", "SKIPPED_NO_CHANNEL", None)


async def _notify_one(
    session: AsyncSession, alert: Alert, channel: str, provider: NotificationProvider, request_id: str
) -> NotificationOutcome:
    key = f"{alert.id}:{channel}:{TEMPLATE_VERSION}"
    existing = (await session.execute(select(Notification).where(Notification.idempotency_key == key))).scalar_one_or_none()
    if existing is not None and existing.delivery_status == "SENT":
        return NotificationOutcome(channel, "SENT", existing.provider_ref)

    if existing is None:
        notif = Notification(
            id=uuid.uuid4(), organization_id=alert.organization_id, alert_id=alert.id, channel=channel,
            template_version=TEMPLATE_VERSION, delivery_status="PENDING", attempt_count=0, idempotency_key=key,
        )
        session.add(notif)
        await session.flush()
    else:
        notif = existing

    status, provider_ref = "FAILED", None
    attempt_count = notif.attempt_count
    for _ in range(MAX_ATTEMPTS):
        attempt_count += 1
        try:
            provider_ref = await provider.send(channel, str(alert.patient_id), {"alert_id": str(alert.id), "level": alert.level})
            status = "SENT"
            break
        except Exception:
            LOGGER.exception("notification attempt failed alert_id=%s channel=%s attempt=%s", alert.id, channel, attempt_count)

    now = dt.datetime.now(dt.UTC)
    notif.delivery_status = status
    notif.provider_ref = provider_ref
    notif.attempt_count = attempt_count
    notif.next_retry_at = _next_retry_at(status, attempt_count, base=now)
    notif.updated_at = now
    await session.flush()
    await audit.record(
        session, request_id=request_id, action=f"notification.{status.lower()}", resource_type="alert",
        resource_id=str(alert.id), organization_id=alert.organization_id, outcome="SUCCESS", metadata={"channel": channel},
    )
    return NotificationOutcome(channel, status, provider_ref)


async def retry_pending_notifications(
    session: AsyncSession,
    *,
    provider: NotificationProvider,
    request_id: str,
    now: dt.datetime | None = None,
) -> list[NotificationOutcome]:
    """Point d'entrée du worker de reprise (Phase 10 : consommateur RabbitMQ).
    Retente les notifications `FAILED` dont la fenêtre de backoff est écoulée,
    une tentative chacune, jusqu'à `MAX_TOTAL_ATTEMPTS` cumulé."""
    moment = now or dt.datetime.now(dt.UTC)
    rows = (
        await session.execute(
            select(Notification, Alert)
            .join(Alert, Alert.id == Notification.alert_id)
            .where(
                Notification.delivery_status == "FAILED",
                Notification.attempt_count < MAX_TOTAL_ATTEMPTS,
                Notification.channel != "none",
                (Notification.next_retry_at.is_(None)) | (Notification.next_retry_at <= moment),
            )
        )
    ).all()
    return [await _retry_one(session, notif, alert, provider, request_id, moment) for notif, alert in rows]


async def _retry_one(
    session: AsyncSession, notif: Notification, alert: Alert, provider: NotificationProvider, request_id: str, moment: dt.datetime
) -> NotificationOutcome:
    attempt_count = notif.attempt_count + 1
    status, provider_ref = "FAILED", None
    try:
        provider_ref = await provider.send(notif.channel, str(alert.patient_id), {"alert_id": str(alert.id), "level": alert.level})
        status = "SENT"
    except Exception:
        LOGGER.exception("notification retry failed alert_id=%s channel=%s attempt=%s", alert.id, notif.channel, attempt_count)

    await session.execute(
        update(Notification)
        .where(Notification.id == notif.id)
        .values(
            delivery_status=status,
            provider_ref=provider_ref,
            attempt_count=attempt_count,
            next_retry_at=_next_retry_at(status, attempt_count, base=moment),
            updated_at=dt.datetime.now(dt.UTC),
        )
    )
    if status == "SENT":
        action = "notification.retry_sent"
    elif attempt_count >= MAX_TOTAL_ATTEMPTS:
        action = "notification.dead_lettered"
    else:
        action = "notification.retry_failed"
    await audit.record(
        session, request_id=request_id, action=action, resource_type="alert", resource_id=str(alert.id),
        organization_id=alert.organization_id, outcome="SUCCESS", metadata={"channel": notif.channel},
    )
    return NotificationOutcome(notif.channel, status, provider_ref)
