from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import uuid4

from .auth import utc_now

LOGGER = logging.getLogger("psychologue_intelligent.notifications")
TEMPLATE_VERSION = "alert-notice-1"
MAX_ATTEMPTS = 3
# Total attempts across the synchronous burst above AND the background retry worker
# (scripts/retry_notifications.py) combined. Beyond this the row stays FAILED with
# next_retry_at cleared: a durable dead letter for manual investigation, not a crash.
MAX_TOTAL_ATTEMPTS = 10


class NotificationProvider(Protocol):
    def send(self, channel: str, target: str, payload: dict) -> str:
        """Deliver a notification and return an opaque provider reference. May raise."""
        ...


class LogNotificationProvider:
    """Development-only placeholder. It never contacts a real channel: it only
    proves the delivery contract (idempotency, retry, audit) end to end.
    A real Email/SMS/Push provider must replace this before any pilot use."""

    def send(self, channel: str, target: str, payload: dict) -> str:
        LOGGER.info("dev notification channel=%s target=%s alert_id=%s", channel, target, payload.get("alert_id"))
        return f"dev-ref-{uuid4()}"


@dataclass(frozen=True)
class NotificationOutcome:
    channel: str
    status: str
    provider_ref: str | None


def notify_alert(conn, alert: dict, channels: tuple[str, ...], provider: NotificationProvider, request_id: str) -> list[NotificationOutcome]:
    """Idempotent per (alert_id, channel, template_version). Retries synchronously,
    bounded, within this call. A row left FAILED here re-enters delivery later via
    retry_pending_notifications, on backoff, up to MAX_TOTAL_ATTEMPTS."""
    if not channels:
        outcome = _skip_no_channel(conn, alert["id"])
        _audit(conn, request_id, alert["id"], "notification.skipped_no_channel")
        return [outcome]

    outcomes = []
    for channel in channels:
        outcomes.append(_notify_one_channel(conn, alert, channel, provider, request_id))
    return outcomes


def _skip_no_channel(conn, alert_id: str) -> NotificationOutcome:
    key = f"{alert_id}:none:{TEMPLATE_VERSION}"
    existing = conn.execute("SELECT * FROM notifications WHERE idempotency_key=?", (key,)).fetchone()
    if existing:
        return NotificationOutcome("none", existing["delivery_status"], existing["provider_ref"])
    now = utc_now().isoformat()
    conn.execute(
        "INSERT INTO notifications(id,alert_id,channel,template_version,delivery_status,attempt_count,idempotency_key,created_at,updated_at) "
        "VALUES (?,?,?,?,?,0,?,?,?)",
        (str(uuid4()), alert_id, "none", TEMPLATE_VERSION, "SKIPPED_NO_CHANNEL", key, now, now),
    )
    return NotificationOutcome("none", "SKIPPED_NO_CHANNEL", None)


def _notify_one_channel(conn, alert: dict, channel: str, provider: NotificationProvider, request_id: str) -> NotificationOutcome:
    key = f"{alert['id']}:{channel}:{TEMPLATE_VERSION}"
    existing = conn.execute("SELECT * FROM notifications WHERE idempotency_key=?", (key,)).fetchone()
    if existing and existing["delivery_status"] == "SENT":
        return NotificationOutcome(channel, "SENT", existing["provider_ref"])

    now = utc_now().isoformat()
    if existing:
        notification_id, attempt_count = existing["id"], existing["attempt_count"]
    else:
        notification_id, attempt_count = str(uuid4()), 0
        conn.execute(
            "INSERT INTO notifications(id,alert_id,channel,template_version,delivery_status,attempt_count,idempotency_key,created_at,updated_at) "
            "VALUES (?,?,?,?,'PENDING',0,?,?,?)",
            (notification_id, alert["id"], channel, TEMPLATE_VERSION, key, now, now),
        )

    status, provider_ref = "FAILED", None
    for _ in range(MAX_ATTEMPTS):
        attempt_count += 1
        try:
            provider_ref = provider.send(channel, alert["patient_id"], {"alert_id": alert["id"], "level": alert["level"]})
            status = "SENT"
            break
        except Exception:
            LOGGER.exception("notification attempt failed alert_id=%s channel=%s attempt=%s", alert["id"], channel, attempt_count)

    next_retry_at = _next_retry_at(status, attempt_count)
    conn.execute(
        "UPDATE notifications SET delivery_status=?, provider_ref=?, attempt_count=?, next_retry_at=?, updated_at=? WHERE id=?",
        (status, provider_ref, attempt_count, next_retry_at, utc_now().isoformat(), notification_id),
    )
    _audit(conn, request_id, alert["id"], f"notification.{status.lower()}", channel)
    return NotificationOutcome(channel, status, provider_ref)


