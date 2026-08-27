#!/usr/bin/env python
"""Retry FAILED alert notifications whose backoff window has elapsed.

This is the background half of the notification outbox pattern: notify_alert()
writes a durable row before attempting delivery and leaves it FAILED with a
next_retry_at timestamp if the synchronous burst does not succeed. Nothing
retries it further until this script runs.

There is no in-process scheduler here on purpose: a real deployment must invoke
this periodically via an OS-level scheduler (cron, systemd timer, Windows Task
Scheduler). Running it more often than the backoff window is harmless (the
WHERE clause in retry_pending_notifications is idempotent per invocation).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import Settings
from backend.app.db import connect, migrate
from backend.app.notifications import LogNotificationProvider, retry_pending_notifications


def main() -> None:
    settings = Settings.from_env()
    conn = connect(settings.database_path)
    migrate(conn)
    try:
        # LogNotificationProvider is the same development-only placeholder used at
        # alert-creation time. A real deployment must inject a real Email/SMS/Push
        # provider here instead, matching whatever notify_alert() is configured with.
        outcomes = retry_pending_notifications(conn, LogNotificationProvider(), "retry-worker-run")
    finally:
        conn.close()

    sent = sum(1 for o in outcomes if o.status == "SENT")
    failed = len(outcomes) - sent
    print(f"Retry run complete: {len(outcomes)} notification(s) attempted, {sent} sent, {failed} still failed.")


if __name__ == "__main__":
    main()