def _backoff_seconds(attempt_count: int) -> int:
    """Exponential backoff, 1 minute doubling up to a 6-hour cap."""
    return min(60 * (2 ** max(attempt_count - 1, 0)), 21600)


def _next_retry_at(status: str, attempt_count: int) -> str | None:
    if status == "SENT" or attempt_count >= MAX_TOTAL_ATTEMPTS:
        return None
    return (utc_now() + timedelta(seconds=_backoff_seconds(attempt_count))).isoformat()


def retry_pending_notifications(conn, provider: NotificationProvider, request_id: str, now=None) -> list[NotificationOutcome]:
    """Background worker entry point (see scripts/retry_notifications.py). Retries FAILED
    notifications whose backoff window has elapsed, one attempt each, up to
    MAX_TOTAL_ATTEMPTS combined with the synchronous burst in _notify_one_channel.
    Meant to be invoked periodically by a real OS-level scheduler (cron/Task Scheduler);
    it does nothing on its own between invocations."""
    now_iso = (now or utc_now()).isoformat()
    rows = conn.execute(
        "SELECT n.*, a.patient_id AS alert_patient_id, a.level AS alert_level FROM notifications n "
        "JOIN alerts a ON a.id = n.alert_id "
        "WHERE n.delivery_status='FAILED' AND n.attempt_count < ? "
        "AND (n.next_retry_at IS NULL OR n.next_retry_at <= ?) AND n.channel != 'none'",
        (MAX_TOTAL_ATTEMPTS, now_iso),
    ).fetchall()
    return [_retry_one(conn, row, provider, request_id) for row in rows]


def _retry_one(conn, row, provider: NotificationProvider, request_id: str) -> NotificationOutcome:
    attempt_count = row["attempt_count"] + 1
    status, provider_ref = "FAILED", None
    try:
        provider_ref = provider.send(row["channel"], row["alert_patient_id"], {"alert_id": row["alert_id"], "level": row["alert_level"]})
        status = "SENT"
    except Exception:
        LOGGER.exception("notification retry failed alert_id=%s channel=%s attempt=%s", row["alert_id"], row["channel"], attempt_count)

    next_retry_at = _next_retry_at(status, attempt_count)
    conn.execute(
        "UPDATE notifications SET delivery_status=?, provider_ref=?, attempt_count=?, next_retry_at=?, updated_at=? WHERE id=?",
        (status, provider_ref, attempt_count, next_retry_at, utc_now().isoformat(), row["id"]),
    )
    action = "notification.retry_sent" if status == "SENT" else (
        "notification.dead_lettered" if attempt_count >= MAX_TOTAL_ATTEMPTS else "notification.retry_failed"
    )
    _audit(conn, request_id, row["alert_id"], action, row["channel"])
    return NotificationOutcome(row["channel"], status, provider_ref)


def _audit(conn, request_id: str, alert_id: str, action: str, channel: str | None = None) -> None:
    import json
    conn.execute(
        "INSERT INTO audit_logs(id,occurred_at,request_id,actor_id,action,resource_type,resource_id,outcome,metadata) VALUES (?,?,?,?,?,?,?,?,?)",
        (str(uuid4()), utc_now().isoformat(), request_id, None, action, "ALERT", alert_id, "SUCCESS", json.dumps({"channel": channel} if channel else {})),
    )
